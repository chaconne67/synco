import pytest
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model

from accounts.models import InviteCode, Membership, Organization

User = get_user_model()


@pytest.mark.django_db
class TestInviteCode:
    def test_create_invite_code(self):
        org = Organization.objects.create(name="Test Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            max_uses=10,
        )
        assert code.code  # auto-generated
        assert len(code.code) == 8
        assert code.is_active is True
        assert code.used_count == 0

    def test_is_valid_active_code(self):
        org = Organization.objects.create(name="Test Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            max_uses=5,
        )
        assert code.is_valid is True

    def test_is_valid_expired(self):
        org = Organization.objects.create(name="Test Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        assert code.is_valid is False

    def test_is_valid_max_uses_reached(self):
        org = Organization.objects.create(name="Test Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            max_uses=1,
            used_count=1,
        )
        assert code.is_valid is False

    def test_is_valid_deactivated(self):
        org = Organization.objects.create(name="Test Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            is_active=False,
        )
        assert code.is_valid is False

    def test_use_increments_count(self):
        org = Organization.objects.create(name="Test Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            max_uses=5,
        )
        code.use()
        assert code.used_count == 1


@pytest.mark.django_db
class TestMembershipStatus:
    def test_default_status_is_active(self):
        org = Organization.objects.create(name="Test Org")
        user = User.objects.create_user(username="test", password="pass")
        m = Membership.objects.create(user=user, organization=org)
        assert m.status == "active"

    def test_pending_status(self):
        org = Organization.objects.create(name="Test Org")
        user = User.objects.create_user(username="test", password="pass")
        m = Membership.objects.create(
            user=user, organization=org, status="pending"
        )
        assert m.status == "pending"

    def test_rejected_status(self):
        org = Organization.objects.create(name="Test Org")
        user = User.objects.create_user(username="test", password="pass")
        m = Membership.objects.create(
            user=user, organization=org, status="rejected"
        )
        assert m.status == "rejected"
