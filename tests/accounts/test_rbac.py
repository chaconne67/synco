import pytest
from django.test import RequestFactory, Client as TestClient
from django.contrib.auth import get_user_model
from django.http import HttpResponse

from accounts.decorators import role_required, membership_required
from accounts.models import Membership, Organization

User = get_user_model()


def dummy_view(request):
    return HttpResponse("OK")


@pytest.mark.django_db
class TestMembershipRequired:
    def test_active_member_passes(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="u1", password="p")
        Membership.objects.create(user=user, organization=org, status="active")

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        view = membership_required(dummy_view)
        response = view(request)
        assert response.status_code == 200

    def test_pending_member_redirects(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="u2", password="p")
        Membership.objects.create(user=user, organization=org, status="pending")

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        view = membership_required(dummy_view)
        response = view(request)
        assert response.status_code == 302
        assert "pending" in response.url

    def test_rejected_member_redirects(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="u2r", password="p")
        Membership.objects.create(user=user, organization=org, status="rejected")

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        view = membership_required(dummy_view)
        response = view(request)
        assert response.status_code == 302
        assert "rejected" in response.url

    def test_no_membership_redirects(self):
        user = User.objects.create_user(username="u3", password="p")

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        view = membership_required(dummy_view)
        response = view(request)
        assert response.status_code == 302
        assert "invite" in response.url


@pytest.mark.django_db
class TestRoleRequired:
    def test_owner_passes_owner_required(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="u4", password="p")
        Membership.objects.create(
            user=user, organization=org, role="owner", status="active"
        )

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        view = role_required("owner")(dummy_view)
        response = view(request)
        assert response.status_code == 200

    def test_consultant_blocked_from_owner_required(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="u5", password="p")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        view = role_required("owner")(dummy_view)
        response = view(request)
        assert response.status_code == 403


