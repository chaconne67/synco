"""P15: Telegram view tests."""

import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client as TestClient, override_settings
from django.utils import timezone

from accounts.models import (
    Membership,
    Organization,
    TelegramBinding,
    TelegramVerification,
    User,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


@pytest.fixture
def auth_client(user):
    c = TestClient()
    c.login(username="tester", password="test1234")
    return c


@pytest.fixture
def binding(user):
    return TelegramBinding.objects.create(
        user=user, chat_id="12345", is_active=True, verified_at=timezone.now()
    )


class TestWebhookView:
    @override_settings(TELEGRAM_WEBHOOK_SECRET="testsecret")
    def test_missing_secret_returns_403(self):
        c = TestClient()
        resp = c.post(
            "/telegram/webhook/",
            data=json.dumps({"update_id": 1}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    @override_settings(TELEGRAM_WEBHOOK_SECRET="testsecret")
    def test_wrong_secret_returns_403(self):
        c = TestClient()
        resp = c.post(
            "/telegram/webhook/",
            data=json.dumps({"update_id": 1}),
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong",
        )
        assert resp.status_code == 403

    @override_settings(TELEGRAM_WEBHOOK_SECRET="testsecret")
    def test_invalid_json_returns_400(self):
        c = TestClient()
        resp = c.post(
            "/telegram/webhook/",
            data="not json",
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="testsecret",
        )
        assert resp.status_code == 400

    @override_settings(TELEGRAM_WEBHOOK_SECRET="testsecret")
    @patch("projects.views_telegram._process_update")
    def test_valid_webhook(self, mock_process):
        c = TestClient()
        resp = c.post(
            "/telegram/webhook/",
            data=json.dumps({"update_id": 123}),
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="testsecret",
        )
        assert resp.status_code == 200
        mock_process.assert_called_once()

    @override_settings(TELEGRAM_WEBHOOK_SECRET="testsecret")
    @patch("projects.views_telegram._process_update")
    def test_duplicate_update_id_skipped(self, mock_process):
        c = TestClient()
        payload = json.dumps({"update_id": 456})
        c.post(
            "/telegram/webhook/",
            data=payload,
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="testsecret",
        )
        c.post(
            "/telegram/webhook/",
            data=payload,
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="testsecret",
        )
        assert mock_process.call_count == 1


class TestBindView:
    def test_bind_get_shows_form(self, auth_client):
        resp = auth_client.get("/telegram/bind/")
        assert resp.status_code == 200

    def test_bind_post_creates_verification(self, auth_client, user):
        resp = auth_client.post("/telegram/bind/")
        assert resp.status_code == 200
        v = TelegramVerification.objects.filter(user=user, consumed=False).first()
        assert v is not None
        assert len(v.code) == 6

    def test_bind_post_invalidates_previous_codes(self, auth_client, user):
        TelegramVerification.objects.create(
            user=user,
            code="111111",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        auth_client.post("/telegram/bind/")
        old = TelegramVerification.objects.get(code="111111")
        assert old.consumed is True


class TestUnbindView:
    def test_unbind(self, auth_client, binding):
        resp = auth_client.post("/telegram/unbind/")
        assert resp.status_code == 200
        binding.refresh_from_db()
        assert binding.is_active is False

    def test_unbind_no_binding(self, auth_client):
        resp = auth_client.post("/telegram/unbind/")
        assert resp.status_code == 200


class TestTestSendView:
    @patch("projects.services.notification._send_telegram_message")
    def test_send_test_message(self, mock_send, auth_client, binding):
        mock_send.return_value = "msg_1"
        resp = auth_client.post("/telegram/test/")
        assert resp.status_code == 200
        mock_send.assert_called_once()

    def test_send_without_binding(self, auth_client):
        resp = auth_client.post("/telegram/test/")
        assert resp.status_code == 200
