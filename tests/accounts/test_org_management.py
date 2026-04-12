# tests/accounts/test_org_management.py
import pytest
from django.test import Client as TestClient
from django.contrib.auth import get_user_model

from accounts.models import InviteCode, Membership, Organization

User = get_user_model()


@pytest.fixture
def owner_setup(db):
    org = Organization.objects.create(name="Test Org")
    owner = User.objects.create_user(username="owner1", password="pass")
    Membership.objects.create(user=owner, organization=org, role="owner", status="active")
    return owner, org


@pytest.fixture
def consultant_setup(db):
    org = Organization.objects.create(name="Test Org")
    consultant = User.objects.create_user(username="cons1", password="pass")
    Membership.objects.create(user=consultant, organization=org, role="consultant", status="active")
    return consultant, org


@pytest.fixture
def cross_org_setup(db):
    """Two orgs with owners for cross-org isolation tests."""
    org_a = Organization.objects.create(name="Org A")
    owner_a = User.objects.create_user(username="owner_a", password="pass")
    Membership.objects.create(user=owner_a, organization=org_a, role="owner", status="active")

    org_b = Organization.objects.create(name="Org B")
    owner_b = User.objects.create_user(username="owner_b", password="pass")
    Membership.objects.create(user=owner_b, organization=org_b, role="owner", status="active")

    return owner_a, org_a, owner_b, org_b


