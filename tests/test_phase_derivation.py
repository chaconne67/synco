"""Phase derivation edge cases NOT covered by test_phase2a_services.py.

Existing coverage (16 tests):
- empty project -> searching
- application without actions -> searching
- reach_out pending -> searching
- submit_to_client done -> screening
- closed project keeps phase

New coverage here:
- reach_out done -> still searching (not submit)
- submit_to_client pending -> still searching (not done)
- dropped app with submit -> searching (multi-app OR rule)
- other app's submit keeps screening (OR rule)
- new app added, existing submit -> screening maintained
- application deleted -> phase recomputed via post_delete signal
"""

import pytest
from django.utils import timezone

from projects.models import ActionItem, ActionItemStatus, ProjectPhase
from projects.services.phase import compute_project_phase

pytestmark = pytest.mark.django_db


def test_reach_out_done_is_still_searching(application, action_type_reach_out):
    """reach_out completed -> still searching (submit_to_client required for screening)."""
    ActionItem.objects.create(
        application=application,
        action_type=action_type_reach_out,
        title="연락",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
    )
    application.project.refresh_from_db()
    assert compute_project_phase(application.project) == ProjectPhase.SEARCHING


def test_submit_pending_is_still_searching(application, action_type_submit):
    """submit_to_client pending -> still searching (must be done)."""
    ActionItem.objects.create(
        application=application,
        action_type=action_type_submit,
        title="제출",
        status=ActionItemStatus.PENDING,
    )
    application.project.refresh_from_db()
    assert compute_project_phase(application.project) == ProjectPhase.SEARCHING


def test_multi_app_dropped_submit_reverts_to_searching(
    application, second_application, action_type_submit
):
    """Multiple apps: drop the only submitted one -> back to searching."""
    from projects.services.application_lifecycle import drop

    # submit on first app only
    ActionItem.objects.create(
        application=application,
        action_type=action_type_submit,
        title="제출",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
    )
    application.project.refresh_from_db()
    assert compute_project_phase(application.project) == ProjectPhase.SCREENING

    # drop first app -> second has no submit -> back to searching
    drop(application, "unfit", None)
    application.project.refresh_from_db()
    assert compute_project_phase(application.project) == ProjectPhase.SEARCHING


def test_other_app_submit_keeps_screening(
    application, second_application, action_type_submit
):
    """OR rule: another app's submit maintains screening even if first has no submit."""
    ActionItem.objects.create(
        application=second_application,
        action_type=action_type_submit,
        title="제출",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
    )
    application.project.refresh_from_db()
    assert compute_project_phase(application.project) == ProjectPhase.SCREENING


def test_new_app_added_with_existing_submit_stays_screening(
    project, application, action_type_submit, user
):
    """Adding a new app when submit already exists -> screening maintained."""
    from candidates.models import Candidate
    from projects.models import Application

    ActionItem.objects.create(
        application=application,
        action_type=action_type_submit,
        title="제출",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
    )
    project.refresh_from_db()
    assert compute_project_phase(project) == ProjectPhase.SCREENING

    # Add new candidate without submit
    new_candidate = Candidate.objects.create(name="최후보")
    Application.objects.create(
        project=project, candidate=new_candidate, created_by=user
    )
    project.refresh_from_db()
    assert compute_project_phase(project) == ProjectPhase.SCREENING


def test_application_delete_recomputes_phase(project, application, action_type_submit):
    """post_delete signal: deleting submitted application -> phase recomputed."""
    ActionItem.objects.create(
        application=application,
        action_type=action_type_submit,
        title="제출",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
    )
    project.refresh_from_db()
    assert project.phase == ProjectPhase.SCREENING

    # Delete the application -> post_delete signal triggers phase recompute
    application.delete()
    project.refresh_from_db()
    assert project.phase == ProjectPhase.SEARCHING
