from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from batch_extract.models import GeminiBatchJob
from batch_extract.services.ingest import ingest_job_results


class Command(BaseCommand):
    help = "Ingest a completed Gemini batch result file into the existing candidates pipeline."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=str)
        parser.add_argument("--workers", type=int, default=1)

    def handle(self, *args, **options):
        job = GeminiBatchJob.objects.filter(pk=options["job_id"]).first()
        if not job:
            raise CommandError("Batch job not found")
        if not job.result_file_path:
            raise CommandError("Batch job does not have a downloaded result file")

        summary = ingest_job_results(job, workers=options["workers"])
        self.stdout.write(
            self.style.SUCCESS(
                "Ingested batch job "
                f"{job.id}: processed={summary['processed']}, "
                f"ingested={summary['ingested']}, failed={summary['failed']}"
            )
        )
