"""AutoAction management: create (idempotent), apply, dismiss, validate.

Phase 1: Updated to use ActionStatusChoice (old ActionStatus/ActionType TextChoices deleted).
Phase 6: AutoAction model itself will be redesigned or removed.
"""

from __future__ import annotations

import logging

from django.db import transaction

from projects.models import ActionStatusChoice, ActionType, Application, AutoAction

logger = logging.getLogger(__name__)


class ConflictError(Exception):
    """Raised when an action is not in the expected state."""

    pass


class ValidationError(Exception):
    pass


# --- Validation ---

# Old ActionType TextChoices values used as string keys
ACTION_DATA_SCHEMA: dict[str, dict] = {
    "posting_draft": {"required": [], "optional": ["text"]},
    "candidate_search": {"required": [], "optional": ["candidate_ids"]},
    "submission_draft": {
        "required": ["candidate_id"],
        "optional": ["draft_json"],
    },
    "offer_template": {
        "required": ["submission_id"],
        "optional": ["salary", "terms"],
    },
    "followup_reminder": {
        "required": ["submission_id"],
        "optional": ["message"],
    },
    "recontact_reminder": {
        "required": ["contact_id"],
        "optional": ["message"],
    },
}


def validate_action_data(action_type: str, data: dict) -> bool:
    """Check that data has required keys for this action type."""
    schema = ACTION_DATA_SCHEMA.get(action_type)
    if not schema:
        return False
    for key in schema["required"]:
        if key not in data:
            return False
    return True


# --- Queries ---


def get_pending_actions(project) -> list[AutoAction]:
    """Return pending auto-actions for a project."""
    return list(
        AutoAction.objects.filter(
            project=project,
            status=ActionStatusChoice.PENDING,
        ).order_by("-created_at")
    )


# --- Type-specific apply handlers ---


def _apply_posting_draft(action, user):
    """Set project.posting_text from generated draft."""
    from projects.models import Project

    text = action.data.get("text", "")
    if text:
        Project.objects.filter(pk=action.project_id).update(posting_text=text)


def _apply_candidate_search(action, user):
    """Candidate search results stored in data; apply is acknowledgment only."""
    pass


def _apply_submission_draft(action, user):
    """Create or update SubmissionDraft with auto_draft_json."""

    # Phase 1: Submission no longer has project/candidate FK.
    # This handler is legacy and will be removed in Phase 6.
    logger.warning("_apply_submission_draft is legacy — skipping in Phase 1.")


def _apply_offer_template(action, user):
    """Create Offer from template data. NOOP — Offer model deleted."""
    # Phase 1: Offer model deleted. Phase 6 will remove this handler.
    logger.warning("_apply_offer_template is legacy — Offer model deleted.")


def _apply_followup_reminder(action, user):
    """Create Notification for the consultant."""
    from projects.models import Notification

    Notification.objects.get_or_create(
        recipient=user,
        type=Notification.Type.REMINDER,
        title=action.title,
        callback_data={"auto_action_id": str(action.pk)},
        defaults={
            "body": action.data.get("message", action.title),
        },
    )


def _apply_recontact_reminder(action, user):
    """Create Notification for the consultant."""
    from projects.models import Notification

    Notification.objects.get_or_create(
        recipient=user,
        type=Notification.Type.REMINDER,
        title=action.title,
        callback_data={"auto_action_id": str(action.pk)},
        defaults={
            "body": action.data.get("message", action.title),
        },
    )


_APPLY_HANDLERS = {
    "posting_draft": _apply_posting_draft,
    "candidate_search": _apply_candidate_search,
    "submission_draft": _apply_submission_draft,
    "offer_template": _apply_offer_template,
    "followup_reminder": _apply_followup_reminder,
    "recontact_reminder": _apply_recontact_reminder,
}


# --- Mutations ---


def apply_action(action_id, user) -> AutoAction:
    """Apply a pending action with type-specific dispatch. Raises ConflictError if not pending."""
    with transaction.atomic():
        action = AutoAction.objects.select_for_update().get(pk=action_id)
        if action.status != ActionStatusChoice.PENDING:
            raise ConflictError("이미 처리된 액션입니다.")

        if not validate_action_data(action.action_type, action.data):
            raise ValidationError("액션 데이터가 유효하지 않습니다.")

        # Type-specific dispatch
        handler = _APPLY_HANDLERS.get(action.action_type)
        if handler:
            handler(action, user)

        action.status = ActionStatusChoice.APPLIED
        action.applied_by = user
        action.save(update_fields=["status", "applied_by", "updated_at"])
    return action


def dismiss_action(action_id, user) -> AutoAction:
    """Dismiss a pending action. Raises ConflictError if not pending."""
    with transaction.atomic():
        action = AutoAction.objects.select_for_update().get(pk=action_id)
        if action.status != ActionStatusChoice.PENDING:
            raise ConflictError("이미 처리된 액션입니다.")
        action.status = ActionStatusChoice.DISMISSED
        action.dismissed_by = user
        action.save(update_fields=["status", "dismissed_by", "updated_at"])
    return action


# --- New helper for Application-based workflow ---

DEFAULT_FIRST_ACTION_CODE = "reach_out"


def suggest_initial_action(application: Application) -> ActionType | None:
    """Application 생성 직후 UI에 제안할 첫 ActionType. 생성은 하지 않음."""
    try:
        return ActionType.objects.get(code=DEFAULT_FIRST_ACTION_CODE, is_active=True)
    except ActionType.DoesNotExist:
        return None
