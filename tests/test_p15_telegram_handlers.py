"""P15: Telegram callback handler tests."""

import uuid
import pytest
from unittest.mock import patch

from accounts.models import Membership, Organization, TelegramBinding, User
from clients.models import Client
from projects.models import (
    Contact,
    Notification,
    Project,
    ProjectApproval,
)
from projects.telegram.handlers import (
    handle_approval_callback,
    handle_contact_callback,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user_owner(db, org):
    u = User.objects.create_user(username="owner", password="test1234")
    Membership.objects.create(user=u, organization=org, role="owner")
    return u


@pytest.fixture
def user_consultant(db, org):
    u = User.objects.create_user(username="consultant", password="test1234")
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


@pytest.fixture
def binding(user_owner):
    return TelegramBinding.objects.create(
        user=user_owner, chat_id="12345", is_active=True
    )


@pytest.fixture
def client_obj(org):
    return Client.objects.create(name="Acme Corp", organization=org)


@pytest.fixture
def project(org, client_obj, user_consultant):
    return Project.objects.create(
        client=client_obj,
        organization=org,
        title="Test Position",
        created_by=user_consultant,
    )


@pytest.fixture
def pending_approval(project, user_consultant, user_owner):
    return ProjectApproval.objects.create(
        project=project,
        requested_by=user_consultant,
        conflict_project=None,
    )


class TestApprovalCallback:
    @patch("projects.telegram.handlers._update_notification_message")
    def test_approve_action(self, mock_update, binding, pending_approval, user_owner):
        notif = Notification.objects.create(
            recipient=user_owner,
            type=Notification.Type.APPROVAL_REQUEST,
            title="Approval",
            body="Test",
            callback_data={
                "action": "approval",
                "approval_id": str(pending_approval.pk),
            },
        )
        result = handle_approval_callback(
            notification=notif,
            action="approve",
            user=user_owner,
        )
        assert result["ok"] is True
        pending_approval.refresh_from_db()
        assert pending_approval.status == ProjectApproval.Status.APPROVED

    @patch("projects.telegram.handlers._update_notification_message")
    def test_reject_action(self, mock_update, binding, pending_approval, user_owner):
        notif = Notification.objects.create(
            recipient=user_owner,
            type=Notification.Type.APPROVAL_REQUEST,
            title="Approval",
            body="Test",
            callback_data={
                "action": "approval",
                "approval_id": str(pending_approval.pk),
            },
        )
        result = handle_approval_callback(
            notification=notif,
            action="reject",
            user=user_owner,
        )
        assert result["ok"] is True

    @patch("projects.telegram.handlers._update_notification_message")
    def test_invalid_approval_id(self, mock_update, user_owner):
        notif = Notification.objects.create(
            recipient=user_owner,
            type=Notification.Type.APPROVAL_REQUEST,
            title="Approval",
            body="Test",
            callback_data={"action": "approval", "approval_id": str(uuid.uuid4())},
        )
        result = handle_approval_callback(
            notification=notif,
            action="approve",
            user=user_owner,
        )
        assert result["ok"] is False


class TestContactCallback:
    @patch("projects.telegram.handlers._send_next_step")
    def test_channel_selection(self, mock_send, binding, user_owner, project):
        from candidates.models import Candidate

        candidate = Candidate.objects.create(
            name="홍길동", owned_by=binding.user.membership.organization
        )
        notif = Notification.objects.create(
            recipient=user_owner,
            type=Notification.Type.AUTO_GENERATED,
            title="Contact",
            body="Test",
            callback_data={
                "action": "contact_record",
                "step": 1,
                "project_id": str(project.pk),
                "candidate_id": str(candidate.pk),
            },
        )
        result = handle_contact_callback(
            notification=notif,
            action="ch_phone",
            user=user_owner,
        )
        assert result["ok"] is True
        assert result["next_step"] == 2

    @patch("projects.telegram.handlers._send_next_step")
    def test_result_selection(self, mock_send, binding, user_owner, project):
        from candidates.models import Candidate

        candidate = Candidate.objects.create(
            name="홍길동", owned_by=binding.user.membership.organization
        )
        notif = Notification.objects.create(
            recipient=user_owner,
            type=Notification.Type.AUTO_GENERATED,
            title="Contact",
            body="Test",
            callback_data={
                "action": "contact_record",
                "step": 2,
                "project_id": str(project.pk),
                "candidate_id": str(candidate.pk),
                "channel": "전화",
            },
        )
        result = handle_contact_callback(
            notification=notif,
            action="rs_interest",
            user=user_owner,
        )
        assert result["ok"] is True
        assert result["next_step"] == 3

    @patch("projects.telegram.handlers._send_next_step")
    def test_save_creates_contact(self, mock_send, binding, user_owner, project):
        from candidates.models import Candidate

        candidate = Candidate.objects.create(
            name="홍길동", owned_by=binding.user.membership.organization
        )
        notif = Notification.objects.create(
            recipient=user_owner,
            type=Notification.Type.AUTO_GENERATED,
            title="Contact",
            body="Test",
            callback_data={
                "action": "contact_record",
                "step": 3,
                "project_id": str(project.pk),
                "candidate_id": str(candidate.pk),
                "channel": "전화",
                "result": "관심",
            },
        )
        result = handle_contact_callback(
            notification=notif,
            action="save",
            user=user_owner,
        )
        assert result["ok"] is True
        assert Contact.objects.filter(project=project, candidate=candidate).exists()
