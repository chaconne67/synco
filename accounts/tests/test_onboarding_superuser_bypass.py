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
