"""ActionItem lifecycle tests NOT covered by test_phase2a_services.py.

Existing coverage:
- create_action on dropped raises
- complete -> propose_next

New coverage here:
- create_action success (status, assigned_to, title auto-gen)
- complete_action (status, completed_at, result)
- skip_action (status, completed_at)
- cancel_action (status)
- reschedule_action (due_at update)
- propose_next: incomplete -> empty list
- propose_next: inactive type excluded
- is_overdue property (3 scenarios)
- guard failures for all transitions
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from projects.models import (
    ActionItemStatus,
    ActionType,
)
from projects.services.action_lifecycle import (
    cancel_action,
    complete_action,
    create_action,
    propose_next,
    reschedule_action,
    skip_action,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------


class TestCreateAction:
    def test_create_action_success(self, application, action_type_reach_out, user):
        """Normal creation: pending status, assigned_to, auto-generated title."""
        action = create_action(application, action_type_reach_out, user)
        assert action.status == ActionItemStatus.PENDING
        assert action.assigned_to == user
        assert action.created_by == user
        assert application.candidate.name in action.title
        assert action_type_reach_out.label_ko in action.title

    def test_create_action_custom_title(self, application, action_type_reach_out, user):
        """Custom title overrides auto-generation."""
        action = create_action(
            application, action_type_reach_out, user, title="커스텀 제목"
        )
        assert action.title == "커스텀 제목"


class TestCompleteAction:
    def test_complete_sets_done(self, application, action_type_reach_out):
        action = create_action(application, action_type_reach_out, None)
        complete_action(action, None, result="success")
        assert action.status == ActionItemStatus.DONE
        assert action.completed_at is not None
        assert action.result == "success"


class TestSkipAction:
    def test_skip_sets_skipped(self, application, action_type_reach_out):
        action = create_action(application, action_type_reach_out, None)
        skip_action(action, None, note="skip reason")
        assert action.status == ActionItemStatus.SKIPPED
        assert action.completed_at is not None
        assert action.note == "skip reason"


class TestCancelAction:
    def test_cancel_sets_cancelled(self, application, action_type_reach_out):
        action = create_action(application, action_type_reach_out, None)
        cancel_action(action, None)
        assert action.status == ActionItemStatus.CANCELLED


class TestRescheduleAction:
    def test_reschedule_updates_due_at(self, application, action_type_reach_out):
        action = create_action(application, action_type_reach_out, None)
        new_due = timezone.now() + timedelta(days=7)
        reschedule_action(action, None, new_due_at=new_due)
        action.refresh_from_db()
        assert action.due_at == new_due


class TestProposeNext:
    def test_propose_next_incomplete_returns_empty(
        self, application, action_type_reach_out
    ):
        """Pending action -> empty suggestions."""
        action = create_action(application, action_type_reach_out, None)
        assert action.status == ActionItemStatus.PENDING
        suggestions = propose_next(action)
        assert suggestions == []

    def test_propose_next_excludes_inactive(self, application, action_type_reach_out):
        """Inactive types are excluded from suggestions."""
        action = create_action(application, action_type_reach_out, None)
        complete_action(action, None)

        # Deactivate all suggested types
        suggested_codes = action_type_reach_out.suggests_next or []
        if suggested_codes:
            ActionType.objects.filter(code__in=suggested_codes).update(is_active=False)
            suggestions = propose_next(action)
            assert len(suggestions) == 0
            # Re-activate for other tests
            ActionType.objects.filter(code__in=suggested_codes).update(is_active=True)


class TestIsOverdue:
    def test_pending_past_due_is_overdue(self, application, action_type_reach_out):
        """Pending + due_at in past -> True."""
        action = create_action(
            application,
            action_type_reach_out,
            None,
            due_at=timezone.now() - timedelta(hours=1),
        )
        assert action.is_overdue is True

    def test_done_past_due_not_overdue(self, application, action_type_reach_out):
        """Done + due_at in past -> False (completed)."""
        action = create_action(
            application,
            action_type_reach_out,
            None,
            due_at=timezone.now() - timedelta(hours=1),
        )
        complete_action(action, None)
        assert action.is_overdue is False

    def test_pending_no_due_not_overdue(self, application, action_type_reach_out):
        """Pending + due_at None -> False."""
        action = create_action(application, action_type_reach_out, None)
        assert action.due_at is None
        assert action.is_overdue is False


# ---------------------------------------------------------------------------
# Guard failures
# ---------------------------------------------------------------------------


class TestCreateActionGuards:
    def test_inactive_type_raises(self, application, action_type_reach_out):
        """Inactive action_type -> ValueError."""
        action_type_reach_out.is_active = False
        action_type_reach_out.save(update_fields=["is_active"])
        with pytest.raises(ValueError, match="inactive action_type"):
            create_action(application, action_type_reach_out, None)
        # Restore
        action_type_reach_out.is_active = True
        action_type_reach_out.save(update_fields=["is_active"])

    # NOTE: "create_action on dropped application" is already covered by
    # test_phase2a_services.py::test_create_action_on_dropped_raises.
    # Omitted here per plan principle: "중복 금지, 확장만".

    def test_closed_project_raises(self, application, action_type_reach_out):
        """Closed project -> ValueError."""
        project = application.project
        project.closed_at = timezone.now()
        project.status = "closed"
        project.save(update_fields=["closed_at", "status"])
        with pytest.raises(ValueError, match="closed project"):
            create_action(application, action_type_reach_out, None)


class TestTransitionGuards:
    """Non-pending actions cannot be completed/skipped/cancelled/rescheduled."""

    def test_complete_non_pending_raises(self, application, action_type_reach_out):
        action = create_action(application, action_type_reach_out, None)
        complete_action(action, None)
        with pytest.raises(ValueError, match="expected pending"):
            complete_action(action, None)

    def test_skip_non_pending_raises(self, application, action_type_reach_out):
        action = create_action(application, action_type_reach_out, None)
        complete_action(action, None)
        with pytest.raises(ValueError, match="expected pending"):
            skip_action(action, None)

    def test_cancel_non_pending_raises(self, application, action_type_reach_out):
        action = create_action(application, action_type_reach_out, None)
        complete_action(action, None)
        with pytest.raises(ValueError, match="expected pending"):
            cancel_action(action, None)

    def test_reschedule_non_pending_raises(self, application, action_type_reach_out):
        action = create_action(application, action_type_reach_out, None)
        complete_action(action, None)
        with pytest.raises(ValueError, match="expected pending"):
            reschedule_action(action, None, new_due_at=timezone.now())
