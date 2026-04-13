import pytest
from django.urls import reverse

from accounts.models import Organization, User


@pytest.mark.django_db
def test_superuser_bypasses_membership_required_on_dashboard(client):
    Organization.objects.create(name="Test Org")
    su = User.objects.create_user(
        username="su_test",
        email="su_test@example.com",
        password="pw12345!",
        is_superuser=True,
        is_staff=True,
    )
    client.force_login(su)
    resp = client.get(reverse("dashboard"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_non_superuser_without_membership_redirects_to_invite(client):
    u = User.objects.create_user(
        username="normal_user",
        email="normal@example.com",
        password="pw12345!",
    )
    client.force_login(u)
    resp = client.get(reverse("dashboard"))
    assert resp.status_code == 302
    assert "/accounts/invite/" in resp.url


@pytest.mark.django_db
def test_superuser_root_goes_to_dashboard_not_invite(client):
    su = User.objects.create_user(
        username="su_root",
        email="su_root@example.com",
        password="pw12345!",
        is_superuser=True,
        is_staff=True,
    )
    client.force_login(su)
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.url.endswith("/dashboard/")


@pytest.mark.django_db
def test_superuser_on_invite_page_goes_to_dashboard(client):
    su = User.objects.create_user(
        username="su_invite",
        email="su_invite@example.com",
        password="pw12345!",
        is_superuser=True,
        is_staff=True,
    )
    client.force_login(su)
    resp = client.get(reverse("invite_code"))
    assert resp.status_code == 302
    assert resp.url.endswith("/dashboard/")
