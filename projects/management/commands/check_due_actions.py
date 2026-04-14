"""Check for due auto-actions. Run daily via cron."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from projects.models import (
    ActionStatusChoice,
    AutoAction,
    Notification,
)


class Command(BaseCommand):
    help = "Check for due auto-actions and create reminder notifications"

    def handle(self, *args, **options):
        now = timezone.now()

        due_count = self._process_due_actions(now)

        self.stdout.write(f"check_due_actions: {due_count} due actions processed")

    def _process_due_actions(self, now) -> int:
        """Create Notifications for due pending actions."""
        due_actions = AutoAction.objects.filter(
            status=ActionStatusChoice.PENDING,
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
            action.status = ActionStatusChoice.APPLIED
            action.save(update_fields=["status", "updated_at"])
            if created:
                count += 1
        return count