@pytest.mark.django_db
class TestOrgAccessControl:
    def test_owner_can_access_org(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        response = client.get("/org/")
        assert response.status_code == 302
        assert response.url == "/org/info/"

    def test_consultant_cannot_access_org(self, consultant_setup):
        consultant, org = consultant_setup
        client = TestClient()
        client.force_login(consultant)
        response = client.get("/org/info/")
        assert response.status_code == 403

    def test_anonymous_redirects_to_login(self):
        client = TestClient()
        response = client.get("/org/info/")
        assert response.status_code == 302
        assert "login" in response.url


@pytest.mark.django_db
class TestOrgInfo:
    def test_org_info_shows_org_data(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        response = client.get("/org/info/")
        assert response.status_code == 200
        assert "Test Org" in response.content.decode()

    def test_org_info_update(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        response = client.post("/org/info/", {"name": "Updated Org"})
        assert response.status_code == 200
        org.refresh_from_db()
        assert org.name == "Updated Org"


@pytest.mark.django_db
class TestOrgMembers:
    def test_members_list(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        response = client.get("/org/members/")
        assert response.status_code == 200
        assert "owner1" in response.content.decode()

    def test_approve_pending_member(self, owner_setup):
        owner, org = owner_setup
        pending_user = User.objects.create_user(username="pending1", password="pass")
        m = Membership.objects.create(
            user=pending_user, organization=org, role="consultant", status="pending"
        )
        client = TestClient()
        client.force_login(owner)
        response = client.post(f"/org/members/{m.pk}/approve/")
        m.refresh_from_db()
        assert m.status == "active"

    def test_reject_pending_member(self, owner_setup):
        owner, org = owner_setup
        pending_user = User.objects.create_user(username="pending2", password="pass")
        m = Membership.objects.create(
            user=pending_user, organization=org, role="consultant", status="pending"
        )
        client = TestClient()
        client.force_login(owner)
        response = client.post(f"/org/members/{m.pk}/reject/")
        m.refresh_from_db()
        assert m.status == "rejected"

    def test_change_role(self, owner_setup):
        owner, org = owner_setup
        member = User.objects.create_user(username="member1", password="pass")
        m = Membership.objects.create(
            user=member, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(owner)
        response = client.post(f"/org/members/{m.pk}/role/", {"role": "viewer"})
        m.refresh_from_db()
        assert m.role == "viewer"

    def test_cannot_change_owner_role(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        m = Membership.objects.get(user=owner)
        response = client.post(f"/org/members/{m.pk}/role/", {"role": "consultant"})
        assert response.status_code == 400
        m.refresh_from_db()
        assert m.role == "owner"

    def test_remove_member(self, owner_setup):
        owner, org = owner_setup
        member = User.objects.create_user(username="rem1", password="pass")
        m = Membership.objects.create(
            user=member, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(owner)
        response = client.post(f"/org/members/{m.pk}/remove/")
        assert not Membership.objects.filter(pk=m.pk).exists()

    def test_cannot_remove_self(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        m = Membership.objects.get(user=owner)
        response = client.post(f"/org/members/{m.pk}/remove/")
        assert response.status_code == 400
        assert Membership.objects.filter(pk=m.pk).exists()


@pytest.mark.django_db
class TestOrgInvites:
    def test_invites_list(self, owner_setup):
        owner, org = owner_setup
        InviteCode.objects.create(organization=org, role="consultant", created_by=owner)
        client = TestClient()
        client.force_login(owner)
        response = client.get("/org/invites/")
        assert response.status_code == 200

    def test_create_invite_code(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        response = client.post(
            "/org/invites/create/",
            {"role": "consultant", "max_uses": "5"},
        )
        assert InviteCode.objects.filter(organization=org, created_by=owner).exists()
        code = InviteCode.objects.filter(organization=org, created_by=owner).first()
        assert code.role == "consultant"
        assert code.max_uses == 5

    def test_create_invite_invalid_form_no_success_message(self, owner_setup):
        """Invalid form should NOT show success message."""
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        response = client.post(
            "/org/invites/create/",
            {"role": "consultant", "max_uses": "0"},  # min is 1
        )
        assert not InviteCode.objects.filter(organization=org, created_by=owner).exists()
        content = response.content.decode()
        assert "생성되었습니다" not in content

    def test_deactivate_invite_code(self, owner_setup):
        owner, org = owner_setup
        code = InviteCode.objects.create(
            organization=org, role="consultant", created_by=owner
        )
        client = TestClient()
        client.force_login(owner)
        response = client.post(f"/org/invites/{code.pk}/deactivate/")
        code.refresh_from_db()
        assert code.is_active is False


@pytest.mark.django_db
class TestOrgCrossOrgIsolation:
    """Cross-org security: owner A must not be able to act on org B resources."""

    def test_cross_org_approve_blocked(self, cross_org_setup):
        owner_a, org_a, owner_b, org_b = cross_org_setup
        pending = User.objects.create_user(username="pending_b", password="pass")
        m = Membership.objects.create(
            user=pending, organization=org_b, role="consultant", status="pending"
        )
        client = TestClient()
        client.force_login(owner_a)
        response = client.post(f"/org/members/{m.pk}/approve/")
        assert response.status_code == 404
        m.refresh_from_db()
        assert m.status == "pending"

    def test_cross_org_role_change_blocked(self, cross_org_setup):
        owner_a, org_a, owner_b, org_b = cross_org_setup
        member_b = User.objects.create_user(username="member_b", password="pass")
        m = Membership.objects.create(
            user=member_b, organization=org_b, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(owner_a)
        response = client.post(f"/org/members/{m.pk}/role/", {"role": "viewer"})
        assert response.status_code == 404
        m.refresh_from_db()
        assert m.role == "consultant"

    def test_cross_org_remove_blocked(self, cross_org_setup):
        owner_a, org_a, owner_b, org_b = cross_org_setup
        member_b = User.objects.create_user(username="rem_b", password="pass")
        m = Membership.objects.create(
            user=member_b, organization=org_b, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(owner_a)
        response = client.post(f"/org/members/{m.pk}/remove/")
        assert response.status_code == 404
        assert Membership.objects.filter(pk=m.pk).exists()

    def test_cross_org_invite_deactivate_blocked(self, cross_org_setup):
        owner_a, org_a, owner_b, org_b = cross_org_setup
        code = InviteCode.objects.create(
            organization=org_b, role="consultant", created_by=owner_b
        )
        client = TestClient()
        client.force_login(owner_a)
        response = client.post(f"/org/invites/{code.pk}/deactivate/")
        assert response.status_code == 404
        code.refresh_from_db()
        assert code.is_active is True
