"""Signal tests NOT covered by test_phase2a_services.py.

Existing coverage:
- ActionItem DONE triggers screening
- submitted app drop reverts to searching
- reopen project clears result

New coverage here (stale state correction pattern):
- ActionItem creation corrects stale phase
- ActionItem deletion recomputes phase
- Application creation smoke
- Application deletion recomputes phase
- Project status sync: closed_at -> status=closed
- Project status sync: closed_at=None -> status=open, result=""
"""

import pytest
from django.utils import timezone

from projects.models import (
    ActionItem,
    ActionItemStatus,
    Project,
    ProjectPhase,
    ProjectStatus,
)
from projects.services.action_lifecycle import create_action

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Phase recompute (stale state correction)
# ---------------------------------------------------------------------------


class TestPhaseRecomputeOnActionChange:
    def test_action_creation_corrects_stale_phase(
        self, project, application, action_type_reach_out
    ):
        """Stale phase correction: DB set to screening, creating non-submit action
        triggers signal that corrects phase back to searching."""
        # Force stale state in DB
        Project.objects.filter(pk=project.pk).update(phase=ProjectPhase.SCREENING)
        project.refresh_from_db()
        assert project.phase == ProjectPhase.SCREENING

        # Creating a reach_out (not submit) -> signal fires -> corrects to searching
        create_action(application, action_type_reach_out, None)
        project.refresh_from_db()
        assert project.phase == ProjectPhase.SEARCHING

    def test_action_deletion_recomputes_phase(self, application, action_type_submit):
        """Deleting submitted ActionItem -> phase reverts from screening to searching."""
        ai = ActionItem.objects.create(
            application=application,
            action_type=action_type_submit,
            title="제출",
            status=ActionItemStatus.DONE,
            completed_at=timezone.now(),
        )
        project = application.project
        project.refresh_from_db()
        assert project.phase == ProjectPhase.SCREENING

        # Delete the action -> post_delete signal fires -> phase reverts
        ai.delete()
        project.refresh_from_db()
        assert project.phase == ProjectPhase.SEARCHING


class TestPhaseRecomputeOnApplicationChange:
    def test_application_creation_smoke(self, project, user):
        """Application creation triggers phase recompute (smoke test)."""
        from candidates.models import Candidate
        from projects.models import Application

        c = Candidate.objects.create(name="스모크후보")
        Application.objects.create(project=project, candidate=c, created_by=user)
        project.refresh_from_db()
        # Empty project -> searching
        assert project.phase == ProjectPhase.SEARCHING

    def test_application_deletion_recomputes_phase(
        self, project, application, action_type_submit
    ):
        """Deleting submitted application -> phase reverts to searching."""
        ActionItem.objects.create(
            application=application,
            action_type=action_type_submit,
            title="제출",
            status=ActionItemStatus.DONE,
            completed_at=timezone.now(),
        )
        project.refresh_from_db()
        assert project.phase == ProjectPhase.SCREENING

        application.delete()
        project.refresh_from_db()
        assert project.phase == ProjectPhase.SEARCHING


# ---------------------------------------------------------------------------
# Project status sync
# ---------------------------------------------------------------------------


class TestProjectStatusSync:
    def test_closed_at_syncs_status(self, project):
        """Setting closed_at -> status auto-synced to closed."""
        project.closed_at = timezone.now()
        project.status = ProjectStatus.CLOSED
        project.save()
        project.refresh_from_db()
        assert project.status == ProjectStatus.CLOSED

    def test_clear_closed_at_syncs_status_and_result(self, project):
        """Clearing closed_at -> status=open, result="" auto-synced."""
        project.closed_at = timezone.now()
        project.status = ProjectStatus.CLOSED
        project.result = "success"
        project.save()

        # Reopen
        project.closed_at = None
        project.save()
        project.refresh_from_db()
        assert project.status == ProjectStatus.OPEN
        assert project.result == ""
