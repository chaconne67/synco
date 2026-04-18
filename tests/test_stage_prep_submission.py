import pytest
from django.urls import reverse

from projects.models import ActionItem, ActionItemStatus


@pytest.mark.django_db
def test_prep_submission_confirm_creates_submit_to_pm_done(client, user, project):
    """컨설턴트 컨펌 → submit_to_pm ActionItem DONE 생성."""
    from candidates.models import Candidate
    from projects.models import Application

    c = Candidate.objects.create(name="컨펌후보")
    app = Application.objects.create(project=project, candidate=c, created_by=user)
    client.force_login(user)

    resp = client.post(
        reverse("projects:stage_prep_submission_confirm", args=[app.pk]),
    )
    assert resp.status_code in (200, 302)
    assert ActionItem.objects.filter(
        application=app,
        action_type__code="submit_to_pm",
        status=ActionItemStatus.DONE,
    ).exists()
