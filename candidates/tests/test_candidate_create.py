import pytest
from django.contrib.auth import get_user_model
from candidates.models import Candidate


@pytest.fixture
def auth_client(client, db):
    User = get_user_model()
    u = User.objects.create_user(username="creator", password="x")
    client.force_login(u)
    return client


@pytest.mark.django_db
def test_new_page_renders(auth_client):
    resp = auth_client.get("/candidates/new/")
    assert resp.status_code == 200
    assert b'name="name"' in resp.content


@pytest.mark.django_db
def test_create_requires_email_or_phone(auth_client):
    resp = auth_client.post("/candidates/new/", {"name": "테스트이름A"})
    assert resp.status_code in (400, 200)
    assert not Candidate.objects.filter(name="테스트이름A").exists()


@pytest.mark.django_db
def test_create_with_email_succeeds(auth_client):
    resp = auth_client.post(
        "/candidates/new/",
        {
            "name": "테스트이름B",
            "email": "holong@ex.com",
            "current_company": "네이버",
        },
    )
    assert resp.status_code in (302, 200)
    assert Candidate.objects.filter(name="테스트이름B", email="holong@ex.com").exists()


@pytest.mark.django_db
def test_duplicate_email_warns(auth_client):
    Candidate.objects.create(name="기존후보자A", email="dup@ex.com")
    resp = auth_client.post(
        "/candidates/new/",
        {
            "name": "신규후보자A",
            "email": "dup@ex.com",
        },
    )
    assert resp.status_code == 200
    assert b"duplicate" in resp.content.lower() or "기존후보자A".encode("utf-8") in resp.content
    # Should NOT have created the new one (still duplicate warning screen)
    assert not Candidate.objects.filter(name="신규후보자A").exists()
