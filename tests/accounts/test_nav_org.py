import pytest
from django.test import Client as TestClient
from django.contrib.auth import get_user_model

from accounts.models import Membership, Organization

User = get_user_model()


@pytest.fixture
def owner_client(db):
    org = Organization.objects.create(name="Test Org")
    owner = User.objects.create_user(username="nav_owner", password="pass")
    Membership.objects.create(user=owner, organization=org, role="owner", status="active")
    client = TestClient()
    client.force_login(owner)
    return client


@pytest.fixture
def consultant_client(db):
    org = Organization.objects.create(name="Test Org")
    consultant = User.objects.create_user(username="nav_cons", password="pass")
    Membership.objects.create(user=consultant, organization=org, role="consultant", status="active")
    client = TestClient()
    client.force_login(consultant)
    return client


@pytest.mark.django_db
class TestNavOrgVisibility:
    def test_owner_sees_org_link_in_nav(self, owner_client):
        response = owner_client.get("/", follow=True)
        content = response.content.decode()
        assert 'data-nav="org"' in content

    def test_consultant_does_not_see_org_link(self, consultant_client):
        response = consultant_client.get("/", follow=True)
        content = response.content.decode()
        assert 'data-nav="org"' not in content
