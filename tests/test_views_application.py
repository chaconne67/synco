"""Application view tests: CRUD, HTMX contracts, auth, org isolation."""

import pytest
from django.test import Client
from django.urls import reverse

from projects.models import Application, ProjectStatus

pytestmark = pytest.mark.django_db


class TestAddCandidate:
    def test_add_candidate_post(self, logged_in_client, project, org):
        """POST /projects/<id>/add_candidate/ -> Application created + HX-Trigger."""
        from candidates.models import Candidate

        c = Candidate.objects.create(name="신규후보", owned_by=org)
        response = logged_in_client.post(
            reverse("projects:project_add_candidate", args=[project.pk]),
            data={"candidate": str(c.pk), "notes": "test"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        assert response.content == b""
        assert response["HX-Trigger"] == "applicationChanged"
        assert Application.objects.filter(project=project, candidate=c).exists()

    def test_add_candidate_get_renders_modal(self, logged_in_client, project):
        """GET /projects/<id>/add_candidate/ -> renders modal form."""
        response = logged_in_client.get(
            reverse("projects:project_add_candidate", args=[project.pk])
        )
        assert response.status_code == 200

    def test_duplicate_candidate_returns_error(
        self, logged_in_client, application, org
    ):
        """Duplicate project+candidate -> error response (not 500)."""
        # application fixture already matched candidate to project
        candidate = application.candidate
        candidate.owned_by = org
        candidate.save(update_fields=["owned_by"])

        response = logged_in_client.post(
            reverse("projects:project_add_candidate", args=[application.project.pk]),
            data={"candidate": str(candidate.pk)},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 400

    def test_invalid_post_returns_400(self, logged_in_client, project):
        """Empty candidate_id -> form error, not 500."""
        response = logged_in_client.post(
            reverse("projects:project_add_candidate", args=[project.pk]),
            data={},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 400


class TestApplicationDrop:
    def test_drop_post_htmx(self, logged_in_client, application):
        """POST drop with HTMX -> 204 + HX-Trigger."""
        response = logged_in_client.post(
            reverse("projects:application_drop", args=[application.pk]),
            data={"drop_reason": "unfit"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        assert response.content == b""
        assert response["HX-Trigger"] == "applicationChanged"
        application.refresh_from_db()
        assert application.dropped_at is not None

    def test_drop_get_renders_modal(self, logged_in_client, application):
        """GET drop -> renders drop modal."""
        response = logged_in_client.get(
            reverse("projects:application_drop", args=[application.pk])
        )
        assert response.status_code == 200

    def test_other_org_drop_404(self, other_org_client, application):
        """Drop from other org -> 404."""
        response = other_org_client.post(
            reverse("projects:application_drop", args=[application.pk]),
            data={"drop_reason": "unfit"},
        )
        assert response.status_code == 404


class TestApplicationRestore:
    def test_restore_post(self, logged_in_client, application):
        """POST restore -> application undropped."""
        from projects.services.application_lifecycle import drop

        drop(application, "unfit", None)
        response = logged_in_client.post(
            reverse("projects:application_restore", args=[application.pk]),
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        application.refresh_from_db()
        assert application.dropped_at is None


class TestApplicationHire:
    def test_hire_post_htmx(self, logged_in_client, application):
        """POST hire -> 204 + HX-Redirect."""
        response = logged_in_client.post(
            reverse("projects:application_hire", args=[application.pk]),
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 204
        assert "HX-Redirect" in response
        application.refresh_from_db()
        assert application.hired_at is not None
        application.project.refresh_from_db()
        assert application.project.status == ProjectStatus.CLOSED

    def test_other_org_hire_404(self, other_org_client, application):
        """Hire from other org -> 404."""
        response = other_org_client.post(
            reverse("projects:application_hire", args=[application.pk]),
        )
        assert response.status_code == 404


class TestApplicationAuthEdge:
    def test_unauthenticated_drop_raises(self, application):
        """Unauthenticated user accessing drop -> AttributeError (missing @login_required).
        Phase 6 should add @login_required to Phase 3b views.
        """
        c = Client(raise_request_exception=False)
        response = c.post(
            reverse("projects:application_drop", args=[application.pk]),
            data={"drop_reason": "unfit"},
        )
        # membership_required without login_required -> 500
        # Documents current behavior; Phase 6 will fix.
        assert response.status_code == 500
