import pytest

from accounts.services.scope import scope_work_qs
from projects.models import Project, ProjectStatus


@pytest.fixture
def projects_fixture(db, staff_user, boss_user):
    from accounts.models import Organization
    from clients.models import Client

    org = Organization.objects.create(name="Test Org")
    cli = Client.objects.create(name="Acme", organization=org)
    p_assigned = Project.objects.create(
        client=cli, organization=org, title="Own", status=ProjectStatus.OPEN, created_by=staff_user
    )
    p_assigned.assigned_consultants.add(staff_user)

    p_other = Project.objects.create(
        client=cli, organization=org, title="Other", status=ProjectStatus.OPEN, created_by=boss_user
    )
    p_other.assigned_consultants.add(boss_user)
    return p_assigned, p_other


@pytest.mark.django_db
def test_staff_sees_only_assigned(staff_user, projects_fixture):
    p_assigned, p_other = projects_fixture
    qs = scope_work_qs(Project.objects.all(), staff_user)
    ids = set(qs.values_list("id", flat=True))
    assert p_assigned.id in ids
    assert p_other.id not in ids


@pytest.mark.django_db
def test_boss_sees_all(boss_user, projects_fixture):
    qs = scope_work_qs(Project.objects.all(), boss_user)
    assert qs.count() == 2


@pytest.mark.django_db
def test_superuser_sees_all(dev_user, projects_fixture):
    qs = scope_work_qs(Project.objects.all(), dev_user)
    assert qs.count() == 2


@pytest.mark.django_db
def test_pending_sees_nothing(pending_user, projects_fixture):
    qs = scope_work_qs(Project.objects.all(), pending_user)
    assert qs.count() == 0
