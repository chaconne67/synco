from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from batch_extract.models import GeminiBatchJob
from batch_extract.services.gemini_batch import download_results_for_job, sync_job_from_remote


class Command(BaseCommand):
    help = "Refresh batch job status from Gemini and download the result file when ready."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=str)

    def handle(self, *args, **options):
        job = GeminiBatchJob.objects.filter(pk=options["job_id"]).first()
        if not job:
            raise CommandError("Batch job not found")
        if not job.gemini_batch_name:
            raise CommandError("Batch job has not been submitted yet")

        remote = sync_job_from_remote(job)
        remote_state = remote.state.name if hasattr(remote.state, "name") else str(remote.state)
        self.stdout.write(f"Remote state: {remote_state}")

        if job.status == GeminiBatchJob.Status.SUCCEEDED and remote.dest and remote.dest.file_name:
            local_path = download_results_for_job(job, remote=remote)
            self.stdout.write(self.style.SUCCESS(f"Downloaded results to {local_path}"))
