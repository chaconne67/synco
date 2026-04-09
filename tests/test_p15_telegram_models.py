"""P15: Telegram model tests."""

import pytest
from datetime import timedelta
from django.utils import timezone

from accounts.models import Membership, Organization, TelegramBinding, TelegramVerification, User
from projects.models import Notification


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


class TestTelegramBinding:
    def test_verified_at_field_exists(self, user):
        binding = TelegramBinding.objects.create(
            user=user, chat_id="123456", is_active=True, verified_at=timezone.now()
        )
        binding.refresh_from_db()
        assert binding.verified_at is not None

    def test_verified_at_nullable(self, user):
        binding = TelegramBinding.objects.create(
            user=user, chat_id="123456", is_active=True
        )
        binding.refresh_from_db()
        assert binding.verified_at is None


class TestTelegramVerification:
    def test_create_verification(self, user):
        v = TelegramVerification.objects.create(
            user=user,
            code="123456",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        assert v.consumed is False
        assert v.attempts == 0

    def test_expired_verification(self, user):
        v = TelegramVerification.objects.create(
            user=user,
            code="123456",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        assert v.is_expired is True

    def test_valid_verification(self, user):
        v = TelegramVerification.objects.create(
            user=user,
            code="123456",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        assert v.is_expired is False

    def test_consumed_is_expired(self, user):
        v = TelegramVerification.objects.create(
            user=user,
            code="123456",
            expires_at=timezone.now() + timedelta(minutes=5),
            consumed=True,
        )
        assert v.is_expired is True

    def test_max_attempts_exceeded(self, user):
        v = TelegramVerification.objects.create(
            user=user,
            code="123456",
            expires_at=timezone.now() + timedelta(minutes=5),
            attempts=5,
        )
        assert v.is_blocked is True

    def test_str(self, user):
        v = TelegramVerification.objects.create(
            user=user,
            code="123456",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        assert "123456" in str(v)


class TestNotificationChatId:
    def test_telegram_chat_id_field(self, user):
        n = Notification.objects.create(
            recipient=user,
            type=Notification.Type.REMINDER,
            title="Test",
            body="Test body",
            telegram_chat_id="999888",
        )
        n.refresh_from_db()
        assert n.telegram_chat_id == "999888"

    def test_telegram_chat_id_blank_default(self, user):
        n = Notification.objects.create(
            recipient=user,
            type=Notification.Type.REMINDER,
            title="Test",
            body="Test body",
        )
        n.refresh_from_db()
        assert n.telegram_chat_id == ""
