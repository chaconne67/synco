import pytest
from django.contrib.auth import get_user_model

from clients.models import Client
from projects.models import Project, ProjectStatus

User = get_user_model()


# --- Level-based user fixtures ---


@pytest.fixture
def pending_user(db):
    return User.objects.create_user(username="pending_u", password="x", level=0)


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username="staff_u", password="x", level=1)


@pytest.fixture
def staff_user_2(db):
    return User.objects.create_user(username="staff_u2", password="x", level=1)


@pytest.fixture
def boss_user(db):
    return User.objects.create_user(username="boss_u", password="x", level=2)


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
def pending_client(client, pending_user):
    client.force_login(pending_user)
    return client


@pytest.fixture
def staff_client(client, staff_user):
    client.force_login(staff_user)
    return client


@pytest.fixture
def boss_client(client, boss_user):
    client.force_login(boss_user)
    return client


@pytest.fixture
def dev_client(client, dev_user):
    client.force_login(dev_user)
    return client


# --- Domain fixtures ---


@pytest.fixture
def client_company(db):
    return Client.objects.create(name="Rayence")


@pytest.fixture
def project(db, client_company, boss_user):
    p = Project.objects.create(
        client=client_company,
        title="품질기획",
        status=ProjectStatus.OPEN,
        created_by=boss_user,
    )
    return p


@pytest.fixture
def project_assigned_to_staff(db, client_company, staff_user):
    p = Project.objects.create(
        client=client_company,
        title="Assigned",
        status=ProjectStatus.OPEN,
        created_by=staff_user,
    )
    p.assigned_consultants.add(staff_user)
    return p


@pytest.fixture
def candidate(db):
    from candidates.models import Candidate

    return Candidate.objects.create(name="김후보")


@pytest.fixture
def application(db, project, candidate, boss_user):
    from projects.models import Application

    return Application.objects.create(
        project=project, candidate=candidate, created_by=boss_user
    )


@pytest.fixture
def second_application(db, project, boss_user):
    from candidates.models import Candidate
    from projects.models import Application

    c2 = Candidate.objects.create(name="이후보")
    return Application.objects.create(
        project=project, candidate=c2, created_by=boss_user
    )


@pytest.fixture
def third_candidate(db):
    from candidates.models import Candidate

    return Candidate.objects.create(name="박후보")


@pytest.fixture
def third_application(db, project, third_candidate, boss_user):
    from projects.models import Application

    return Application.objects.create(
        project=project, candidate=third_candidate, created_by=boss_user
    )


# --- ActionType fixtures (migration-seeded) ---


@pytest.fixture
def action_type_reach_out(db):
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
def submission_factory(db, project, boss_user):
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
            project=project, candidate=candidate, created_by=boss_user
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
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }


# --- Back-compat aliases for tests not yet fully rewritten ---


@pytest.fixture
def user(boss_user):
    """Back-compat: default logged-in user is now the boss."""
    return boss_user


@pytest.fixture
def other_user(staff_user_2):
    return staff_user_2


@pytest.fixture
def logged_in_client(boss_client):
    return boss_client
