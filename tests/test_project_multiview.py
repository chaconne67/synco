"""P04: Project Multi-View tests.

Tests for board/list/table view switching, tab_switch partial rendering,
status_update PATCH endpoint, filter preservation across views,
table annotate counts, board all-status display, and org isolation.
"""

import json
from datetime import timedelta

import pytest
from django.test import Client as TestClient
from django.utils import timezone

from accounts.models import User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Contact, Interview, Project, Submission


# --- Fixtures ---




@pytest.fixture
def user_with_org(db):
    user = User.objects.create_user(username="mv_tester", password="test1234")
    return user


@pytest.fixture
def user_with_org2(db):
    user = User.objects.create_user(username="mv_tester2", password="test1234")
    return user


@pytest.fixture
def auth_client(user_with_org):
    c = TestClient()
    c.login(username="mv_tester", password="test1234")
    return c


@pytest.fixture
def auth_client2(user_with_org2):
    c = TestClient()
    c.login(username="mv_tester2", password="test1234")
    return c


@pytest.fixture
def client_obj(org):
    return Client.objects.create(
        name="Acme Corp",
        industry="IT")


@pytest.fixture
def client_obj2(org2):
    return Client.objects.create(
        name="Other Corp",
        industry="Finance")


@pytest.fixture
def project_new(org, client_obj, user_with_org):
    p = Project.objects.create(
        client=client_obj
        title="New Project",
        status="new",
        created_by=user_with_org)
    p.assigned_consultants.add(user_with_org)
    return p


@pytest.fixture
def project_searching(org, client_obj, user_with_org):
    p = Project.objects.create(
        client=client_obj
        title="Searching Project",
        status="searching",
        created_by=user_with_org)
    p.assigned_consultants.add(user_with_org)
    return p


@pytest.fixture
def project_other_org(org2, client_obj2, user_with_org2):
    return Project.objects.create(
        client=client_obj2
        title="Other Org Project",
        status="new",
        created_by=user_with_org2)


# --- View Switching ---


