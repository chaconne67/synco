import pytest
from django.urls import reverse

from accounts.models import Membership, Organization, User


@pytest.fixture
def org(db):
    return Organization.objects.create(name="TestOrg")


@pytest.fixture
def owner(org):
    u = User.objects.create_user(username="owner", password="x")
    Membership.objects.create(user=u, organization=org, role="owner")
    return u


@pytest.fixture
def owner_client(client, owner):
    client.force_login(owner)
    return client


@pytest.mark.django_db
def test_dashboard_renders_with_empty_org(owner_client):
    """Skeleton: dashboard renders 200 with empty org, no crash."""
    resp = owner_client.get(reverse("dashboard"))
    assert resp.status_code == 200
    assert b"Monthly Success" in resp.content
