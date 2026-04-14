"""Full lifecycle integration test per FINAL-SPEC section 6.1.

Single test reproducing the complete headhunting workflow:
Project -> Applications -> Actions -> Phase transitions -> Hire -> Close -> Reopen.
"""

import pytest
from django.utils import timezone

from projects.models import (
    ActionItemStatus,
    ActionType,
    ProjectPhase,
    ProjectResult,
    ProjectStatus,
)
from projects.services.action_lifecycle import (
    complete_action,
    create_action,
)
from projects.services.application_lifecycle import (
    create_application,
    drop,
    hire,
)
from projects.services.phase import compute_project_phase

pytestmark = pytest.mark.django_db


class TestFullLifecycleScenario:
    """Reproduce section 6.1 milestone-by-milestone."""

    def test_full_lifecycle(self, project, user):
        """End-to-end: create -> submit -> drop -> hire -> reopen."""
        from candidates.models import Candidate

        reach_out = ActionType.objects.get(code="reach_out")
        submit_type = ActionType.objects.get(code="submit_to_client")

        # ---------------------------------------------------------------
        # Step 1: Project starts as searching, open
        # ---------------------------------------------------------------
        assert project.status == ProjectStatus.OPEN
        assert compute_project_phase(project) == ProjectPhase.SEARCHING

        # ---------------------------------------------------------------
        # Step 2: Create 3 applications -> phase stays searching
        # ---------------------------------------------------------------
        c1 = Candidate.objects.create(name="1번후보")
        c2 = Candidate.objects.create(name="2번후보")
        c3 = Candidate.objects.create(name="3번후보")

        app1 = create_application(project, c1, user)
        app2 = create_application(project, c2, user)
        app3 = create_application(project, c3, user)

        project.refresh_from_db()
        assert compute_project_phase(project) == ProjectPhase.SEARCHING

        # ---------------------------------------------------------------
        # Step 3: App1 — reach_out -> complete -> submit_to_client -> complete
        #         Phase should transition to SCREENING (OR rule)
        # ---------------------------------------------------------------
        ro1 = create_action(app1, reach_out, user)
        complete_action(ro1, user)

        sub1 = create_action(app1, submit_type, user)
        complete_action(sub1, user, result="서류 전달 완료")

        project.refresh_from_db()
        assert project.phase == ProjectPhase.SCREENING

        # ---------------------------------------------------------------
        # Step 4: App2 — reach_out -> complete -> drop(candidate_declined)
        #         Phase stays SCREENING (app1's submit still active)
        # ---------------------------------------------------------------
        ro2 = create_action(app2, reach_out, user)
        complete_action(ro2, user)

        drop(app2, "candidate_declined", user)
        app2.refresh_from_db()
        assert app2.dropped_at is not None

        project.refresh_from_db()
        assert project.phase == ProjectPhase.SCREENING

        # ---------------------------------------------------------------
        # Step 5: App3 has no submit -> phase stays SCREENING
        # ---------------------------------------------------------------
        project.refresh_from_db()
        assert project.phase == ProjectPhase.SCREENING

        # ---------------------------------------------------------------
        # Step 6: App1 — confirm_hire -> hire()
        #         Project auto-closes, app3 auto-dropped, pending actions cancelled
        # ---------------------------------------------------------------
        # Give app3 a pending action before hire
        pending_action_3 = create_action(app3, reach_out, user)
        assert pending_action_3.status == ActionItemStatus.PENDING

        hire(app1, user)

        # Check project auto-close
        project.refresh_from_db()
        assert project.status == ProjectStatus.CLOSED
        assert project.result == ProjectResult.SUCCESS
        assert project.closed_at is not None

        # Check app1 hired
        app1.refresh_from_db()
        assert app1.hired_at is not None

        # Check app3 auto-dropped
        app3.refresh_from_db()
        assert app3.dropped_at is not None
        assert app3.drop_reason == "other"

        # Check app3's pending action cancelled
        pending_action_3.refresh_from_db()
        assert pending_action_3.status == ActionItemStatus.CANCELLED

        # ---------------------------------------------------------------
        # Step 7: Reopen -> status=open, result="", closed_at=None
        # ---------------------------------------------------------------
        project.closed_at = None
        project.status = ProjectStatus.OPEN
        project.result = ""
        project.save(update_fields=["closed_at", "status", "result"])

        project.refresh_from_db()
        assert project.status == ProjectStatus.OPEN
        assert project.result == ""
        assert project.closed_at is None


class TestCaseDClosedProjectAddCandidate:
    """Case D: closed project -> add candidate fails -> reopen -> add succeeds."""

    def test_case_d(self, project, user):
        from candidates.models import Candidate

        # Close the project
        project.closed_at = timezone.now()
        project.status = ProjectStatus.CLOSED
        project.result = ProjectResult.FAIL
        project.save(update_fields=["closed_at", "status", "result"])

        # Try to add candidate to closed project -> ValueError
        new_c = Candidate.objects.create(name="뉴후보")
        with pytest.raises(ValueError, match="closed project"):
            create_application(project, new_c, user)

        # Reopen
        project.closed_at = None
        project.status = ProjectStatus.OPEN
        project.result = ""
        project.save(update_fields=["closed_at", "status", "result"])

        # Now add candidate succeeds
        app = create_application(project, new_c, user)
        assert app.is_active
