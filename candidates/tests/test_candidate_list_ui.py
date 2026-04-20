from django.contrib.auth import get_user_model
from candidates.models import Candidate


def _login(client):
    User = get_user_model()
    u = User.objects.create_user(username="lister", password="x", level=1)
    client.force_login(u)
    return u


def test_list_page_renders_card_v2(client, db):
    _login(client)
    Candidate.objects.create(name="김철수", current_company="네이버")
    resp = client.get("/candidates/")
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "김철수" in content
    assert "rounded-card" in content or "bg-white" in content
