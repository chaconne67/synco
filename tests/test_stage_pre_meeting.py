import pytest
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone

from projects.models import ActionItem, ActionItemStatus


@pytest.mark.django_db
def test_schedule_creates_schedule_pre_meet_done(client, user, project):
    """일정 확정 → schedule_pre_meet ActionItem DONE 생성."""
    from candidates.models import Candidate
    from projects.models import Application

    c = Candidate.objects.create(name="일정테스트")
    app = Application.objects.create(project=project, candidate=c, created_by=user)
    client.force_login(user)

    future = (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    resp = client.post(
        reverse("projects:stage_pre_meeting_schedule", args=[app.pk]),
        {"scheduled_at": future, "channel": "video", "location": "zoom.us/abc"},
    )
    assert resp.status_code in (200, 302)
    ai = ActionItem.objects.get(application=app, action_type__code="schedule_pre_meet")
    assert ai.status == ActionItemStatus.DONE
    assert ai.scheduled_at is not None


@pytest.mark.django_db
def test_record_creates_meeting_done(client, user, project):
    """결과 기록 → pre_meeting ActionItem DONE + summary 저장."""
    from candidates.models import Candidate
    from projects.models import Application

    c = Candidate.objects.create(name="결과테스트")
    app = Application.objects.create(project=project, candidate=c, created_by=user)
    client.force_login(user)

    resp = client.post(
        reverse("projects:stage_pre_meeting_record", args=[app.pk]),
        {"summary": "좋은 인상, 연봉 협의 필요"},
    )
    assert resp.status_code in (200, 302)
    ai = ActionItem.objects.get(application=app, action_type__code="pre_meeting")
    assert ai.status == ActionItemStatus.DONE
    assert "좋은 인상" in ai.result


@pytest.mark.django_db
def test_has_pre_meeting_scheduled_property(user, project):
    """schedule ActionItem 이 DONE 으로 있으면 True, 없으면 False."""
    from candidates.models import Candidate
    from projects.models import Application, ActionType

    c = Candidate.objects.create(name="프로퍼티테스트")
    app = Application.objects.create(project=project, candidate=c, created_by=user)
    assert app.has_pre_meeting_scheduled is False

    schedule_type = ActionType.objects.get(code="schedule_pre_meet")
    ActionItem.objects.create(
        application=app,
        action_type=schedule_type,
        title="일정",
        status=ActionItemStatus.DONE,
        scheduled_at=timezone.now() + timedelta(days=1),
    )
    app.refresh_from_db()
    assert app.has_pre_meeting_scheduled is True
    assert app.pre_meeting_scheduled_at is not None
