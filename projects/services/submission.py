"""Submission service — ActionItem 1:1 relationship.

Phase 2b: Rewritten. Old Submission.Status transition logic removed
(Status field was deleted in Phase 1).
"""

from __future__ import annotations

from projects.models import ActionItem, Submission


def get_or_create_for_action(action_item: ActionItem, *, consultant=None) -> Submission:
    """submit_to_client ActionItem에 Submission을 1:1로 붙임."""
    if action_item.action_type.code != "submit_to_client":
        raise ValueError("submission only for submit_to_client action")
    submission, _ = Submission.objects.get_or_create(
        action_item=action_item,
        defaults={"consultant": consultant},
    )
    return submission
