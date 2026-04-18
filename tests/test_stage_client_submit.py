import pytest
from django.urls import reverse

from projects.models import Submission


@pytest.mark.django_db
def test_client_submit_single_creates_submission_without_batch(client, user, project):
    """단독 제출 → Submission 생성, batch_id = None."""
    from candidates.models import Candidate
    from projects.models import Application

    c = Candidate.objects.create(name="단독제출후보")
    app = Application.objects.create(project=project, candidate=c, created_by=user)
    client.force_login(user)

    resp = client.post(
        reverse("projects:stage_client_submit_single", args=[app.pk]),
    )
    assert resp.status_code in (200, 302)
    sub = Submission.objects.get(action_item__application=app)
    assert sub.batch_id is None  # 단독 제출 = batch_id 없음
    assert sub.consultant == user
