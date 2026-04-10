"""AutoAction management: create (idempotent), apply, dismiss, validate."""

from __future__ import annotations

import logging

from django.db import transaction

from projects.models import ActionStatus, ActionType, AutoAction

logger = logging.getLogger(__name__)


class ConflictError(Exception):
    """Raised when an action is not in the expected state."""

    pass


class ValidationError(Exception):
    pass


# --- Validation ---

ACTION_DATA_SCHEMA: dict[str, dict] = {
    ActionType.POSTING_DRAFT: {"required": [], "optional": ["text"]},
    ActionType.CANDIDATE_SEARCH: {"required": [], "optional": ["candidate_ids"]},
    ActionType.SUBMISSION_DRAFT: {
        "required": ["candidate_id"],
        "optional": ["draft_json"],
    },
    ActionType.OFFER_TEMPLATE: {
        "required": ["submission_id"],
        "optional": ["salary", "terms"],
    },
    ActionType.FOLLOWUP_REMINDER: {
        "required": ["submission_id"],
        "optional": ["message"],
    },
    ActionType.RECONTACT_REMINDER: {
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
            status=ActionStatus.PENDING,
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
    from projects.models import Submission, SubmissionDraft

    candidate_id = action.data.get("candidate_id")
    draft_json = action.data.get("draft_json", {})
    if not candidate_id or not draft_json:
        return
    submission = Submission.objects.filter(
        project=action.project,
        candidate_id=candidate_id,
    ).first()
    if submission:
        SubmissionDraft.objects.update_or_create(
            submission=submission,
            defaults={"auto_draft_json": draft_json},
        )


def _apply_offer_template(action, user):
    """Create Offer from template data."""
    from projects.models import Offer, Submission

    submission_id = action.data.get("submission_id")
    if not submission_id:
        return
    submission = Submission.objects.filter(pk=submission_id).first()
    if not submission:
        return
    if hasattr(submission, "offer"):
        return
    Offer.objects.create(
        submission=submission,
        salary=action.data.get("salary", ""),
        terms=action.data.get("terms", {}),
    )


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
    ActionType.POSTING_DRAFT: _apply_posting_draft,
    ActionType.CANDIDATE_SEARCH: _apply_candidate_search,
    ActionType.SUBMISSION_DRAFT: _apply_submission_draft,
    ActionType.OFFER_TEMPLATE: _apply_offer_template,
    ActionType.FOLLOWUP_REMINDER: _apply_followup_reminder,
    ActionType.RECONTACT_REMINDER: _apply_recontact_reminder,
}


# --- Mutations ---


def apply_action(action_id, user) -> AutoAction:
    """Apply a pending action with type-specific dispatch. Raises ConflictError if not pending."""
    with transaction.atomic():
        action = AutoAction.objects.select_for_update().get(pk=action_id)
        if action.status != ActionStatus.PENDING:
            raise ConflictError("이미 처리된 액션입니다.")

        if not validate_action_data(action.action_type, action.data):
            raise ValidationError("액션 데이터가 유효하지 않습니다.")

        # Type-specific dispatch
        _APPLY_HANDLERS[action.action_type](action, user)

        action.status = ActionStatus.APPLIED
        action.applied_by = user
        action.save(update_fields=["status", "applied_by", "updated_at"])
    return action


def dismiss_action(action_id, user) -> AutoAction:
    """Dismiss a pending action. Raises ConflictError if not pending."""
    with transaction.atomic():
        action = AutoAction.objects.select_for_update().get(pk=action_id)
        if action.status != ActionStatus.PENDING:
            raise ConflictError("이미 처리된 액션입니다.")
        action.status = ActionStatus.DISMISSED
        action.dismissed_by = user
        action.save(update_fields=["status", "dismissed_by", "updated_at"])
    return action
