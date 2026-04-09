"""P15: Reminder management command tests."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts.models import Membership, Organization, TelegramBinding, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import (
    Contact,
    Interview,
    Notification,
    Project,
    Submission,
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
def client_obj(org):
    return Client.objects.create(name="Acme", organization=org)


@pytest.fixture
def project(org, client_obj, user):
    return Project.objects.create(
        client=client_obj,
        organization=org,
        title="Test Project",
        created_by=user,
    )


@pytest.fixture
def candidate(org):
    return Candidate.objects.create(name="홍길동", owned_by=org)


class TestSendReminders:
    @patch("projects.services.notification.send_notification")
    def test_recontact_reminder(self, mock_send, binding, project, candidate, user):
        mock_send.return_value = True
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            result=Contact.Result.RESERVED,
            next_contact_date=date.today(),
            locked_until=timezone.now() + timedelta(days=1),
        )
        call_command("send_reminders")
        assert Notification.objects.filter(type=Notification.Type.REMINDER).exists()

    @patch("projects.services.notification.send_notification")
    def test_lock_expiry_reminder(self, mock_send, binding, project, candidate, user):
        mock_send.return_value = True
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            result=Contact.Result.RESERVED,
            locked_until=timezone.now() + timedelta(days=1),
        )
        call_command("send_reminders")
        assert Notification.objects.filter(
            type=Notification.Type.REMINDER,
        ).exists()

    @patch("projects.services.notification.send_notification")
    def test_submission_review_reminder(
        self, mock_send, binding, project, candidate, user
    ):
        mock_send.return_value = True
        Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            status=Submission.Status.SUBMITTED,
            submitted_at=timezone.now() - timedelta(days=3),
        )
        call_command("send_reminders")
        assert Notification.objects.filter(
            type=Notification.Type.REMINDER,
        ).exists()

    @patch("projects.services.notification.send_notification")
    def test_interview_tomorrow_reminder(
        self, mock_send, binding, project, candidate, user
    ):
        mock_send.return_value = True
        sub = Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            status=Submission.Status.PASSED,
        )
        Interview.objects.create(
            submission=sub,
            round=1,
            scheduled_at=timezone.now() + timedelta(days=1),
            type=Interview.Type.IN_PERSON,
        )
        call_command("send_reminders")
        assert Notification.objects.filter(
            type=Notification.Type.REMINDER,
        ).exists()

    @patch("projects.services.notification.send_notification")
    def test_no_reminders_when_nothing_due(self, mock_send, binding, project):
        mock_send.return_value = True
        call_command("send_reminders")
        assert not Notification.objects.filter(
            type=Notification.Type.REMINDER,
        ).exists()
