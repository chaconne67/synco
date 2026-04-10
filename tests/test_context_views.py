import json

import pytest
from django.test import Client as TestClient

from projects.models import ActionStatus, ActionType, AutoAction, ProjectContext


@pytest.fixture
def auth_client(user):
    client = TestClient()
    client.force_login(user)
    return client


@pytest.fixture
def other_org_client(other_org_user):
    client = TestClient()
    client.force_login(other_org_user)
    return client


@pytest.mark.django_db
class TestContextSaveView:
    def test_save_creates_context(self, auth_client, project, user):
        url = f"/projects/{project.pk}/context/save/"
        data = {
            "last_step": "contact_create",
            "pending_action": "Test action",
            "draft_data": {"form": "contact_create", "fields": {}},
        }
        response = auth_client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code == 204
        ctx = ProjectContext.objects.get(project=project, consultant=user)
        assert ctx.last_step == "contact_create"

    def test_save_invalid_data_returns_400(self, auth_client, project):
        url = f"/projects/{project.pk}/context/save/"
        data = {
            "last_step": "test",
            "pending_action": "test",
            "draft_data": {"no_form_key": True},
        }
        response = auth_client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_save_forbidden_for_other_org(self, other_org_client, project):
        url = f"/projects/{project.pk}/context/save/"
        data = {
            "last_step": "test",
            "pending_action": "test",
            "draft_data": {"form": "test"},
        }
        response = other_org_client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestContextDiscardView:
    def test_discard_deletes_context(self, auth_client, project, user):
        ProjectContext.objects.create(
            project=project,
            consultant=user,
            last_step="test",
            draft_data={"form": "test"},
        )
        url = f"/projects/{project.pk}/context/discard/"
        response = auth_client.post(url)
        assert response.status_code == 200
        assert not ProjectContext.objects.filter(
            project=project, consultant=user
        ).exists()


@pytest.mark.django_db
class TestContextResumeView:
    def test_resume_returns_hx_redirect(self, auth_client, project, user):
        ProjectContext.objects.create(
            project=project,
            consultant=user,
            last_step="contact_create",
            draft_data={"form": "contact_create", "fields": {"channel": "phone"}},
        )
        url = f"/projects/{project.pk}/context/resume/"
        response = auth_client.post(url)
        assert response.status_code == 200
        assert "HX-Redirect" in response
        redirect_url = response["HX-Redirect"]
        assert f"/projects/{project.pk}/contacts/new/" in redirect_url
        assert "resume=" in redirect_url

    def test_resume_no_context_returns_404(self, auth_client, project):
        url = f"/projects/{project.pk}/context/resume/"
        response = auth_client.post(url)
        assert response.status_code == 404

    def test_resume_unknown_form_returns_404(self, auth_client, project, user):
        ProjectContext.objects.create(
            project=project,
            consultant=user,
            last_step="unknown_form",
            draft_data={"form": "unknown_form"},
        )
        url = f"/projects/{project.pk}/context/resume/"
        response = auth_client.post(url)
        assert response.status_code == 404


@pytest.mark.django_db
class TestAutoActionApplyView:
    def test_apply_action(self, auth_client, project, user):
        action = AutoAction.objects.create(
            project=project,
            trigger_event="test",
            action_type=ActionType.FOLLOWUP_REMINDER,
            title="test",
            data={"submission_id": "fake", "message": "test"},
        )
        url = f"/projects/{project.pk}/auto-actions/{action.pk}/apply/"
        response = auth_client.post(url)
        assert response.status_code == 200
        action.refresh_from_db()
        assert action.status == ActionStatus.APPLIED

    def test_apply_already_applied_returns_409(self, auth_client, project):
        action = AutoAction.objects.create(
            project=project,
            trigger_event="test",
            action_type=ActionType.FOLLOWUP_REMINDER,
            title="test",
            data={"submission_id": "fake"},
            status=ActionStatus.APPLIED,
        )
        url = f"/projects/{project.pk}/auto-actions/{action.pk}/apply/"
        response = auth_client.post(url)
        assert response.status_code == 409


@pytest.mark.django_db
class TestAutoActionDismissView:
    def test_dismiss_action(self, auth_client, project, user):
        action = AutoAction.objects.create(
            project=project,
            trigger_event="test",
            action_type=ActionType.POSTING_DRAFT,
            title="test",
            data={},
        )
        url = f"/projects/{project.pk}/auto-actions/{action.pk}/dismiss/"
        response = auth_client.post(url)
        assert response.status_code == 200
        action.refresh_from_db()
        assert action.status == ActionStatus.DISMISSED


@pytest.mark.django_db
class TestAutoActionPermissions:
    def test_other_org_cannot_list_actions(self, other_org_client, project):
        url = f"/projects/{project.pk}/auto-actions/"
        response = other_org_client.get(url)
        assert response.status_code == 404

    def test_other_org_cannot_apply_action(self, other_org_client, project):
        action = AutoAction.objects.create(
            project=project,
            trigger_event="test",
            action_type=ActionType.POSTING_DRAFT,
            title="test",
            data={},
        )
        url = f"/projects/{project.pk}/auto-actions/{action.pk}/apply/"
        response = other_org_client.post(url)
        assert response.status_code == 404
