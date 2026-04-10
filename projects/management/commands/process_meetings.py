"""Process pending meeting recordings (STT + LLM analysis).

Run via cron or manually:
    python manage.py process_meetings
    python manage.py process_meetings --id <uuid>  # single record
"""

from django.core.management.base import BaseCommand

from projects.models import MeetingRecord
from projects.services.voice.meeting_analyzer import analyze_meeting


class Command(BaseCommand):
    help = "Process pending meeting recordings (STT + LLM analysis)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--id",
            type=str,
            help="Process a specific MeetingRecord by UUID",
        )

    def handle(self, *args, **options):
        record_id = options.get("id")

        if record_id:
            try:
                record = MeetingRecord.objects.get(pk=record_id)
                self.stdout.write(f"Processing meeting {record.pk}...")
                analyze_meeting(record.pk)
                record.refresh_from_db()
                self.stdout.write(self.style.SUCCESS(f"Done: {record.status}"))
            except MeetingRecord.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(f"MeetingRecord {record_id} not found")
                )
            return

        pending = MeetingRecord.objects.filter(
            status=MeetingRecord.Status.UPLOADED,
        ).order_by("created_at")

        if not pending.exists():
            self.stdout.write("No pending meetings to process.")
            return

        self.stdout.write(f"Found {pending.count()} pending meeting(s).")
        for record in pending:
            self.stdout.write(f"  Processing {record.pk} ({record.candidate})...")
            try:
                analyze_meeting(record.pk)
                record.refresh_from_db()
                self.stdout.write(f"    -> {record.status}")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"    -> Failed: {e}"))
