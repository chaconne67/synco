"""긴급도 자동 산정 로직."""

from __future__ import annotations

from django.utils import timezone

from projects.models import ActionItem, ActionItemStatus, Project


def collect_all_actions(project: Project) -> list[dict]:
    """Collect pending action items with urgency metadata."""
    now = timezone.now()
    items = ActionItem.objects.filter(
        application__project=project,
        status=ActionItemStatus.PENDING,
    ).select_related("action_type", "application__candidate")

    result = []
    for item in items:
        is_overdue = item.due_at is not None and item.due_at < now
        result.append(
            {
                "action_item": item,
                "title": item.title,
                "due_at": item.due_at,
                "overdue": is_overdue,
            }
        )
    return result


def compute_project_urgency(project: Project) -> dict | None:
    """Compute project urgency based on ActionItem due dates."""
    actions = collect_all_actions(project)
    if not actions:
        return None

    overdue_count = sum(1 for a in actions if a["overdue"])
    pending_count = len(actions)

    return {
        "pending_count": pending_count,
        "overdue_count": overdue_count,
        "has_overdue": overdue_count > 0,
    }
