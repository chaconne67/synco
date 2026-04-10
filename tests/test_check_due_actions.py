from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from candidates.models import Candidate
from projects.models import (
    ActionStatus,
    ActionType,
    AutoAction,
    Contact,
    Notification,
)


@pytest.mark.django_db
class TestCheckDueActions:
    def test_creates_recontact_reminder_for_expiring_lock(self, project, user, org):
        candidate = Candidate.objects.create(name="만료임박", owned_by=org)
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=Contact.Channel.PHONE,
            result=Contact.Result.RESERVED,
            locked_until=timezone.now() + timedelta(hours=20),
        )
        call_command("check_due_actions")
        actions = AutoAction.objects.filter(
            project=project,
            action_type=ActionType.RECONTACT_REMINDER,
        )
        assert actions.count() == 1
        assert "만료임박" in actions[0].title

    def test_ignores_already_expired_locks(self, project, user, org):
        candidate = Candidate.objects.create(name="이미만료", owned_by=org)
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=Contact.Channel.PHONE,
            result=Contact.Result.RESERVED,
            locked_until=timezone.now() - timedelta(hours=1),
        )
        call_command("check_due_actions")
        assert AutoAction.objects.filter(
            project=project,
            action_type=ActionType.RECONTACT_REMINDER,
        ).count() == 0

    def test_ignores_far_future_locks(self, project, user, org):
        candidate = Candidate.objects.create(name="먼미래", owned_by=org)
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=Contact.Channel.PHONE,
            result=Contact.Result.RESERVED,
            locked_until=timezone.now() + timedelta(days=5),
        )
        call_command("check_due_actions")
        assert AutoAction.objects.filter(
            project=project,
            action_type=ActionType.RECONTACT_REMINDER,
        ).count() == 0

    def test_idempotent_run(self, project, user, org):
        candidate = Candidate.objects.create(name="멱등", owned_by=org)
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=Contact.Channel.PHONE,
            result=Contact.Result.RESERVED,
            locked_until=timezone.now() + timedelta(hours=20),
        )
        call_command("check_due_actions")
        call_command("check_due_actions")
        assert AutoAction.objects.filter(
            project=project,
            action_type=ActionType.RECONTACT_REMINDER,
        ).count() == 1

    def test_processes_due_followup_reminders(self, project, user, org):
        """Due followup reminders create Notification records."""
        candidate = Candidate.objects.create(name="팔로업", owned_by=org)
        AutoAction.objects.create(
            project=project,
            trigger_event="submission_submitted",
            action_type=ActionType.FOLLOWUP_REMINDER,
            title="팔로업 리마인더",
            data={"submission_id": "fake-uuid", "message": "팔로업 필요"},
            due_at=timezone.now() - timedelta(hours=1),
            created_by=user,
        )
        call_command("check_due_actions")
        notifs = Notification.objects.filter(
            type=Notification.Type.REMINDER,
        )
        assert notifs.count() >= 1
