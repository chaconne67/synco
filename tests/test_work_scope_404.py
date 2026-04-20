"""Cross-user 404 integration — Level 1 staff cannot access other staff's work.

This file is the executable contract for the scope enforcement spec
(docs/superpowers/specs/2026-04-21-work-scope-enforcement-design.md).
"""

import pytest


@pytest.fixture
def other_project(db, client_company, staff_user_2):
    from projects.models import Project, ProjectStatus

    p = Project.objects.create(
        client=client_company,
        title="남의 것",
        status=ProjectStatus.OPEN,
        created_by=staff_user_2,
    )
    p.assigned_consultants.add(staff_user_2)
    return p


@pytest.mark.django_db
def test_staff_gets_404_on_other_project_detail(staff_client, other_project):
    resp = staff_client.get(f"/projects/{other_project.pk}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_staff_gets_404_on_other_project_applications_partial(
    staff_client, other_project
):
    resp = staff_client.get(f"/projects/{other_project.pk}/applications/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_staff_gets_404_on_other_project_timeline(staff_client, other_project):
    resp = staff_client.get(f"/projects/{other_project.pk}/timeline/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_staff_gets_404_on_other_application(staff_client, other_project, candidate):
    from projects.models import Application

    app = Application.objects.create(
        project=other_project, candidate=candidate, created_by=other_project.created_by
    )
    from django.urls import reverse

    try:
        url = reverse("application_detail", kwargs={"pk": app.pk})
    except Exception:
        pytest.skip("application detail URL not present")
    resp = staff_client.get(url)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_boss_sees_other_staff_project(boss_client, other_project):
    resp = boss_client.get(f"/projects/{other_project.pk}/")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_superuser_sees_other_staff_project(dev_client, other_project):
    resp = dev_client.get(f"/projects/{other_project.pk}/")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_staff_sees_own_project(staff_client, project_assigned_to_staff):
    resp = staff_client.get(f"/projects/{project_assigned_to_staff.pk}/")
    assert resp.status_code == 200
