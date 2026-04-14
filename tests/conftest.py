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
        status=ProjectStatus.OPEN,
        created_by=user,
    )


# --- Phase 2a fixtures ---


@pytest.fixture
def candidate(db):
    from candidates.models import Candidate

    return Candidate.objects.create(name="김후보")


@pytest.fixture
def application(db, project, candidate, user):
    from projects.models import Application

    return Application.objects.create(
        project=project,
        candidate=candidate,
        created_by=user,
    )


@pytest.fixture
def second_application(db, project, user):
    from candidates.models import Candidate
    from projects.models import Application

    candidate2 = Candidate.objects.create(name="이후보")
    return Application.objects.create(
        project=project,
        candidate=candidate2,
        created_by=user,
    )
