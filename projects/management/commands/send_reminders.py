"""Generate and send daily reminder notifications via Telegram."""

from __future__ import annotations

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from projects.models import Contact, Interview, Notification, Submission
from projects.services.notification import send_notification
from projects.telegram.formatters import format_reminder


class Command(BaseCommand):
    help = "Generate and send daily reminder notifications"

    def handle(self, *args, **options):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        now = timezone.now()
        total_sent = 0

        # 1. Recontact reminders
        recontacts = Contact.objects.filter(
            next_contact_date=today,
            result=Contact.Result.RESERVED,
        ).select_related("consultant", "candidate", "project")

        for contact in recontacts:
            if not contact.consultant:
                continue
            notif = Notification.objects.create(
                recipient=contact.consultant,
                type=Notification.Type.REMINDER,
                title="재컨택 예정",
                body=f"{contact.candidate.name} - {contact.project.title}",
            )
            text = format_reminder(
                reminder_type="recontact",
                details=f"{contact.candidate.name} - {contact.project.title}",
            )
            if send_notification(notif, text=text):
                total_sent += 1

        # 2. Lock expiry reminders (tomorrow)
        lock_expiring = Contact.objects.filter(
            locked_until__date=tomorrow,
            result=Contact.Result.RESERVED,
        ).select_related("consultant", "candidate", "project")

        for contact in lock_expiring:
            if not contact.consultant:
                continue
            notif = Notification.objects.create(
                recipient=contact.consultant,
                type=Notification.Type.REMINDER,
                title="잠금 만료 임박",
                body=f"{contact.candidate.name} - {contact.project.title}",
            )
            text = format_reminder(
                reminder_type="lock_expiry",
                details=f"{contact.candidate.name} - {contact.project.title} (만료: {contact.locked_until:%m/%d})",
            )
            if send_notification(notif, text=text):
                total_sent += 1

        # 3. Submission review pending 2+ days
        stale_submissions = Submission.objects.filter(
            status=Submission.Status.SUBMITTED,
            submitted_at__lte=now - timedelta(days=2),
            client_feedback="",
        ).select_related("consultant", "candidate", "project")

        for sub in stale_submissions:
            if not sub.consultant:
                continue
            notif = Notification.objects.create(
                recipient=sub.consultant,
                type=Notification.Type.REMINDER,
                title="서류 검토 대기",
                body=f"{sub.candidate.name} - {sub.project.title} (제출: {sub.submitted_at:%m/%d})",
            )
            text = format_reminder(
                reminder_type="submission_review",
                details=f"{sub.candidate.name} - {sub.project.title} (제출: {sub.submitted_at:%m/%d})",
            )
            if send_notification(notif, text=text):
                total_sent += 1

        # 4. Interview tomorrow
        tomorrow_interviews = Interview.objects.filter(
            scheduled_at__date=tomorrow,
            result=Interview.Result.PENDING,
        ).select_related(
            "submission__consultant", "submission__candidate", "submission__project"
        )

        for interview in tomorrow_interviews:
            consultant = interview.submission.consultant
            if not consultant:
                continue
            candidate = interview.submission.candidate
            project = interview.submission.project
            notif = Notification.objects.create(
                recipient=consultant,
                type=Notification.Type.REMINDER,
                title="내일 면접",
                body=f"{candidate.name} - {project.title} ({interview.scheduled_at:%H:%M})",
            )
            text = format_reminder(
                reminder_type="interview_tomorrow",
                details=f"{candidate.name} - {project.title}\n시간: {interview.scheduled_at:%H:%M}\n장소: {interview.location or '미정'}",
            )
            if send_notification(notif, text=text):
                total_sent += 1

        self.stdout.write(self.style.SUCCESS(f"Sent {total_sent} reminder(s)"))