@pytest.mark.django_db
class TestViewPermissions:
    """Route-level integration tests for RBAC decorators."""

    def test_consultant_cannot_create_client(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/clients/new/")
        assert response.status_code == 403

    def test_owner_can_create_client(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="own", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="owner", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/clients/new/")
        assert response.status_code == 200

    def test_consultant_cannot_create_project(self):
        """Consultant CAN access project_create (approval workflow needs it)."""
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con2", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/projects/new/")
        # project_create uses @membership_required (not owner-only)
        # because P11 approval workflow requires consultant access
        assert response.status_code == 200

    def test_consultant_can_read_client_list(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con3", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/clients/")
        assert response.status_code == 200

    def test_consultant_cannot_delete_project(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con4", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        # Use a valid UUID format — role_required runs before view body
        response = client.post("/projects/00000000-0000-0000-0000-000000000000/delete/")
        assert response.status_code == 403

    def test_consultant_cannot_access_approval_queue(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con5", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/projects/approvals/")
        assert response.status_code == 403

    def test_no_membership_redirects_to_invite(self):
        user = User.objects.create_user(username="nomem", password="pass")
        client = TestClient()
        client.force_login(user)

        response = client.get("/clients/")
        assert response.status_code == 302
        assert "/accounts/invite/" in response.url

    def test_consultant_cannot_access_dashboard_team(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con6", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/dashboard/team/")
        assert response.status_code == 403

    def test_consultant_can_access_dashboard_actions(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con7", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/dashboard/actions/")
        assert response.status_code == 200


from clients.models import Client
from projects.models import Project, ProjectStatus


@pytest.mark.django_db
class TestProjectFiltering:
    @pytest.mark.parametrize("role", ["consultant", "viewer"])
    def test_non_owner_sees_only_assigned_projects(self, role):
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username=f"owner_{role}", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        user = User.objects.create_user(username=f"user_{role}", password="p")
        Membership.objects.create(
            user=user, organization=org, role=role, status="active"
        )
        client_co = Client.objects.create(name="Client", organization=org)

        # Project assigned to user
        p1 = Project.objects.create(
            title="Assigned",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )
        p1.assigned_consultants.add(user)

        # Project NOT assigned but created_by user (should NOT be visible)
        Project.objects.create(
            title="Created But Not Assigned",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=user,
        )

        # Project NOT assigned at all
        Project.objects.create(
            title="Not Assigned",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )

        test_client = TestClient()
        test_client.force_login(user)

        # Test with scope=all (the real behavioral change)
        response = test_client.get("/projects/?scope=all")
        content = response.content.decode()
        assert "Assigned" in content
        assert "Created But Not Assigned" not in content
        assert "Not Assigned" not in content

    def test_owner_sees_all_projects(self):
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="owner2", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        other = User.objects.create_user(username="other2", password="p")
        Membership.objects.create(
            user=other, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Client", organization=org)

        # Project created by owner
        Project.objects.create(
            title="Owner Project",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )

        # Project created by another user, assigned to another user
        p2 = Project.objects.create(
            title="Other Project",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=other,
        )
        p2.assigned_consultants.add(other)

        test_client = TestClient()
        test_client.force_login(owner)

        # Owner should see all projects with scope=all
        response = test_client.get("/projects/?scope=all")
        content = response.content.decode()
        assert "Owner Project" in content
        assert "Other Project" in content


@pytest.mark.django_db
class TestNavFiltering:
    """Test role-based navigation menu filtering."""

    def test_owner_sees_reference_in_sidebar(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="own_nav", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="owner", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/", follow=True)
        content = response.content.decode()
        assert "레퍼런스" in content

    def test_consultant_does_not_see_reference_in_sidebar(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con_nav", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/", follow=True)
        content = response.content.decode()
        assert "레퍼런스" not in content

    def test_sidebar_does_not_contain_old_approval_label(self):
        """Sidebar uses '프로젝트 승인' (not '승인 요청')."""
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="own_appr", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="owner", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/", follow=True)
        content = response.content.decode()
        # Extract sidebar nav section only (dash_admin.html also contains "승인 요청")
        sidebar_start = content.find('id="sidebar-nav"')
        sidebar_end = content.find("</nav>", sidebar_start)
        sidebar = content[sidebar_start:sidebar_end]
        assert "승인 요청" not in sidebar

    def test_consultant_does_not_see_approval_menu(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con_appr", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/", follow=True)
        content = response.content.decode()
        assert "프로젝트 승인" not in content
        assert "승인 요청" not in content


@pytest.mark.django_db
class TestProjectConsultantAssignment:
    def test_owner_can_assign_consultants_on_create(self):
        """Owner selects specific consultants during project creation."""
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="own_a8", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        con = User.objects.create_user(username="con_a8", password="p")
        Membership.objects.create(
            user=con, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Co8", organization=org)

        test_client = TestClient()
        test_client.force_login(owner)

        response = test_client.post("/projects/new/", {
            "title": "Assigned Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
            "assigned_consultants": [str(con.pk)],
        }, follow=True)
        assert response.status_code == 200
        project = Project.objects.get(title="Assigned Project")
        assert con in project.assigned_consultants.all()
        # Owner should NOT be auto-added when explicit selection exists
        assert project.assigned_consultants.count() == 1

    def test_no_consultants_defaults_to_creator(self):
        """No consultants selected => creator becomes default assignee."""
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="own_b8", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        client_co = Client.objects.create(name="Co8b", organization=org)

        test_client = TestClient()
        test_client.force_login(owner)

        response = test_client.post("/projects/new/", {
            "title": "Solo Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
        }, follow=True)
        assert response.status_code == 200
        project = Project.objects.get(title="Solo Project")
        assert owner in project.assigned_consultants.all()

    def test_consultant_can_create_with_self_assigned(self):
        """Consultant creates project (via approval workflow) and gets default assignment."""
        org = Organization.objects.create(name="Org")
        con = User.objects.create_user(username="con_c8", password="p")
        Membership.objects.create(
            user=con, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Co8c", organization=org)

        test_client = TestClient()
        test_client.force_login(con)

        response = test_client.post("/projects/new/", {
            "title": "Consultant Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
        }, follow=True)
        assert response.status_code == 200
        project = Project.objects.get(title="Consultant Project")
        assert con in project.assigned_consultants.all()

    def test_update_changes_assigned_consultants(self):
        """Owner can change assigned consultants on update."""
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="own_d8", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        con1 = User.objects.create_user(username="con_d8a", password="p")
        Membership.objects.create(
            user=con1, organization=org, role="consultant", status="active"
        )
        con2 = User.objects.create_user(username="con_d8b", password="p")
        Membership.objects.create(
            user=con2, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Co8d", organization=org)
        project = Project.objects.create(
            title="Update Test",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )
        project.assigned_consultants.add(con1)

        test_client = TestClient()
        test_client.force_login(owner)

        response = test_client.post(f"/projects/{project.pk}/edit/", {
            "title": "Update Test",
            "client": str(client_co.pk),
            "jd_text": "Updated JD",
            "assigned_consultants": [str(con2.pk)],
        }, follow=True)
        assert response.status_code == 200
        project.refresh_from_db()
        assert con2 in project.assigned_consultants.all()
        assert con1 not in project.assigned_consultants.all()

    def test_cross_org_user_rejected_on_create(self):
        """Submitting a user PK from another org is rejected by form validation."""
        org1 = Organization.objects.create(name="Org1")
        org2 = Organization.objects.create(name="Org2")
        owner = User.objects.create_user(username="own_e8", password="p")
        Membership.objects.create(
            user=owner, organization=org1, role="owner", status="active"
        )
        alien = User.objects.create_user(username="alien_e8", password="p")
        Membership.objects.create(
            user=alien, organization=org2, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Co8e", organization=org1)

        test_client = TestClient()
        test_client.force_login(owner)

        test_client.post("/projects/new/", {
            "title": "Cross Org Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
            "assigned_consultants": [str(alien.pk)],
        })
        # Form should be invalid — cross-org PK not in queryset
        assert not Project.objects.filter(title="Cross Org Project").exists()

    def test_update_can_clear_all_consultants(self):
        """Clearing all consultants on update is allowed (no default fallback)."""
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="own_f8", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        con = User.objects.create_user(username="con_f8", password="p")
        Membership.objects.create(
            user=con, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Co8f", organization=org)
        project = Project.objects.create(
            title="Clear Test",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )
        project.assigned_consultants.add(con)

        test_client = TestClient()
        test_client.force_login(owner)

        # POST without assigned_consultants field => M2M cleared
        response = test_client.post(f"/projects/{project.pk}/edit/", {
            "title": "Clear Test",
            "client": str(client_co.pk),
            "jd_text": "Updated JD",
        }, follow=True)
        assert response.status_code == 200
        project.refresh_from_db()
        assert project.assigned_consultants.count() == 0
