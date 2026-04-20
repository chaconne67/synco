import pytest

from accounts.services.scope import scope_work_qs
from projects.models import Project, ProjectStatus


@pytest.fixture
def projects_fixture(db, staff_user, boss_user):
    from clients.models import Client

    cli = Client.objects.create(name="Acme")
    p_assigned = Project.objects.create(
        client=cli, title="Own", status=ProjectStatus.OPEN, created_by=staff_user
    )
    p_assigned.assigned_consultants.add(staff_user)

    p_other = Project.objects.create(
        client=cli, title="Other", status=ProjectStatus.OPEN, created_by=boss_user
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


@pytest.mark.django_db
def test_application_scope_for_staff(staff_user, project_assigned_to_staff, candidate):
    from projects.models import Application
    from accounts.services.scope import scope_work_qs

    app_own = Application.objects.create(
        project=project_assigned_to_staff, candidate=candidate, created_by=staff_user
    )
    qs = scope_work_qs(Application.objects.all(), staff_user)
    ids = set(qs.values_list("id", flat=True))
    assert app_own.id in ids


@pytest.mark.django_db
def test_action_item_scope_or_rule(staff_user, staff_user_2, project, candidate):
    """ActionItem: 본인 assigned_to 거나 본인이 컨설턴트인 프로젝트의 액션."""
    from projects.models import Application, ActionItem, ActionType
    from accounts.services.scope import scope_work_qs

    project.assigned_consultants.add(staff_user_2)
    app = Application.objects.create(
        project=project, candidate=candidate, created_by=staff_user_2
    )
    atype, _ = ActionType.objects.get_or_create(
        code="test_action", defaults={"label_ko": "테스트"}
    )

    ai_own = ActionItem.objects.create(
        application=app, action_type=atype, title="내 TODO", assigned_to=staff_user
    )
    ai_project = ActionItem.objects.create(
        application=app,
        action_type=atype,
        title="팀원 TODO",
        assigned_to=staff_user_2,
    )

    qs = scope_work_qs(ActionItem.objects.all(), staff_user)
    ids = set(qs.values_list("id", flat=True))
    assert ai_own.id in ids
    assert ai_project.id not in ids


@pytest.mark.django_db
def test_unknown_model_raises(staff_user):
    from clients.models import Client
    from accounts.services.scope import scope_work_qs

    with pytest.raises(ValueError):
        scope_work_qs(Client.objects.all(), staff_user)
