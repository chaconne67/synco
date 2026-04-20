"""Project view tests: kanban, detail, close, reopen, auth, org isolation."""

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from projects.models import ProjectResult, ProjectStatus

pytestmark = pytest.mark.django_db


class TestProjectList:
    def test_project_list_200(self, logged_in_client, project):
        """GET /projects/ -> 200 with kanban context."""
        response = logged_in_client.get(reverse("projects:project_list"))
        assert response.status_code == 200
        assert "kanban" in response.context

    def test_unauthenticated_redirects(self):
        """Unauthenticated user -> login redirect."""
        c = Client()
        response = c.get(reverse("projects:project_list"))
        assert response.status_code == 302


class TestProjectDetail:
    def test_assigned_staff_can_access_project(self, staff_user, project_assigned_to_staff):
        from django.test import Client
        c = Client()
        c.force_login(staff_user)
        response = c.get(
            reverse("projects:project_detail", args=[project_assigned_to_staff.pk])
        )
        assert response.status_code == 200


class TestProjectClose:
    def test_close_project_post(self, logged_in_client, project):
        """POST /projects/<id>/close/ -> project closed + HX-Redirect."""
        response = logged_in_client.post(
            reverse("projects:project_close", args=[project.pk]),
            data={"result": "fail", "note": "테스트 종료"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 204
        assert "HX-Redirect" in response

        project.refresh_from_db()
        assert project.status == ProjectStatus.CLOSED
        assert project.closed_at is not None
        assert project.result == "fail"

    def test_close_project_get_renders_modal(self, logged_in_client, project):
        """GET /projects/<id>/close/ -> renders close modal form."""
        response = logged_in_client.get(
            reverse("projects:project_close", args=[project.pk])
        )
        assert response.status_code == 200


class TestProjectReopen:
    def test_reopen_project(self, logged_in_client, project):
        """POST /projects/<id>/reopen/ -> project reopened."""
        # Close first
        project.closed_at = timezone.now()
        project.status = ProjectStatus.CLOSED
        project.result = ProjectResult.FAIL
        project.save(update_fields=["closed_at", "status", "result"])

        response = logged_in_client.post(
            reverse("projects:project_reopen", args=[project.pk])
        )
        assert response.status_code == 302  # redirect

        project.refresh_from_db()
        assert project.status == ProjectStatus.OPEN
        assert project.result == ""
        assert project.closed_at is None
