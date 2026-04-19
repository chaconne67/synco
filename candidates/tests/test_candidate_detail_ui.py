import pytest
from django.contrib.auth import get_user_model
from candidates.models import Candidate


@pytest.mark.django_db
def test_detail_page_renders_new_header(client):
    User = get_user_model()
    u = User.objects.create_user(username="viewer", password="x")
    client.force_login(u)
    c = Candidate.objects.create(name="상세뷰테스트", current_company="네이버")
    resp = client.get(f"/candidates/{c.pk}/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Candidate Profile" in body
    assert "Back to Talent Pool" in body
    assert "상세뷰테스트" in body
