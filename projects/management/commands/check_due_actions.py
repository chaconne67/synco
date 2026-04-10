"""Check for due auto-actions and expiring locks. Run daily via cron."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from projects.models import (
    ActionStatus,
    ActionType,
    AutoAction,
    Contact,
    Notification,
)


class Command(BaseCommand):
    help = "Check for expiring locks and process due auto-action reminders"

    def handle(self, *args, **options):
        now = timezone.now()
        tomorrow = now + timedelta(days=1)

        lock_count = self._check_expiring_locks(now, tomorrow)
        due_count = self._process_due_actions(now)

        self.stdout.write(
            f"check_due_actions: {lock_count} lock reminders, "
            f"{due_count} due actions processed"
        )

    def _check_expiring_locks(self, now, tomorrow) -> int:
        """Create recontact reminders for locks expiring within 24h."""
        expiring = Contact.objects.filter(
            result=Contact.Result.RESERVED,
            locked_until__lte=tomorrow,
            locked_until__gt=now,
        ).select_related("candidate", "project", "consultant")

        count = 0
        for contact in expiring:
            contact_id = str(contact.pk)
            if AutoAction.objects.filter(
                project=contact.project,
                action_type=ActionType.RECONTACT_REMINDER,
                data__contact_id=contact_id,
            ).exists():
                continue
            AutoAction.objects.create(
                project=contact.project,
                trigger_event="lock_expiring",
                action_type=ActionType.RECONTACT_REMINDER,
                title=f"{contact.candidate.name} 컨택 잠금 내일 만료",
                data={"contact_id": contact_id},
                created_by=contact.consultant,
            )
            count += 1
        return count

    def _process_due_actions(self, now) -> int:
        """Create Notifications for due pending actions."""
        due_actions = AutoAction.objects.filter(
            status=ActionStatus.PENDING,
            due_at__lte=now,
        ).select_related("project", "created_by")

        count = 0
        for action in due_actions:
            recipient = action.created_by or action.project.created_by
            if not recipient:
                continue

            _, created = Notification.objects.get_or_create(
                recipient=recipient,
                type=Notification.Type.REMINDER,
                callback_data__auto_action_id=str(action.pk),
                defaults={
                    "title": action.title,
                    "body": action.data.get("message", action.title),
                    "callback_data": {"auto_action_id": str(action.pk)},
                },
            )
            # Mark the action as applied regardless
            action.status = ActionStatus.APPLIED
            action.save(update_fields=["status", "updated_at"])
            if created:
                count += 1
        return count
