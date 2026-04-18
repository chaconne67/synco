import pytest

from projects.models import Application
from projects.services.searching import add_candidates_to_project


@pytest.mark.django_db
def test_add_candidates_creates_applications(project, user):
    from candidates.models import Candidate

    c1 = Candidate.objects.create(name="후보A")
    c2 = Candidate.objects.create(name="후보B")

    apps = add_candidates_to_project(project, [c1.id, c2.id], created_by=user)

    assert len(apps) == 2
    assert Application.objects.filter(project=project).count() == 2


@pytest.mark.django_db
def test_add_candidates_dedupes_existing(project, user):
    from candidates.models import Candidate

    c1 = Candidate.objects.create(name="후보중복")
    Application.objects.create(project=project, candidate=c1)

    apps = add_candidates_to_project(project, [c1.id], created_by=user)
    assert apps == []
    assert Application.objects.filter(project=project, candidate=c1).count() == 1


@pytest.mark.django_db
def test_project_add_candidate_view(client, user, project):
    from candidates.models import Candidate
    from django.urls import reverse

    candidate = Candidate.objects.create(name="통합테스트후보")
    client.force_login(user)

    resp = client.post(
        reverse("projects:project_add_candidate", args=[project.pk]),
        {"candidate_id": str(candidate.pk)},
    )
    assert resp.status_code in (200, 302)
    assert Application.objects.filter(project=project, candidate=candidate).exists()
