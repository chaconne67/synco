"""P14: Voice context resolver tests."""

import pytest

from accounts.models import User
from clients.models import Client
from projects.models import Project
from projects.services.voice.context_resolver import resolve_context



@pytest.fixture
def user(db):
    u = User.objects.create_user(username="ctx_tester", password="test1234")
    return u


@pytest.fixture
def client_obj(db):
    return Client.objects.create(name="Test Client")


@pytest.fixture
def project(db, client_obj, user):
    return Project.objects.create(
        client=client_obj,
        title="Context Test Project",
        created_by=user)


def test_resolve_context_dashboard(user):
    ctx = resolve_context(
        user=user,
        context_hint={"page": "dashboard"})
    assert ctx["page"] == "dashboard"
    assert ctx["project_id"] is None
    assert ctx["scope"] == "global"


def test_resolve_context_project_detail(user, project):
    ctx = resolve_context(
        user=user,
        context_hint={"page": "project_detail", "project_id": str(project.pk)})
    assert ctx["page"] == "project_detail"
    assert ctx["project_id"] == project.pk
    assert ctx["scope"] == "project"
    assert ctx["project_title"] == project.title


def test_resolve_context_invalid_project(user):
    """Project not in user's org -> project_id is None."""
    ctx = resolve_context(
        user=user,
        context_hint={
            "page": "project_detail",
            "project_id": "00000000-0000-0000-0000-000000000000",
        })
    assert ctx["project_id"] is None
    assert ctx["scope"] == "global"


def test_resolve_context_missing_hint(user):
    ctx = resolve_context(user=user, context_hint={})
    assert ctx["page"] == "unknown"
    assert ctx["scope"] == "global"
