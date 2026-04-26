"""Smoke test: key project views render without 500."""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_dashboard_renders(staff_user, client):
    client.force_login(staff_user)
    resp = client.get(reverse("dashboard"))
    assert resp.status_code in (200, 302)


def test_project_list_renders(staff_user, client):
    client.force_login(staff_user)
    resp = client.get(reverse("projects:project_list"))
    assert resp.status_code in (200, 302)


def test_project_create_form_renders(staff_user, client):
    client.force_login(staff_user)
    resp = client.get(reverse("projects:project_create"))
    assert resp.status_code in (200, 302)


def test_approval_queue_renders(staff_user, client):
    client.force_login(staff_user)
    resp = client.get(reverse("projects:approval_queue"))
    assert resp.status_code in (200, 302, 403)


def test_resume_unassigned_renders(staff_user, client):
    client.force_login(staff_user)
    resp = client.get(reverse("projects:resume_unassigned"))
    assert resp.status_code in (200, 302)
