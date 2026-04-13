import pytest
from django.test import override_settings

from accounts.models import Membership, Organization, User


CEO_LOGIN_URL = "/accounts/ceo-login/"


@pytest.mark.django_db
@override_settings(ALLOW_CEO_TEST_LOGIN=False)
def test_ceo_login_returns_404_when_flag_off(client):
    resp = client.get(CEO_LOGIN_URL)
    assert resp.status_code == 404


@pytest.mark.django_db
@override_settings(ALLOW_CEO_TEST_LOGIN=True)
def test_ceo_login_get_renders_form_when_flag_on(client):
    resp = client.get(CEO_LOGIN_URL)
    assert resp.status_code == 200
    assert b'name="username"' in resp.content


@pytest.mark.django_db
@override_settings(ALLOW_CEO_TEST_LOGIN=True)
def test_ceo_login_accepts_owner_and_redirects(client):
    org = Organization.objects.create(name="테스트 헤드헌팅")
    ceo = User.objects.create_user(
        username="ceo",
        email="ceo@example.com",
        password="ceo1234",
    )
    Membership.objects.create(
        user=ceo,
        organization=org,
        role=Membership.Role.OWNER,
        status=Membership.Status.ACTIVE,
    )
    resp = client.post(
        CEO_LOGIN_URL,
        {"username": "ceo", "password": "ceo1234"},
    )
    assert resp.status_code == 302
    assert resp.url == "/"
    assert "_auth_user_id" in client.session


@pytest.mark.django_db
@override_settings(ALLOW_CEO_TEST_LOGIN=True)
def test_ceo_login_rejects_non_owner(client):
    User.objects.create_user(
        username="rando",
        email="r@example.com",
        password="pw!",
    )
    resp = client.post(
        CEO_LOGIN_URL,
        {"username": "rando", "password": "pw!"},
    )
    assert resp.status_code == 200
    assert "_auth_user_id" not in client.session
