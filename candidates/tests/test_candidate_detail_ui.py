import pytest
from django.contrib.auth import get_user_model
from candidates.models import Candidate, LanguageSkill


@pytest.fixture
def auth_client(client, db):
    User = get_user_model()
    u = User.objects.create_user(username="detail_viewer", password="x", level=1)
    client.force_login(u)
    return client


@pytest.mark.django_db
def test_detail_page_renders_new_header(client):
    User = get_user_model()
    u = User.objects.create_user(username="viewer", password="x", level=1)
    client.force_login(u)
    c = Candidate.objects.create(name="상세뷰테스트", current_company="네이버")
    resp = client.get(f"/candidates/{c.pk}/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Candidate Profile" in body
    assert "Back to Talent Pool" in body
    assert "상세뷰테스트" in body


@pytest.mark.django_db
def test_detail_renders_sections(auth_client):
    c = Candidate.objects.create(name="김상세", summary="테스트 요약")
    LanguageSkill.objects.create(candidate=c, language="영어", level="Business")
    resp = auth_client.get(f"/candidates/{c.pk}/")
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "Summary" in content
    assert "테스트 요약" in content
    assert "Languages" in content
    assert "Activity Snapshot" in content
    assert "준비중" in content
