import pytest
from django.urls import reverse

from projects.models import ActionItem, ActionItemStatus


@pytest.mark.django_db
def test_contact_positive_creates_reach_out_done(client, user, project):
    """긍정 응답 → reach_out ActionItem DONE 생성, note에 응답 기록."""
    from candidates.models import Candidate
    from projects.models import Application

    c = Candidate.objects.create(name="긍정후보")
    app = Application.objects.create(project=project, candidate=c, created_by=user)
    client.force_login(user)

    resp = client.post(
        reverse("projects:stage_contact_complete", args=[app.pk]),
        {"response": "positive", "note": "수락함"},
    )
    assert resp.status_code in (200, 302)
    ai = ActionItem.objects.get(application=app, action_type__code="reach_out")
    assert ai.status == ActionItemStatus.DONE
    assert "positive" in ai.note
    assert "수락함" in ai.note


@pytest.mark.django_db
def test_contact_negative_drops_application(client, user, project):
    """부정 응답 → Application drop (candidate_declined)."""
    from candidates.models import Candidate
    from projects.models import Application

    c = Candidate.objects.create(name="거절후보")
    app = Application.objects.create(project=project, candidate=c, created_by=user)
    client.force_login(user)

    resp = client.post(
        reverse("projects:stage_contact_complete", args=[app.pk]),
        {"response": "negative", "note": "거절함"},
    )
    assert resp.status_code in (200, 302)
    app.refresh_from_db()
    assert app.dropped_at is not None
    assert app.drop_reason == "candidate_declined"
    assert "거절함" in app.drop_note


@pytest.mark.django_db
def test_contact_pending_creates_reach_out_done(client, user, project):
    """보류 응답도 reach_out DONE 생성 (접촉 자체는 성사 — drop 안 함)."""
    from candidates.models import Candidate
    from projects.models import Application

    c = Candidate.objects.create(name="보류후보")
    app = Application.objects.create(project=project, candidate=c, created_by=user)
    client.force_login(user)

    resp = client.post(
        reverse("projects:stage_contact_complete", args=[app.pk]),
        {"response": "pending"},
    )
    assert resp.status_code in (200, 302)
    ai = ActionItem.objects.get(application=app, action_type__code="reach_out")
    assert ai.status == ActionItemStatus.DONE