class TestViewSwitching:
    @pytest.mark.django_db
    def test_board_view_default(self, auth_client, project_new):
        resp = auth_client.get("/projects/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "kanban-board" in content or "kanban-column" in content

    @pytest.mark.django_db
    def test_board_view_explicit(self, auth_client, project_new):
        resp = auth_client.get("/projects/?view=board")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "kanban-board" in content or "kanban-column" in content

    @pytest.mark.django_db
    def test_list_view(self, auth_client, project_new):
        resp = auth_client.get("/projects/?view=list")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "New Project" in content

    @pytest.mark.django_db
    def test_table_view(self, auth_client, project_new):
        resp = auth_client.get("/projects/?view=table")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "New Project" in content

    @pytest.mark.django_db
    def test_invalid_view_falls_back_to_board(self, auth_client, project_new):
        resp = auth_client.get("/projects/?view=invalid")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "kanban-board" in content or "kanban-column" in content

    @pytest.mark.django_db
    def test_all_three_views_render_200(self, auth_client, project_new):
        for view in ("board", "list", "table"):
            resp = auth_client.get(f"/projects/?view={view}")
            assert resp.status_code == 200, f"View {view} failed"


# --- Tab Switch Partial Rendering ---


class TestTabSwitchPartial:
    @pytest.mark.django_db
    def test_tab_switch_returns_partial_only(self, auth_client, project_new):
        resp = auth_client.get(
            "/projects/?view=board&tab_switch=1",
            HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        content = resp.content.decode()
        # Partial should not have full page wrapper
        assert "<!DOCTYPE" not in content
        # But should have board content
        assert "kanban" in content

    @pytest.mark.django_db
    def test_tab_switch_list_returns_partial(self, auth_client, project_new):
        resp = auth_client.get(
            "/projects/?view=list&tab_switch=1",
            HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "<!DOCTYPE" not in content

    @pytest.mark.django_db
    def test_tab_switch_table_returns_partial(self, auth_client, project_new):
        resp = auth_client.get(
            "/projects/?view=table&tab_switch=1",
            HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "<!DOCTYPE" not in content

    @pytest.mark.django_db
    def test_full_page_request_includes_tabs(self, auth_client, project_new):
        resp = auth_client.get("/projects/?view=board")
        content = resp.content.decode()
        assert "view=board" in content
        assert "view=list" in content
        assert "view=table" in content


# --- Filter Preservation ---


class TestFilterPreservation:
    @pytest.mark.django_db
    def test_filters_in_board_view(self, auth_client, project_new):
        resp = auth_client.get("/projects/?view=board&scope=all&status=new")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "New Project" in content

    @pytest.mark.django_db
    def test_filters_in_list_view(self, auth_client, project_new):
        resp = auth_client.get("/projects/?view=list&scope=all&status=new")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_filters_in_table_view(self, auth_client, project_new):
        resp = auth_client.get("/projects/?view=table&scope=all&status=new")
        assert resp.status_code == 200


# --- Status Update (PATCH) ---


class TestStatusUpdate:
    @pytest.mark.django_db
    def test_patch_updates_status(self, auth_client, project_new):
        resp = auth_client.patch(
            f"/projects/{project_new.pk}/status/",
            data=json.dumps({"status": "searching"}),
            content_type="application/json")
        assert resp.status_code == 204
        project_new.refresh_from_db()
        assert project_new.status == "searching"

    @pytest.mark.django_db
    def test_patch_invalid_status_returns_400(self, auth_client, project_new):
        resp = auth_client.patch(
            f"/projects/{project_new.pk}/status/",
            data=json.dumps({"status": "nonexistent"}),
            content_type="application/json")
        assert resp.status_code == 400

    @pytest.mark.django_db
    def test_patch_requires_login(self, project_new):
        c = TestClient()
        resp = c.patch(
            f"/projects/{project_new.pk}/status/",
            data=json.dumps({"status": "searching"}),
            content_type="application/json")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    @pytest.mark.django_db
    def test_patch_org_isolation(self, auth_client, project_other_org):
        resp = auth_client.patch(
            f"/projects/{project_other_org.pk}/status/",
            data=json.dumps({"status": "searching"}),
            content_type="application/json")
        assert resp.status_code == 404

    @pytest.mark.django_db
    def test_patch_only_patch_method(self, auth_client, project_new):
        resp = auth_client.get(f"/projects/{project_new.pk}/status/")
        assert resp.status_code == 405

    @pytest.mark.django_db
    def test_patch_post_method_not_allowed(self, auth_client, project_new):
        resp = auth_client.post(
            f"/projects/{project_new.pk}/status/",
            data=json.dumps({"status": "searching"}),
            content_type="application/json")
        assert resp.status_code == 405


# --- Board View: All 10 Statuses ---


class TestBoardAllStatuses:
    @pytest.mark.django_db
    def test_board_shows_all_10_status_columns(self, auth_client, project_new):
        resp = auth_client.get("/projects/?view=board&scope=all")
        content = resp.content.decode()
        # All 10 status labels should appear
        for _, label in Project._meta.get_field("status").choices:
            assert label in content, f"Status '{label}' not found in board"


# --- Table View: Annotated Counts ---


class TestTableAnnotations:
    @pytest.mark.django_db
    def test_table_shows_counts(self, auth_client, project_new, user_with_org):
        # Create a candidate, contact, submission, and interview
        candidate = Candidate.objects.create(name="Test Candidate")
        Contact.objects.create(
            project=project_new,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답")
        sub = Submission.objects.create(
            project=project_new,
            candidate=candidate,
            consultant=user_with_org)
        Interview.objects.create(
            submission=sub,
            round=1,
            scheduled_at=timezone.now(),
            type="대면")

        resp = auth_client.get("/projects/?view=table&scope=all")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "New Project" in content


# --- List View: Urgency Groups ---


class TestListUrgency:
    @pytest.mark.django_db
    def test_list_shows_urgency_groups(self, auth_client, project_new):
        resp = auth_client.get("/projects/?view=list")
        assert resp.status_code == 200
        content = resp.content.decode()
        # Recently created project should be in "green" group
        assert "정상 진행" in content

    @pytest.mark.django_db
    def test_old_project_in_red_group(
        self, auth_client, client_obj, user_with_org
    ):
        p = Project.objects.create(
            client=client_obj
            title="Old Project",
            status="searching",
            created_by=user_with_org)
        p.assigned_consultants.add(user_with_org)
        # Manually backdate created_at
        Project.objects.filter(pk=p.pk).update(
            created_at=timezone.now() - timedelta(days=25)
        )

        resp = auth_client.get("/projects/?view=list")
        content = resp.content.decode()
        assert "긴급" in content
        assert "Old Project" in content

    @pytest.mark.django_db
    def test_medium_project_in_yellow_group(
        self, auth_client, client_obj, user_with_org
    ):
        p = Project.objects.create(
            client=client_obj
            title="Medium Project",
            status="searching",
            created_by=user_with_org)
        p.assigned_consultants.add(user_with_org)
        # Backdate to 15 days ago (between 10 and 20)
        Project.objects.filter(pk=p.pk).update(
            created_at=timezone.now() - timedelta(days=15)
        )

        resp = auth_client.get("/projects/?view=list")
        content = resp.content.decode()
        assert "이번 주" in content
        assert "Medium Project" in content


# --- Pagination ---


class TestPagination:
    @pytest.mark.django_db
    def test_board_no_pagination(self, auth_client, project_new):
        resp = auth_client.get("/projects/?view=board")
        content = resp.content.decode()
        # Board should NOT have pagination nav
        assert "page_obj" not in content or "이전" not in content

    @pytest.mark.django_db
    def test_table_has_pagination(self, auth_client, client_obj, user_with_org):
        # Create 25 projects to exceed PAGE_SIZE=20
        for i in range(25):
            p = Project.objects.create(
                client=client_obj
                title=f"Bulk Project {i}",
                status="new",
                created_by=user_with_org)
            p.assigned_consultants.add(user_with_org)

        resp = auth_client.get("/projects/?view=table&scope=all")
        content = resp.content.decode()
        # Should show pagination
        assert "다음" in content


# --- Organization Isolation ---


class TestMultiViewOrgIsolation:
    @pytest.mark.django_db
    def test_board_org_isolation(self, auth_client, project_other_org):
        resp = auth_client.get("/projects/?view=board&scope=all")
        assert "Other Org Project" not in resp.content.decode()

    @pytest.mark.django_db
    def test_list_org_isolation(self, auth_client, project_other_org):
        resp = auth_client.get("/projects/?view=list&scope=all")
        assert "Other Org Project" not in resp.content.decode()

    @pytest.mark.django_db
    def test_table_org_isolation(self, auth_client, project_other_org):
        resp = auth_client.get("/projects/?view=table&scope=all")
        assert "Other Org Project" not in resp.content.decode()
