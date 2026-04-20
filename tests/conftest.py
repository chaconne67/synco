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
    u = User.objects.create_user(username="consultant1", password="testpass123", level=2)
    Membership.objects.create(user=u, organization=org, role="owner", status="active")
    return u


@pytest.fixture
def other_user(db, org):
    u = User.objects.create_user(username="consultant2", password="testpass123", level=2)
    Membership.objects.create(user=u, organization=org, role="owner", status="active")
    return u


@pytest.fixture
def other_org_user(db):
    other_org = Organization.objects.create(name="Other Org")
    u = User.objects.create_user(username="outsider", password="testpass123", level=2)
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


# --- Phase 5 fixtures ---


@pytest.fixture
def action_type_reach_out(db):
    """Migration-seeded ActionType."""
    from projects.models import ActionType

    return ActionType.objects.get(code="reach_out")


@pytest.fixture
def action_type_submit(db):
    from projects.models import ActionType

    return ActionType.objects.get(code="submit_to_client")


@pytest.fixture
def action_type_confirm_hire(db):
    from projects.models import ActionType

    return ActionType.objects.get(code="confirm_hire")


@pytest.fixture
def logged_in_client(client, user):
    """pytest-django client with force_login."""
    client.force_login(user)
    return client


@pytest.fixture
def other_org_client(client, other_org_user):
    """Different-org user logged-in client."""
    client.force_login(other_org_user)
    return client


@pytest.fixture
def third_candidate(db):
    from candidates.models import Candidate

    return Candidate.objects.create(name="박후보")


@pytest.fixture
def third_application(db, project, third_candidate, user):
    from projects.models import Application

    return Application.objects.create(
        project=project,
        candidate=third_candidate,
        created_by=user,
    )


@pytest.fixture
def submission_factory(db, project, user):
    """Factory that creates a Submission linked to a fresh Application/ActionItem each call."""
    from candidates.models import Candidate
    from projects.models import (
        ActionItem,
        ActionItemStatus,
        ActionType,
        Application,
        Submission,
    )

    counter = {"n": 0}

    def _make(**kwargs):
        batch_id = kwargs.pop("batch_id", None)
        counter["n"] += 1
        candidate = Candidate.objects.create(name=f"배치후보{counter['n']}")
        app = Application.objects.create(
            project=project, candidate=candidate, created_by=user
        )
        at = ActionType.objects.get(code="submit_to_client")
        ai = ActionItem.objects.create(
            application=app,
            action_type=at,
            title="Test submit",
            status=ActionItemStatus.DONE,
        )
        return Submission.objects.create(action_item=ai, batch_id=batch_id)

    return _make


@pytest.fixture(autouse=True)
def _disable_manifest_storage(settings):
    """Use plain static storage for tests (no collectstatic needed)."""
    settings.STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }


@pytest.fixture
def legacy_org(db):
    """Temporary shim until T7 drops organization FK from Client/Project/Contract."""
    from accounts.models import Organization

    return Organization.objects.create(name="Legacy")


# --- Level-based fixtures (single-tenant refactor) ---


@pytest.fixture
def pending_user(db):
    return User.objects.create_user(
        username="pending_u", password="x", level=0
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="staff_u", password="x", level=1
    )


@pytest.fixture
def boss_user(db):
    return User.objects.create_user(
        username="boss_u", password="x", level=2
    )


@pytest.fixture
def dev_user(db):
    return User.objects.create_user(
        username="dev_u",
        password="x",
        level=2,
        is_superuser=True,
        is_staff=True,
    )


@pytest.fixture
def staff_client(client, staff_user):
    client.force_login(staff_user)
    return client


@pytest.fixture
def boss_client(client, boss_user):
    client.force_login(boss_user)
    return client


@pytest.fixture
def pending_client(client, pending_user):
    client.force_login(pending_user)
    return client


@pytest.fixture
def dev_client(client, dev_user):
    client.force_login(dev_user)
    return client
