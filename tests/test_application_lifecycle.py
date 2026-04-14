"""Application lifecycle tests NOT covered by test_phase2a_services.py.

Existing coverage:
- drop cancels pending actions
- double drop raises
- restore blocked on closed project
- hire dropped raises
- hire closes project + drops others + cancels pending

New coverage here:
- create_application success
- drop + restore round-trip
- hire full verification (hired_at, project fields, losers' actions cancelled)
- guard failures (parameterized)
- create_application on closed project
- create_application duplicate
"""

import pytest
from django.utils import timezone

from projects.models import (
    ActionItemStatus,
    ProjectResult,
    ProjectStatus,
)
from projects.services.action_lifecycle import create_action
from projects.services.application_lifecycle import (
    create_application,
    drop,
    hire,
    restore,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------


class TestCreateApplication:
    def test_create_application_success(self, project, user):
        from candidates.models import Candidate

        c = Candidate.objects.create(name="신규후보")
        app = create_application(project, c, user, notes="test note")
        assert app.project == project
        assert app.candidate == c
        assert app.notes == "test note"
        assert app.created_by == user
        assert app.is_active


class TestDropRestoreRoundTrip:
    def test_drop_then_restore(self, application, user):
        """Full round-trip: active -> dropped -> active."""
        drop(application, "unfit", None)
        assert application.dropped_at is not None
        assert application.drop_reason == "unfit"
        assert not application.is_active

        restore(application, None)
        application.refresh_from_db()
        assert application.dropped_at is None
        assert application.drop_reason == ""
        assert application.is_active


class TestHireFullVerification:
    def test_hire_sets_hired_at_and_closes_project(
        self, application, second_application, action_type_reach_out
    ):
        """hire() full processing check: hired_at, project closed, losers dropped, actions cancelled."""
        # Give second_application a pending action
        pending_action = create_action(second_application, action_type_reach_out, None)
        assert pending_action.status == ActionItemStatus.PENDING

        hire(application, None)

        # Check hired application
        application.refresh_from_db()
        assert application.hired_at is not None

        # Check project auto-close
        project = application.project
        project.refresh_from_db()
        assert project.closed_at is not None
        assert project.status == ProjectStatus.CLOSED
        assert project.result == ProjectResult.SUCCESS

        # Check losers dropped
        second_application.refresh_from_db()
        assert second_application.dropped_at is not None
        assert second_application.drop_reason == "other"

        # Check losers' pending actions cancelled (R1-11)
        pending_action.refresh_from_db()
        assert pending_action.status == ActionItemStatus.CANCELLED


# ---------------------------------------------------------------------------
# Guard failures — parameterized
# ---------------------------------------------------------------------------


class TestDropGuards:
    def test_drop_hired_raises(self, application):
        """Cannot drop a hired application."""
        application.hired_at = timezone.now()
        application.save(update_fields=["hired_at"])
        with pytest.raises(ValueError, match="cannot drop a hired"):
            drop(application, "unfit", None)

    def test_drop_invalid_reason_raises(self, application):
        """Invalid drop_reason raises ValueError."""
        with pytest.raises(ValueError, match="invalid drop_reason"):
            drop(application, "nonexistent_reason", None)


class TestRestoreGuards:
    def test_restore_not_dropped_raises(self, application):
        """Cannot restore an application that isn't dropped."""
        with pytest.raises(ValueError, match="not dropped"):
            restore(application, None)

    def test_restore_hired_raises(self, application):
        """Cannot restore a hired application."""
        application.dropped_at = timezone.now()
        application.hired_at = timezone.now()
        application.save(update_fields=["dropped_at", "hired_at"])
        with pytest.raises(ValueError, match="cannot restore a hired"):
            restore(application, None)


class TestHireGuards:
    def test_hire_already_hired_raises(self, application):
        """Cannot hire an already-hired application."""
        application.hired_at = timezone.now()
        application.save(update_fields=["hired_at"])
        with pytest.raises(ValueError, match="already hired"):
            hire(application, None)

    def test_hire_closed_project_raises(self, application):
        """Cannot hire in a closed project."""
        project = application.project
        project.closed_at = timezone.now()
        project.status = ProjectStatus.CLOSED
        project.result = ProjectResult.FAIL
        project.save(update_fields=["closed_at", "status", "result"])
        with pytest.raises(ValueError, match="cannot hire in a closed project"):
            hire(application, None)

    def test_hire_another_already_hired_raises(self, application, second_application):
        """Cannot hire when another app is already hired in the project.
        hire() closes the project, so the guard that fires first is 'closed project'.
        """
        hire(application, None)
        with pytest.raises(ValueError, match="cannot hire in a closed project"):
            hire(second_application, None)


class TestCreateApplicationGuards:
    def test_create_on_closed_project_raises(self, project, user):
        """Cannot add candidate to a closed project."""
        from candidates.models import Candidate

        project.closed_at = timezone.now()
        project.status = ProjectStatus.CLOSED
        project.save(update_fields=["closed_at", "status"])

        c = Candidate.objects.create(name="신규")
        with pytest.raises(ValueError, match="closed project"):
            create_application(project, c, user)

    def test_create_duplicate_raises(self, application, user):
        """Cannot create duplicate project+candidate application."""
        # application fixture already created one for project+candidate
        with pytest.raises(ValueError, match="이미 매칭된"):
            create_application(application.project, application.candidate, user)
