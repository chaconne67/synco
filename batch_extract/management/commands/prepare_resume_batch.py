from __future__ import annotations

from django.core.management.base import BaseCommand

from batch_extract.models import GeminiBatchJob
from batch_extract.services.prepare import prepare_drive_job


class Command(BaseCommand):
    help = "Prepare a Gemini Batch API job for resume extraction without changing the existing import flow."

    def add_arguments(self, parser):
        parser.add_argument("--folder", type=str, default="")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--workers", type=int, default=4)
        parser.add_argument("--parent-folder-id", type=str, default="root")
        parser.add_argument("--display-name", type=str, default="")

    def handle(self, *args, **options):
        display_name = options["display_name"] or "resume-batch-job"
        job = GeminiBatchJob.objects.create(
            display_name=display_name,
            status=GeminiBatchJob.Status.PREPARING,
        )
        job = prepare_drive_job(
            job=job,
            folder_name=options["folder"] or None,
            limit=options["limit"],
            parent_folder_id=options["parent_folder_id"],
            workers=options["workers"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Prepared job {job.id} with {job.total_requests} requests"
            )
        )
        self.stdout.write(f"Request file: {job.request_file_path}")
