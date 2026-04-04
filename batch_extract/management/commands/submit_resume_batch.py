from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from batch_extract.models import GeminiBatchItem, GeminiBatchJob
from batch_extract.services.gemini_batch import create_batch_job, upload_request_file


class Command(BaseCommand):
    help = "Upload a prepared JSONL request file and submit a Gemini Batch API job."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=str)

    def handle(self, *args, **options):
        job = GeminiBatchJob.objects.filter(pk=options["job_id"]).first()
        if not job:
            raise CommandError("Batch job not found")
        if not job.request_file_path:
            raise CommandError("Batch job has no request file")

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
