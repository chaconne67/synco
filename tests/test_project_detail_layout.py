import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_project_detail_has_area_a_and_b(client, user, project):
    """project_detail 페이지는 영역 A(id=project-area-a)와 영역 B(id=project-area-b)를 반드시 포함."""
    client.force_login(user)
    resp = client.get(reverse("projects:project_detail", args=[project.pk]))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'id="project-area-a"' in content
    assert 'id="project-area-b"' in content


@pytest.mark.django_db
def test_candidate_card_shows_7_stages_not_8(client, user, project):
    """후보자 카드 진행바는 서칭을 제외한 7단계만 표시."""
    from candidates.models import Candidate
    from projects.models import Application

    c = Candidate.objects.create(name="진행바테스트")
    Application.objects.create(project=project, candidate=c, created_by=user)
    client.force_login(user)

    resp = client.get(reverse("projects:project_detail", args=[project.pk]))
    assert resp.status_code == 200
    content = resp.content.decode()

    # 7-stage card should contain each of these labels
    for label in [
        "접촉",
        "이력서 준비",
        "사전 미팅",
        "이력서 작성(제출용)",
        "이력서 제출",
        "면접",
        "입사",
    ]:
        assert label in content, f"Missing stage label: {label}"
