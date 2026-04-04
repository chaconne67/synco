from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError

from batch_extract.models import GeminiBatchItem, GeminiBatchJob
from batch_extract.services.gemini_batch import (
    create_batch_job,
    download_results_for_job,
    sync_job_from_remote,
    upload_request_file,
)
from batch_extract.services.ingest import ingest_job_results
from batch_extract.services.prepare import prepare_drive_job


class Command(BaseCommand):
    help = (
        "Prepare resumes, submit a Gemini Batch API extraction job, wait for completion, "
        "download results, and save them into the DB."
    )

    def add_arguments(self, parser):
        parser.add_argument("--folder", type=str, default="")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--prepare-workers", type=int, default=4)
        parser.add_argument("--ingest-workers", type=int, default=1)
        parser.add_argument("--parent-folder-id", type=str, default="root")
        parser.add_argument("--display-name", type=str, default="")
        parser.add_argument("--poll-interval", type=int, default=30)
        parser.add_argument("--timeout-minutes", type=int, default=24 * 60)

    def handle(self, *args, **options):
        display_name = options["display_name"] or "resume-batch-job"
        job = GeminiBatchJob.objects.create(
            display_name=display_name,
            status=GeminiBatchJob.Status.PREPARING,
        )
        self.stdout.write(f"Created local job {job.id}")

        job = prepare_drive_job(
            job=job,
            folder_name=options["folder"] or None,
            limit=options["limit"],
            parent_folder_id=options["parent_folder_id"],
            workers=options["prepare_workers"],
        )
        if job.total_requests == 0:
            raise CommandError("No new resume requests were prepared")
        self.stdout.write(
            self.style.SUCCESS(
                f"Prepared {job.total_requests} requests at {job.request_file_path}"
            )
        )

        uploaded = upload_request_file(job.request_file_path, display_name=job.display_name)
        remote_job = create_batch_job(
            model_name=job.model_name,
            file_name=uploaded.name,
            display_name=job.display_name,
        )
        job.gemini_file_name = uploaded.name
        job.gemini_batch_name = remote_job.name
        job.status = GeminiBatchJob.Status.SUBMITTED
        job.metadata = {
            **(job.metadata or {}),
            "uploaded_file": uploaded.model_dump(mode="json"),
            "remote_job": remote_job.model_dump(mode="json"),
        }
        job.save(
            update_fields=[
                "gemini_file_name",
                "gemini_batch_name",
                "status",
                "metadata",
                "updated_at",
            ]
        )
        job.items.filter(status=GeminiBatchItem.Status.PREPARED).update(
            status=GeminiBatchItem.Status.SUBMITTED
        )
        self.stdout.write(self.style.SUCCESS(f"Submitted remote batch {remote_job.name}"))

        deadline = time.monotonic() + (options["timeout_minutes"] * 60)
        remote = None
        while time.monotonic() < deadline:
            remote = sync_job_from_remote(job)
            remote_state = remote.state.name if hasattr(remote.state, "name") else str(remote.state)
            self.stdout.write(f"Remote state: {remote_state}")

            if job.status == GeminiBatchJob.Status.SUCCEEDED:
                break
            if job.status == GeminiBatchJob.Status.FAILED:
                raise CommandError(job.error_message or f"Remote batch failed: {remote_state}")
            time.sleep(options["poll_interval"])

        if job.status != GeminiBatchJob.Status.SUCCEEDED:
            raise CommandError("Timed out waiting for Gemini batch job completion")

        local_result_path = download_results_for_job(job, remote=remote)
        if not local_result_path:
            raise CommandError("Batch completed but no result file was available")
        self.stdout.write(self.style.SUCCESS(f"Downloaded results to {local_result_path}"))

        summary = ingest_job_results(job, workers=options["ingest_workers"])
        self.stdout.write(
            self.style.SUCCESS(
                "Batch pipeline finished "
                f"(processed={summary['processed']}, "
                f"ingested={summary['ingested']}, failed={summary['failed']})"
            )
        )
