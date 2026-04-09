"""P15: Notification service tests."""

import pytest
from unittest.mock import patch
from django.utils import timezone

from accounts.models import Membership, Organization, TelegramBinding, User
from projects.models import Notification
from projects.services.notification import (
    send_notification,
    send_bulk_notifications,
    update_telegram_message,
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
def binding(user):
    return TelegramBinding.objects.create(
        user=user, chat_id="12345", is_active=True, verified_at=timezone.now()
    )


@pytest.fixture
def notification(user):
    return Notification.objects.create(
        recipient=user,
        type=Notification.Type.REMINDER,
        title="Test Reminder",
        body="Test body",
    )


class TestSendNotification:
    @patch("projects.services.notification._send_telegram_message")
    def test_send_success(self, mock_send, binding, notification):
        mock_send.return_value = "msg_123"
        result = send_notification(notification)
        assert result is True
        notification.refresh_from_db()
        assert notification.status == Notification.Status.SENT
        assert notification.telegram_message_id == "msg_123"
        assert notification.telegram_chat_id == "12345"

    @patch("projects.services.notification._send_telegram_message")
    def test_send_no_binding(self, mock_send, notification):
        """No TelegramBinding → skip, return False."""
        result = send_notification(notification)
        assert result is False
        mock_send.assert_not_called()

    @patch("projects.services.notification._send_telegram_message")
    def test_send_inactive_binding(self, mock_send, user, notification):
        TelegramBinding.objects.create(user=user, chat_id="12345", is_active=False)
        result = send_notification(notification)
        assert result is False
        mock_send.assert_not_called()

    @patch("projects.services.notification._send_telegram_message")
    def test_send_api_failure(self, mock_send, binding, notification):
        mock_send.side_effect = Exception("Telegram API error")
        result = send_notification(notification)
        assert result is False
        notification.refresh_from_db()
        assert notification.status == Notification.Status.PENDING


class TestSendBulk:
    @patch("projects.services.notification._send_telegram_message")
    def test_bulk_send(self, mock_send, binding, user):
        mock_send.return_value = "msg_1"
        n1 = Notification.objects.create(
            recipient=user,
            type=Notification.Type.NEWS,
            title="News 1",
            body="Body 1",
        )
        n2 = Notification.objects.create(
            recipient=user,
            type=Notification.Type.NEWS,
            title="News 2",
            body="Body 2",
        )
        count = send_bulk_notifications([n1, n2])
        assert count == 2


class TestUpdateMessage:
    @patch("projects.services.notification._edit_telegram_message")
    def test_update_success(self, mock_edit, binding, notification):
        notification.telegram_message_id = "msg_123"
        notification.telegram_chat_id = "12345"
        notification.save()
        result = update_telegram_message(notification, "Updated text")
        assert result is True
        mock_edit.assert_called_once()

    @patch("projects.services.notification._edit_telegram_message")
    def test_update_chat_id_mismatch(self, mock_edit, user, notification):
        """Rebind scenario: chat_id changed → skip update."""
        TelegramBinding.objects.create(user=user, chat_id="99999", is_active=True)
        notification.telegram_message_id = "msg_123"
        notification.telegram_chat_id = "12345"  # Old chat_id
        notification.save()
        result = update_telegram_message(notification, "Updated text")
        assert result is False
        mock_edit.assert_not_called()

    @patch("projects.services.notification._edit_telegram_message")
    def test_update_no_message_id(self, mock_edit, binding, notification):
        """No telegram_message_id → skip."""
        result = update_telegram_message(notification, "Updated text")
        assert result is False
        mock_edit.assert_not_called()
