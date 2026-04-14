from datetime import datetime

from django.utils import timezone

from projects.models import (
    ActionItem,
    ActionItemStatus,
    ActionType,
    Application,
)


def create_action(
    application: Application,
    action_type: ActionType,
    actor,
    *,
    title: str = "",
    channel: str = "",
    scheduled_at: datetime | None = None,
    due_at: datetime | None = None,
    parent_action: ActionItem | None = None,
    note: str = "",
) -> ActionItem:
    # guard: inactive type
    if not action_type.is_active:
        raise ValueError(f"inactive action_type: {action_type.code}")
    # guard: closed application/project [I-08]
    if not application.is_active:
        raise ValueError("cannot create action on inactive application")
    if application.project.closed_at is not None:
        raise ValueError("cannot create action on closed project")

    if not title:
        title = f"{application.candidate} \u00b7 {action_type.label_ko}"
    return ActionItem.objects.create(
        application=application,
        action_type=action_type,
        title=title,
        channel=channel or action_type.default_channel,
        scheduled_at=scheduled_at,
        due_at=due_at,
        parent_action=parent_action,
        note=note,
        assigned_to=actor,
        created_by=actor,
        status=ActionItemStatus.PENDING,
    )


def _require_pending(action: ActionItem) -> None:
    """Validate pending status before transition [I-08]."""
    if action.status != ActionItemStatus.PENDING:
        raise ValueError(f"action is {action.status}, expected pending")


def complete_action(
    action: ActionItem,
    actor,
    *,
    result: str = "",
    note: str = "",
) -> ActionItem:
    _require_pending(action)
    action.status = ActionItemStatus.DONE
    action.completed_at = timezone.now()
    if result:
        action.result = result
    if note:
        action.note = note
    action.save(
        update_fields=["status", "completed_at", "result", "note", "updated_at"]
    )
    return action


def skip_action(action: ActionItem, actor, *, note: str = "") -> ActionItem:
    _require_pending(action)
    action.status = ActionItemStatus.SKIPPED
    action.completed_at = timezone.now()
    if note:
        action.note = note
    action.save(update_fields=["status", "completed_at", "note", "updated_at"])
    return action


def cancel_action(action: ActionItem, actor) -> ActionItem:
    _require_pending(action)
    action.status = ActionItemStatus.CANCELLED
    action.save(update_fields=["status", "updated_at"])
    return action


def reschedule_action(
    action: ActionItem,
    actor,
    *,
    new_due_at: datetime | None = None,
    new_scheduled_at: datetime | None = None,
) -> ActionItem:
    _require_pending(action)
    fields = ["updated_at"]
    if new_due_at is not None:
        action.due_at = new_due_at
        fields.append("due_at")
    if new_scheduled_at is not None:
        action.scheduled_at = new_scheduled_at
        fields.append("scheduled_at")
    action.save(update_fields=fields)
    return action


def propose_next(action: ActionItem) -> list[ActionType]:
    """Return next action type candidates based on suggests_next."""
    if action.status != ActionItemStatus.DONE:
        return []
    codes = action.action_type.suggests_next or []
    return list(
        ActionType.objects.filter(code__in=codes, is_active=True).order_by(
            "sort_order"
        )
    )
