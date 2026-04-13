import pytest
from django.urls import reverse

from accounts.models import User


STAFF_LOGIN_URL = "/accounts/chaconne67-login/"


@pytest.mark.django_db
def test_staff_login_get_renders_form(client):
    resp = client.get(STAFF_LOGIN_URL)
    assert resp.status_code == 200
    assert b"name=\"username\"" in resp.content
    assert b"name=\"password\"" in resp.content


@pytest.mark.django_db
def test_staff_login_rejects_non_superuser(client):
    User.objects.create_user(
        username="normaluser",
        email="n@example.com",
        password="pw12345!",
    )
    resp = client.post(
        STAFF_LOGIN_URL,
        {"username": "normaluser", "password": "pw12345!"},
    )
    assert resp.status_code == 200  # renders form with error
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_staff_login_rejects_bad_password(client):
    User.objects.create_user(
        username="chaconne67",
        email="c@example.com",
        password="correct!",
        is_superuser=True,
        is_staff=True,
    )
    resp = client.post(
        STAFF_LOGIN_URL,
        {"username": "chaconne67", "password": "wrong"},
    )
    assert resp.status_code == 200
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_staff_login_accepts_superuser_and_redirects(client):
    User.objects.create_user(
        username="chaconne67",
        email="c@example.com",
        password="correct!",
        is_superuser=True,
        is_staff=True,
    )
    resp = client.post(
        STAFF_LOGIN_URL,
        {"username": "chaconne67", "password": "correct!"},
    )
    assert resp.status_code == 302
    assert resp.url == "/"
    assert "_auth_user_id" in client.session
