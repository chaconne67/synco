"""Phase 2a: phase derivation + Application/ActionItem lifecycle + signal tests."""

import pytest
from django.utils import timezone

from projects.models import (
    ActionItem,
    ActionItemStatus,
    ActionType,
    ProjectPhase,
    ProjectStatus,
)
from projects.services.phase import compute_project_phase

pytestmark = pytest.mark.django_db


# ===========================================================================
# Category A: Phase derivation (5 tests)
# ===========================================================================


def test_empty_project_is_searching(project):
    assert compute_project_phase(project) == ProjectPhase.SEARCHING


def test_application_without_actions_is_searching(project, application):
    assert compute_project_phase(project) == ProjectPhase.SEARCHING


def test_reach_out_pending_is_searching(application):
    reach_out = ActionType.objects.get(code="reach_out")
    ActionItem.objects.create(
        application=application,
        action_type=reach_out,
        title="연락",
        status=ActionItemStatus.PENDING,
    )
    application.project.refresh_from_db()
    assert compute_project_phase(application.project) == ProjectPhase.SEARCHING


def test_submit_to_client_done_is_screening(application):
    submit = ActionType.objects.get(code="submit_to_client")
    ActionItem.objects.create(
        application=application,
        action_type=submit,
        title="제출",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
    )
    application.project.refresh_from_db()
    assert compute_project_phase(application.project) == ProjectPhase.SCREENING


def test_closed_project_keeps_phase(project):
    project.closed_at = timezone.now()
    project.status = ProjectStatus.CLOSED
    project.phase = ProjectPhase.SCREENING
    project.save()
    assert compute_project_phase(project) == ProjectPhase.SCREENING


# ===========================================================================
# Category B: Signal integration (4 tests)
# ===========================================================================


def test_action_done_triggers_screening(application):
    """ActionItem DONE -> signal changes project.phase to screening."""
    submit = ActionType.objects.get(code="submit_to_client")
    ActionItem.objects.create(
        application=application,
        action_type=submit,
        title="제출",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
    )
    application.project.refresh_from_db()
    assert application.project.phase == ProjectPhase.SCREENING


def test_submitted_app_drop_reverts_to_searching(application):
    """Dropping submitted app reverts phase to searching."""
    from projects.services.application_lifecycle import drop

    submit = ActionType.objects.get(code="submit_to_client")
    ActionItem.objects.create(
        application=application,
        action_type=submit,
        title="제출",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
    )
    drop(application, "unfit", None)
    application.project.refresh_from_db()
    assert application.project.phase == ProjectPhase.SEARCHING


def test_hire_closes_project_and_drops_others(application, second_application):
    """hire -> project closed + others dropped + pending actions cancelled."""
    from projects.services.application_lifecycle import hire

    ActionItem.objects.create(
        application=second_application,
        action_type=ActionType.objects.get(code="reach_out"),
        title="연락",
        status=ActionItemStatus.PENDING,
    )
    hire(application, None)
    application.project.refresh_from_db()
    second_application.refresh_from_db()
    assert application.project.status == ProjectStatus.CLOSED
    assert application.project.result == "success"
    assert second_application.dropped_at is not None
    pending_count = ActionItem.objects.filter(
        application=second_application,
        status=ActionItemStatus.PENDING,
    ).count()
    assert pending_count == 0


def test_reopen_project_clears_result(project):
    """closed -> reopen: status=open, result='' auto-sync."""
    project.closed_at = timezone.now()
    project.status = ProjectStatus.CLOSED
    project.result = "success"
    project.save()
    # reopen
    project.closed_at = None
    project.save()
    project.refresh_from_db()
    assert project.status == ProjectStatus.OPEN
    assert project.result == ""


# ===========================================================================
# Category C: Service lifecycle (6 tests)
# ===========================================================================


def test_drop_cancels_pending_actions(application):
    from projects.services.action_lifecycle import create_action
    from projects.services.application_lifecycle import drop

    action = create_action(
        application, ActionType.objects.get(code="reach_out"), None
    )
    drop(application, "unfit", None)
    action.refresh_from_db()
    assert action.status == ActionItemStatus.CANCELLED


def test_double_drop_raises(application):
    from projects.services.application_lifecycle import drop

    drop(application, "unfit", None)
    with pytest.raises(ValueError, match="already dropped"):
        drop(application, "unfit", None)


def test_restore_blocked_on_closed_project(application, second_application):
    from projects.models import Application
    from projects.services.application_lifecycle import drop, hire, restore

    # drop second_application first, then hire first -> project closes
    drop(second_application, "unfit", None)
    hire(application, None)
    # refresh from DB to pick up the closed project
    second_application = Application.objects.select_related("project").get(
        pk=second_application.pk
    )
    # now try to restore second_application in closed project
    with pytest.raises(ValueError, match="cannot restore application in a closed project"):
        restore(second_application, None)


def test_hire_dropped_raises(application):
    from projects.services.application_lifecycle import drop, hire

    drop(application, "unfit", None)
    with pytest.raises(ValueError, match="cannot hire a dropped"):
        hire(application, None)


def test_create_action_on_dropped_raises(application):
    from projects.services.action_lifecycle import create_action
    from projects.services.application_lifecycle import drop

    drop(application, "unfit", None)
    with pytest.raises(ValueError, match="cannot create action on inactive application"):
        create_action(
            application, ActionType.objects.get(code="reach_out"), None
        )


def test_complete_then_propose_next(application):
    from projects.services.action_lifecycle import complete_action, create_action, propose_next

    reach_out = ActionType.objects.get(code="reach_out")
    action = create_action(application, reach_out, None)
    complete_action(action, None)
    suggestions = propose_next(action)
    expected_codes = set(reach_out.suggests_next)
    actual_codes = {s.code for s in suggestions}
    assert actual_codes == expected_codes


# ===========================================================================
# Category D: Seed integrity (1 test)
# ===========================================================================


def test_action_type_seed_integrity(db):
    """ActionType seed: 23 types + 4 protected must be present and active."""
    assert ActionType.objects.count() >= 23
    protected_codes = [
        "submit_to_client",
        "pre_meeting",
        "interview_round",
        "confirm_hire",
    ]
    for code in protected_codes:
        at = ActionType.objects.get(code=code)
        assert at.is_active, f"{code} should be active"
        assert at.is_protected, f"{code} should be protected"
