import pytest
from django.contrib.auth import get_user_model

from accounts.models import Membership, Organization
from clients.models import Client
from projects.models import Project, ProjectStatus

User = get_user_model()


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Org")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="consultant1", password="testpass123")
    Membership.objects.create(user=u, organization=org, role="owner", status="active")
    return u


@pytest.fixture
def other_user(db, org):
    u = User.objects.create_user(username="consultant2", password="testpass123")
    Membership.objects.create(user=u, organization=org, role="owner", status="active")
    return u


@pytest.fixture
def other_org_user(db):
    other_org = Organization.objects.create(name="Other Org")
    u = User.objects.create_user(username="outsider", password="testpass123")
    Membership.objects.create(user=u, organization=other_org, status="active")
    return u


@pytest.fixture
def client_company(db, org):
    return Client.objects.create(name="Rayence", organization=org)


@pytest.fixture
def project(db, org, client_company, user):
    return Project.objects.create(
        client=client_company,
        organization=org,
        title="품질기획",
        status=ProjectStatus.SEARCHING,  # NOT NEW — avoids signal trigger
        created_by=user,
    )


@pytest.fixture
def new_project(db, org, client_company, user):
    """Project with NEW status — triggers on_project_created signal."""
    return Project.objects.create(
        client=client_company,
        organization=org,
        title="Signal Test Project",
        status=ProjectStatus.NEW,
        created_by=user,
    )
