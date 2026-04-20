"""P15: Telegram auth tests."""

import pytest
from unittest.mock import MagicMock

from django.test import RequestFactory, override_settings

from accounts.models import TelegramBinding, User
from projects.telegram.auth import validate_webhook_secret, verify_telegram_user_access


@pytest.fixture
def user(db):
    return User.objects.create_user(username="tester", password="test1234", level=1)


@pytest.fixture
def binding(user):
    return TelegramBinding.objects.create(user=user, chat_id="12345", is_active=True)


class TestWebhookSecret:
    @override_settings(TELEGRAM_WEBHOOK_SECRET="mysecret")
    def test_valid_secret(self):
        factory = RequestFactory()
        request = factory.post(
            "/telegram/webhook/",
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="mysecret",
        )
        assert validate_webhook_secret(request) is True

    @override_settings(TELEGRAM_WEBHOOK_SECRET="mysecret")
    def test_invalid_secret(self):
        factory = RequestFactory()
        request = factory.post(
            "/telegram/webhook/",
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong",
        )
        assert validate_webhook_secret(request) is False

    @override_settings(TELEGRAM_WEBHOOK_SECRET="mysecret")
    def test_missing_secret_header(self):
        factory = RequestFactory()
        request = factory.post(
            "/telegram/webhook/",
            content_type="application/json",
        )
        assert validate_webhook_secret(request) is False

    @override_settings(TELEGRAM_WEBHOOK_SECRET="")
    def test_empty_configured_secret_rejects(self):
        factory = RequestFactory()
        request = factory.post(
            "/telegram/webhook/",
            content_type="application/json",
        )
        assert validate_webhook_secret(request) is False


class TestVerifyUserAccess:
    def test_valid_access(self, binding):
        from clients.models import Client
        from projects.models import Project

        client = Client.objects.create(name="Acme")
        project = Project.objects.create(
            client=client, title="Test", created_by=binding.user
        )
        user = verify_telegram_user_access("12345", project)
        assert user == binding.user

    def test_unknown_chat_id(self):
        with pytest.raises(Exception):
            verify_telegram_user_access("unknown", MagicMock())

    def test_inactive_binding(self, binding):
        binding.is_active = False
        binding.save()
        with pytest.raises(Exception):
            verify_telegram_user_access("12345", MagicMock())
