import pytest
from django.urls import reverse

from accounts.models import InviteCode, Membership, Organization, User


SUPERADMIN_URL = "/superadmin/companies/"


@pytest.mark.django_db
def test_anonymous_redirected_to_login(client):
    resp = client.get(SUPERADMIN_URL)
    assert resp.status_code == 302
    assert "/accounts/login/" in resp.url


@pytest.mark.django_db
def test_non_superuser_gets_404(client):
    u = User.objects.create_user(username="u1", email="u1@e.com", password="p!")
    client.force_login(u)
    resp = client.get(SUPERADMIN_URL)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_superuser_get_shows_form_and_empty_list(client):
    su = User.objects.create_user(
        username="su", email="su@e.com", password="p!",
        is_superuser=True, is_staff=True,
    )
    client.force_login(su)
    resp = client.get(SUPERADMIN_URL)
    assert resp.status_code == 200
    assert b"name=\"name\"" in resp.content


@pytest.mark.django_db
def test_superuser_post_creates_org_and_owner_invite(client):
    su = User.objects.create_user(
        username="su", email="su@e.com", password="p!",
        is_superuser=True, is_staff=True,
    )
    client.force_login(su)
    resp = client.post(SUPERADMIN_URL, {"name": "ACME 헤드헌팅"})
    assert resp.status_code == 302
    assert resp.url == SUPERADMIN_URL
    org = Organization.objects.get(name="ACME 헤드헌팅")
    invite = InviteCode.objects.get(organization=org)
    assert invite.role == InviteCode.Role.OWNER
    assert invite.is_active
    assert invite.created_by == su


@pytest.mark.django_db
def test_superuser_post_empty_name_shows_error(client):
    su = User.objects.create_user(
        username="su", email="su@e.com", password="p!",
        is_superuser=True, is_staff=True,
    )
    client.force_login(su)
    resp = client.post(SUPERADMIN_URL, {"name": "   "})
    assert resp.status_code == 200
    assert Organization.objects.count() == 0


@pytest.mark.django_db
def test_list_shows_existing_companies_with_codes(client):
    su = User.objects.create_user(
        username="su", email="su@e.com", password="p!",
        is_superuser=True, is_staff=True,
    )
    org = Organization.objects.create(name="Preexisting Co")
    InviteCode.objects.create(
        organization=org,
        role=InviteCode.Role.OWNER,
        created_by=su,
    )
    client.force_login(su)
    resp = client.get(SUPERADMIN_URL)
    assert resp.status_code == 200
    assert b"Preexisting Co" in resp.content
