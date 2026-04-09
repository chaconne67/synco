"""P15: Telegram auth tests."""

import pytest
from unittest.mock import MagicMock

from django.test import RequestFactory, override_settings

from accounts.models import Membership, Organization, TelegramBinding, User
from projects.telegram.auth import validate_webhook_secret, verify_telegram_user_access


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


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
    def test_valid_access(self, binding, org):
        from clients.models import Client

        client = Client.objects.create(name="Acme", organization=org)
        from projects.models import Project

        project = Project.objects.create(
            client=client, organization=org, title="Test", created_by=binding.user
        )
        user, user_org = verify_telegram_user_access("12345", project)
        assert user == binding.user
        assert user_org == org

    def test_unknown_chat_id(self):
        with pytest.raises(Exception):
            verify_telegram_user_access("unknown", MagicMock(organization=MagicMock()))

    def test_inactive_binding(self, binding):
        binding.is_active = False
        binding.save()
        with pytest.raises(Exception):
            verify_telegram_user_access("12345", MagicMock(organization=MagicMock()))

    def test_wrong_organization(self, binding):
        other_org = Organization.objects.create(name="Other Firm")
        mock_obj = MagicMock()
        mock_obj.organization = other_org
        with pytest.raises(Exception):
            verify_telegram_user_access("12345", mock_obj)
