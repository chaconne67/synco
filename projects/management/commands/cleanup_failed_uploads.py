"""Clean up failed resume uploads older than 30 days."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from projects.models import ResumeUpload


class Command(BaseCommand):
    help = "Delete failed resume uploads older than 30 days"

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=30)
        old_failed = ResumeUpload.objects.filter(
            status=ResumeUpload.Status.FAILED,
            created_at__lt=cutoff,
        )
        count = 0
        for upload in old_failed:
            if upload.file:
                upload.file.delete(save=False)
            upload.delete()
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Cleaned up {count} failed uploads"))
