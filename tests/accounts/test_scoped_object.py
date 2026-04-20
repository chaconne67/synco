import pytest
from django.http import Http404

from accounts.services.scope import get_scoped_object_or_404
from projects.models import Project


@pytest.mark.django_db
def test_boss_gets_any_project(boss_user, project):
    result = get_scoped_object_or_404(Project, boss_user, pk=project.pk)
    assert result.pk == project.pk


@pytest.mark.django_db
def test_superuser_gets_any_project(dev_user, project):
    result = get_scoped_object_or_404(Project, dev_user, pk=project.pk)
    assert result.pk == project.pk


@pytest.mark.django_db
def test_staff_gets_own_project(staff_user, project_assigned_to_staff):
    result = get_scoped_object_or_404(
        Project, staff_user, pk=project_assigned_to_staff.pk
    )
    assert result.pk == project_assigned_to_staff.pk


@pytest.mark.django_db
def test_staff_denied_others_project(staff_user, project):
    """project is assigned to boss_user, not staff_user → 404."""
    with pytest.raises(Http404):
        get_scoped_object_or_404(Project, staff_user, pk=project.pk)


@pytest.mark.django_db
def test_pending_denied(pending_user, project):
    with pytest.raises(Http404):
        get_scoped_object_or_404(Project, pending_user, pk=project.pk)


@pytest.mark.django_db
def test_missing_pk_is_404(boss_user, db):
    import uuid

    with pytest.raises(Http404):
        get_scoped_object_or_404(Project, boss_user, pk=uuid.uuid4())
