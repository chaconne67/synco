"""P03: Project CRUD view tests.

Tests for Project CRUD, Organization isolation, login_required,
scope/client/status filters, sorting, created_by auto-set,
assigned_consultants auto-add, JD file upload, delete protection,
and days_elapsed property.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as TestClient

from accounts.models import Membership, Organization, User
from clients.models import Client
from projects.models import Contact, Project, Submission


# --- Fixtures ---


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def org2(db):
    return Organization.objects.create(name="Other Firm")


@pytest.fixture
def user_with_org(db, org):
    user = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=user, organization=org)
    return user


@pytest.fixture
def user2_with_org(db, org):
    """Second user in same org."""
    user = User.objects.create_user(username="tester_same_org", password="test1234")
    Membership.objects.create(user=user, organization=org)
    return user


@pytest.fixture
def user_with_org2(db, org2):
    user = User.objects.create_user(username="tester2", password="test1234")
    Membership.objects.create(user=user, organization=org2)
    return user


@pytest.fixture
def auth_client(user_with_org):
    c = TestClient()
    c.login(username="tester", password="test1234")
    return c


@pytest.fixture
def auth_client2(user_with_org2):
    c = TestClient()
    c.login(username="tester2", password="test1234")
    return c


@pytest.fixture
def client_obj(org):
    return Client.objects.create(
        name="Acme Corp",
        industry="IT",
        organization=org,
    )


@pytest.fixture
def client_obj2(org2):
    return Client.objects.create(
        name="Other Corp",
        industry="Finance",
        organization=org2,
    )


@pytest.fixture
def project_obj(org, client_obj, user_with_org):
    p = Project.objects.create(
        client=client_obj,
        organization=org,
        title="Dev Hire",
        status="searching",
        created_by=user_with_org,
    )
    p.assigned_consultants.add(user_with_org)
    return p


@pytest.fixture
def project_obj2(org2, client_obj2, user_with_org2):
    return Project.objects.create(
        client=client_obj2,
        organization=org2,
        title="Other Project",
        status="new",
        created_by=user_with_org2,
    )


# --- Login Required ---


class TestLoginRequired:
    @pytest.mark.django_db
    def test_list_requires_login(self):
        c = TestClient()
        resp = c.get("/projects/")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    @pytest.mark.django_db
    def test_create_requires_login(self):
        c = TestClient()
        resp = c.get("/projects/new/")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    @pytest.mark.django_db
    def test_detail_requires_login(self, project_obj):
        c = TestClient()
        resp = c.get(f"/projects/{project_obj.pk}/")
        assert resp.status_code == 302

    @pytest.mark.django_db
    def test_update_requires_login(self, project_obj):
        c = TestClient()
        resp = c.get(f"/projects/{project_obj.pk}/edit/")
        assert resp.status_code == 302

    @pytest.mark.django_db
    def test_delete_requires_login(self, project_obj):
        c = TestClient()
        resp = c.post(f"/projects/{project_obj.pk}/delete/")
        assert resp.status_code == 302


# --- Project CRUD ---


class TestProjectCRUD:
    @pytest.mark.django_db
    def test_list_page_renders(self, auth_client):
        resp = auth_client.get("/projects/")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_list_shows_own_projects(self, auth_client, project_obj):
        resp = auth_client.get("/projects/")
        assert resp.status_code == 200
        assert "Dev Hire" in resp.content.decode()

    @pytest.mark.django_db
    def test_create_project(self, auth_client, org, client_obj, user_with_org):
        resp = auth_client.post(
            "/projects/new/",
            {
                "client": str(client_obj.pk),
                "title": "New Project",
                "jd_text": "Looking for engineers",
                "status": "new",
            },
        )
        assert resp.status_code == 302  # redirect to detail
        project = Project.objects.get(title="New Project")
        assert project.organization == org
        assert project.created_by == user_with_org

    @pytest.mark.django_db
    def test_create_project_assigns_creator_as_consultant(
        self, auth_client, client_obj, user_with_org
    ):
        auth_client.post(
            "/projects/new/",
            {
                "client": str(client_obj.pk),
                "title": "Auto Assign Test",
                "status": "new",
            },
        )
        project = Project.objects.get(title="Auto Assign Test")
        assert user_with_org in project.assigned_consultants.all()

    @pytest.mark.django_db
    def test_detail_page_renders(self, auth_client, project_obj):
        resp = auth_client.get(f"/projects/{project_obj.pk}/")
        assert resp.status_code == 200
        assert "Dev Hire" in resp.content.decode()

    @pytest.mark.django_db
    def test_update_project(self, auth_client, project_obj, client_obj):
        resp = auth_client.post(
            f"/projects/{project_obj.pk}/edit/",
            {
                "client": str(client_obj.pk),
                "title": "Updated Title",
                "status": "interviewing",
            },
        )
        assert resp.status_code == 302
        project_obj.refresh_from_db()
        assert project_obj.title == "Updated Title"
        assert project_obj.status == "interviewing"

    @pytest.mark.django_db
    def test_delete_project(self, auth_client, project_obj):
        pk = project_obj.pk
        resp = auth_client.post(f"/projects/{pk}/delete/")
        assert resp.status_code == 302
        assert not Project.objects.filter(pk=pk).exists()

    @pytest.mark.django_db
    def test_delete_only_post(self, auth_client, project_obj):
        resp = auth_client.get(f"/projects/{project_obj.pk}/delete/")
        assert resp.status_code == 405

    @pytest.mark.django_db
    def test_create_form_renders(self, auth_client):
        resp = auth_client.get("/projects/new/")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_update_form_renders(self, auth_client, project_obj):
        resp = auth_client.get(f"/projects/{project_obj.pk}/edit/")
        assert resp.status_code == 200


# --- Organization Isolation ---


class TestOrganizationIsolation:
    @pytest.mark.django_db
    def test_cannot_see_other_org_projects(self, auth_client, project_obj2):
        resp = auth_client.get("/projects/?scope=all")
        assert "Other Project" not in resp.content.decode()

    @pytest.mark.django_db
    def test_cannot_access_other_org_project_detail(self, auth_client, project_obj2):
        resp = auth_client.get(f"/projects/{project_obj2.pk}/")
        assert resp.status_code == 404

    @pytest.mark.django_db
    def test_cannot_update_other_org_project(self, auth_client, project_obj2):
        resp = auth_client.post(
            f"/projects/{project_obj2.pk}/edit/",
            {"title": "Hacked"},
        )
        assert resp.status_code == 404

    @pytest.mark.django_db
    def test_cannot_delete_other_org_project(self, auth_client, project_obj2):
        resp = auth_client.post(f"/projects/{project_obj2.pk}/delete/")
        assert resp.status_code == 404


# --- Scope Filter ---


class TestScopeFilter:
    @pytest.mark.django_db
    def test_scope_mine_shows_assigned_projects(self, auth_client, project_obj):
        resp = auth_client.get("/projects/?scope=mine")
        assert "Dev Hire" in resp.content.decode()

    @pytest.mark.django_db
    def test_scope_mine_hides_unassigned_projects(
        self, auth_client, org, client_obj, user2_with_org
    ):
        """Project created by another user, not assigned to current user."""
        other_project = Project.objects.create(
            client=client_obj,
            organization=org,
            title="Not My Project",
            status="new",
            created_by=user2_with_org,
        )
        other_project.assigned_consultants.add(user2_with_org)

        resp = auth_client.get("/projects/?scope=mine")
        assert "Not My Project" not in resp.content.decode()

    @pytest.mark.django_db
    def test_scope_all_shows_all_org_projects(
        self, auth_client, project_obj, org, client_obj, user2_with_org
    ):
        other_project = Project.objects.create(
            client=client_obj,
            organization=org,
            title="Other User Project",
            status="new",
            created_by=user2_with_org,
        )
        other_project.assigned_consultants.add(user2_with_org)

        resp = auth_client.get("/projects/?scope=all")
        content = resp.content.decode()
        assert "Dev Hire" in content
        assert "Other User Project" in content

    @pytest.mark.django_db
    def test_scope_mine_includes_created_by_user(
        self, auth_client, org, client_obj, user_with_org
    ):
        """scope=mine should include projects created by user even if not assigned."""
        Project.objects.create(
            client=client_obj,
            organization=org,
            title="Created Not Assigned",
            status="new",
            created_by=user_with_org,
        )
        # Not adding to assigned_consultants

        resp = auth_client.get("/projects/?scope=mine")
        assert "Created Not Assigned" in resp.content.decode()


# --- Client/Status Filter ---


class TestFilters:
    @pytest.mark.django_db
    def test_filter_by_client(self, auth_client, project_obj, org, user_with_org):
        other_client = Client.objects.create(name="Other Client", organization=org)
        other_project = Project.objects.create(
            client=other_client,
            organization=org,
            title="Other Client Project",
            status="new",
            created_by=user_with_org,
        )
        other_project.assigned_consultants.add(user_with_org)

        resp = auth_client.get(f"/projects/?scope=mine&client={project_obj.client.pk}")
        content = resp.content.decode()
        assert "Dev Hire" in content
        assert "Other Client Project" not in content

    @pytest.mark.django_db
    def test_filter_by_status(
        self, auth_client, project_obj, org, client_obj, user_with_org
    ):
        new_project = Project.objects.create(
            client=client_obj,
            organization=org,
            title="New Project",
            status="new",
            created_by=user_with_org,
        )
        new_project.assigned_consultants.add(user_with_org)

        resp = auth_client.get("/projects/?scope=mine&status=new")
        content = resp.content.decode()
        assert "New Project" in content
        assert "Dev Hire" not in content  # status=searching, not new


# --- Sorting ---


class TestSorting:
    @pytest.mark.django_db
    def test_sort_days_desc(self, auth_client, org, client_obj, user_with_org):
        """days_desc = most elapsed days first = oldest created_at first."""
        p1 = Project.objects.create(
            client=client_obj,
            organization=org,
            title="Project A",
            status="new",
            created_by=user_with_org,
        )
        p1.assigned_consultants.add(user_with_org)
        p2 = Project.objects.create(
            client=client_obj,
            organization=org,
            title="Project B",
            status="new",
            created_by=user_with_org,
        )
        p2.assigned_consultants.add(user_with_org)

        resp = auth_client.get("/projects/?scope=mine&sort=days_desc")
        content = resp.content.decode()
        pos_a = content.find("Project A")
        pos_b = content.find("Project B")
        # A was created first, so more elapsed days, should appear first
        assert pos_a < pos_b

    @pytest.mark.django_db
    def test_sort_days_asc(self, auth_client, org, client_obj, user_with_org):
        """days_asc = least elapsed days first = newest created_at first."""
        p1 = Project.objects.create(
            client=client_obj,
            organization=org,
            title="Project A",
            status="new",
            created_by=user_with_org,
        )
        p1.assigned_consultants.add(user_with_org)
        p2 = Project.objects.create(
            client=client_obj,
            organization=org,
            title="Project B",
            status="new",
            created_by=user_with_org,
        )
        p2.assigned_consultants.add(user_with_org)

        resp = auth_client.get("/projects/?scope=mine&sort=days_asc")
        content = resp.content.decode()
        pos_a = content.find("Project A")
        pos_b = content.find("Project B")
        # B was created second (newer), so fewer elapsed days, should appear first
        assert pos_b < pos_a


# --- JD File Upload ---


class TestJDFileUpload:
    @pytest.mark.django_db
    def test_create_with_jd_file(self, auth_client, client_obj, settings, tmp_path):
        settings.STORAGES = {
            **settings.STORAGES,
            "default": {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
                "OPTIONS": {"location": str(tmp_path)},
            },
        }
        jd_file = SimpleUploadedFile(
            "job_description.pdf",
            b"fake pdf content",
            content_type="application/pdf",
        )
        resp = auth_client.post(
            "/projects/new/",
            {
                "client": str(client_obj.pk),
                "title": "JD Upload Test",
                "status": "new",
                "jd_file": jd_file,
            },
        )
        assert resp.status_code == 302
        project = Project.objects.get(title="JD Upload Test")
        assert project.jd_file
        assert "job_description" in project.jd_file.name


# --- Delete Protection ---


class TestDeleteProtection:
    @pytest.mark.django_db
    def test_cannot_delete_with_contacts(self, auth_client, project_obj, user_with_org):
        from django.utils import timezone

        from candidates.models import Candidate

        candidate = Candidate.objects.create(
            name="Test Candidate",
        )
        Contact.objects.create(
            project=project_obj,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )

        resp = auth_client.post(f"/projects/{project_obj.pk}/delete/")
        assert resp.status_code == 200
        assert Project.objects.filter(pk=project_obj.pk).exists()
        assert "컨택 또는 제출 이력이 있어 삭제할 수 없습니다" in resp.content.decode()

    @pytest.mark.django_db
    def test_cannot_delete_with_submissions(
        self, auth_client, project_obj, user_with_org
    ):
        from candidates.models import Candidate

        candidate = Candidate.objects.create(
            name="Test Candidate",
        )
        Submission.objects.create(
            project=project_obj,
            candidate=candidate,
            consultant=user_with_org,
        )

        resp = auth_client.post(f"/projects/{project_obj.pk}/delete/")
        assert resp.status_code == 200
        assert Project.objects.filter(pk=project_obj.pk).exists()
        assert "컨택 또는 제출 이력이 있어 삭제할 수 없습니다" in resp.content.decode()

    @pytest.mark.django_db
    def test_can_delete_without_related_data(self, auth_client, project_obj):
        pk = project_obj.pk
        resp = auth_client.post(f"/projects/{pk}/delete/")
        assert resp.status_code == 302
        assert not Project.objects.filter(pk=pk).exists()


# --- Days Elapsed ---


class TestDaysElapsed:
    @pytest.mark.django_db
    def test_days_elapsed_property(self, project_obj):
        # Project was just created, so days_elapsed should be 0
        assert project_obj.days_elapsed == 0

    @pytest.mark.django_db
    def test_days_elapsed_shown_in_list(self, auth_client, project_obj):
        resp = auth_client.get("/projects/")
        content = resp.content.decode()
        assert "0일 경과" in content

    @pytest.mark.django_db
    def test_days_elapsed_shown_in_detail(self, auth_client, project_obj):
        resp = auth_client.get(f"/projects/{project_obj.pk}/")
        content = resp.content.decode()
        assert "0일" in content


# --- HTMX Navigation ---


class TestHTMXNavigation:
    @pytest.mark.django_db
    def test_list_htmx_renders_partial(self, auth_client):
        resp = auth_client.get(
            "/projects/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "<!DOCTYPE" not in content

    @pytest.mark.django_db
    def test_list_full_page_renders(self, auth_client):
        resp = auth_client.get("/projects/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "<!DOCTYPE" in content
