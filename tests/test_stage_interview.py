import pytest
from django.urls import reverse

from projects.models import ActionItem, ActionItemStatus


@pytest.mark.django_db
def test_interview_passed_without_review(client, user, project):
    """Review 없이도 합격 결과로 완료."""
    from candidates.models import Candidate
    from projects.models import Application

    c = Candidate.objects.create(name="합격후보")
    app = Application.objects.create(project=project, candidate=c, created_by=user)
    client.force_login(user)

    resp = client.post(
        reverse("projects:stage_interview_complete", args=[app.pk]),
        {"result": "passed"},
    )
    assert resp.status_code in (200, 302)
    ai = ActionItem.objects.get(application=app, action_type__code="interview_round")
    assert ai.status == ActionItemStatus.DONE


@pytest.mark.django_db
def test_interview_with_review_text(client, user, project):
    """리뷰 텍스트 저장 확인."""
    from candidates.models import Candidate
    from projects.models import Application

    c = Candidate.objects.create(name="리뷰후보")
    app = Application.objects.create(project=project, candidate=c, created_by=user)
    client.force_login(user)

    resp = client.post(
        reverse("projects:stage_interview_complete", args=[app.pk]),
        {"result": "passed", "review": "질문 대응 무난, 연봉 협의 필요"},
    )
    assert resp.status_code in (200, 302)
    ai = ActionItem.objects.get(application=app, action_type__code="interview_round")
    assert "연봉 협의" in ai.result


@pytest.mark.django_db
def test_interview_failed_drops(client, user, project):
    """탈락 결과 → Application drop (client_rejected)."""
    from candidates.models import Candidate
    from projects.models import Application

    c = Candidate.objects.create(name="탈락후보")
    app = Application.objects.create(project=project, candidate=c, created_by=user)
    client.force_login(user)

    resp = client.post(
        reverse("projects:stage_interview_complete", args=[app.pk]),
        {"result": "failed", "review": "역량 부족"},
    )
    assert resp.status_code in (200, 302)
    app.refresh_from_db()
    assert app.dropped_at is not None
    assert app.drop_reason == "client_rejected"
    assert "역량 부족" in app.drop_note
