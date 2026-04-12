import pytest
from django.test import Client as TestClient
from django.contrib.auth import get_user_model

from accounts.models import InviteCode, Membership, Organization

User = get_user_model()


@pytest.mark.django_db
class TestInviteCodeView:
    def test_no_membership_shows_invite_page(self):
        user = User.objects.create_user(username="new", password="pass")
        client = TestClient()
        client.force_login(user)

        response = client.get("/accounts/invite/")
        assert response.status_code == 200
        assert "초대코드" in response.content.decode()

    def test_valid_owner_code_creates_active_membership(self):
        org = Organization.objects.create(name="Org")
        code = InviteCode.objects.create(organization=org, role="owner", max_uses=1)
        user = User.objects.create_user(username="boss", password="pass")
        client = TestClient()
        client.force_login(user)

        client.post("/accounts/invite/", {"code": code.code}, follow=True)
        membership = Membership.objects.get(user=user)
        assert membership.status == "active"
        assert membership.role == "owner"
        code.refresh_from_db()
        assert code.used_count == 1

    def test_valid_consultant_code_creates_pending_membership(self):
        org = Organization.objects.create(name="Org")
        code = InviteCode.objects.create(
            organization=org, role="consultant", max_uses=10
        )
        user = User.objects.create_user(username="emp", password="pass")
        client = TestClient()
        client.force_login(user)

        client.post("/accounts/invite/", {"code": code.code}, follow=True)
        membership = Membership.objects.get(user=user)
        assert membership.status == "pending"
        assert membership.role == "consultant"

    def test_invalid_code_shows_error(self):
        user = User.objects.create_user(username="bad", password="pass")
        client = TestClient()
        client.force_login(user)

        response = client.post("/accounts/invite/", {"code": "INVALID1"})
        assert response.status_code == 200
        assert "유효하지 않은" in response.content.decode()

    def test_expired_code_shows_error(self):
        from datetime import timedelta
        from django.utils import timezone

        org = Organization.objects.create(name="Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        user = User.objects.create_user(username="late", password="pass")
        client = TestClient()
        client.force_login(user)

        response = client.post("/accounts/invite/", {"code": code.code})
        assert response.status_code == 200
        assert "유효하지 않은" in response.content.decode()

    def test_pending_user_redirected_from_invite(self):
        """pending 사용자가 /accounts/invite/에 접근하면 승인대기로 리다이렉트."""
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="pend_inv", password="pass")
        Membership.objects.create(
            user=user, organization=org, status="pending", role="consultant"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/accounts/invite/")
        assert response.status_code == 302
        assert "pending" in response.url


@pytest.mark.django_db
class TestPendingApprovalView:
    def test_pending_user_sees_waiting_page(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="wait", password="pass")
        Membership.objects.create(user=user, organization=org, status="pending")
        client = TestClient()
        client.force_login(user)

        response = client.get("/accounts/pending/")
        assert response.status_code == 200
        assert "승인" in response.content.decode()

    def test_active_user_redirects_to_dashboard(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="active", password="pass")
        Membership.objects.create(user=user, organization=org, status="active")
        client = TestClient()
        client.force_login(user)

        response = client.get("/accounts/pending/")
        assert response.status_code == 302


@pytest.mark.django_db
class TestRejectedView:
    def test_rejected_user_sees_rejection_page(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="rej", password="pass")
        Membership.objects.create(user=user, organization=org, status="rejected")
        client = TestClient()
        client.force_login(user)

        response = client.get("/accounts/rejected/")
        assert response.status_code == 200
        assert "거절" in response.content.decode()

    def test_active_user_redirects_from_rejected(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="act2", password="pass")
        Membership.objects.create(user=user, organization=org, status="active")
        client = TestClient()
        client.force_login(user)

        response = client.get("/accounts/rejected/")
        assert response.status_code == 302


@pytest.mark.django_db
class TestHomeRedirection:
    def test_no_membership_redirects_to_invite(self):
        user = User.objects.create_user(username="nomem", password="pass")
        client = TestClient()
        client.force_login(user)

        response = client.get("/")
        assert response.status_code == 302
        assert "invite" in response.url

    def test_pending_redirects_to_pending(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="pend", password="pass")
        Membership.objects.create(user=user, organization=org, status="pending")
        client = TestClient()
        client.force_login(user)

        response = client.get("/")
        assert response.status_code == 302
        assert "pending" in response.url

    def test_rejected_redirects_to_rejected(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="rej2", password="pass")
        Membership.objects.create(user=user, organization=org, status="rejected")
        client = TestClient()
        client.force_login(user)

        response = client.get("/")
        assert response.status_code == 302
        assert "rejected" in response.url
