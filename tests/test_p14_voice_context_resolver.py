"""P14: Voice context resolver tests."""

import pytest

from accounts.models import Membership, Organization, User
from clients.models import Client
from projects.models import Project
from projects.services.voice.context_resolver import resolve_context


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="ctx_tester", password="test1234")
    Membership.objects.create(user=u, organization=org)
    return u


@pytest.fixture
def client_obj(db, org):
    return Client.objects.create(name="Test Client", organization=org)


@pytest.fixture
def project(db, org, client_obj, user):
    return Project.objects.create(
        client=client_obj,
        organization=org,
        title="Context Test Project",
        created_by=user,
    )


def test_resolve_context_dashboard(user, org):
    ctx = resolve_context(
        user=user,
        organization=org,
        context_hint={"page": "dashboard"},
    )
    assert ctx["page"] == "dashboard"
    assert ctx["project_id"] is None
    assert ctx["scope"] == "global"


def test_resolve_context_project_detail(user, org, project):
    ctx = resolve_context(
        user=user,
        organization=org,
        context_hint={"page": "project_detail", "project_id": str(project.pk)},
    )
    assert ctx["page"] == "project_detail"
    assert ctx["project_id"] == project.pk
    assert ctx["scope"] == "project"
    assert ctx["project_title"] == project.title


def test_resolve_context_invalid_project(user, org):
    """Project not in user's org -> project_id is None."""
    ctx = resolve_context(
        user=user,
        organization=org,
        context_hint={
            "page": "project_detail",
            "project_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert ctx["project_id"] is None
    assert ctx["scope"] == "global"


def test_resolve_context_missing_hint(user, org):
    ctx = resolve_context(user=user, organization=org, context_hint={})
    assert ctx["page"] == "unknown"
    assert ctx["scope"] == "global"
