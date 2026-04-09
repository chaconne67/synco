"""P14: Voice action executor tests."""

import pytest
from django.utils import timezone

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Contact, Project
from projects.services.voice.action_executor import preview_action, confirm_action


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="ae_tester", password="test1234")
    Membership.objects.create(user=u, organization=org)
    return u


@pytest.fixture
def client_obj(db, org):
    return Client.objects.create(name="레이언스", organization=org)


@pytest.fixture
def project(db, org, client_obj, user):
    return Project.objects.create(
        client=client_obj,
        organization=org,
        title="AE Test",
        created_by=user,
    )


@pytest.fixture
def candidate(db, org):
    return Candidate.objects.create(name="홍길동", owned_by=org)


def test_preview_contact_record(project, candidate, user, org):
    result = preview_action(
        intent="contact_record",
        entities={
            "candidate_id": str(candidate.pk),
            "channel": "전화",
            "result": "관심",
            "contacted_at": timezone.now().isoformat(),
        },
        project=project,
        user=user,
        organization=org,
    )
    assert result["ok"] is True
    assert result["intent"] == "contact_record"
    assert "홍길동" in result["summary"]
    assert Contact.objects.filter(project=project, candidate=candidate).count() == 0


def test_confirm_contact_record(project, candidate, user, org):
    now = timezone.now()
    entities = {
        "candidate_id": str(candidate.pk),
        "channel": "전화",
        "result": "관심",
        "contacted_at": now.isoformat(),
    }
    result = confirm_action(
        intent="contact_record",
        entities=entities,
        project=project,
        user=user,
        organization=org,
    )
    assert result["ok"] is True
    assert Contact.objects.filter(project=project, candidate=candidate).count() == 1
    contact = Contact.objects.get(project=project, candidate=candidate)
    assert contact.result == Contact.Result.INTERESTED
    assert contact.channel == Contact.Channel.PHONE


def test_preview_status_query(project, user, org):
    result = preview_action(
        intent="status_query",
        entities={"project_name": project.title},
        project=project,
        user=user,
        organization=org,
    )
    assert result["ok"] is True
    assert result["intent"] == "status_query"


def test_preview_navigate(user, org):
    result = preview_action(
        intent="navigate",
        entities={"target_page": "projects"},
        project=None,
        user=user,
        organization=org,
    )
    assert result["ok"] is True
    assert result["url"] is not None


# Amendment A1: Test new intents
def test_preview_project_create(user, org, client_obj):
    result = preview_action(
        intent="project_create",
        entities={"client": "레이언스", "title": "신규 프로젝트"},
        project=None,
        user=user,
        organization=org,
    )
    assert result["ok"] is True
    assert result["intent"] == "project_create"


def test_confirm_project_create(user, org, client_obj):
    result = confirm_action(
        intent="project_create",
        entities={"client": "레이언스", "title": "신규 프로젝트"},
        project=None,
        user=user,
        organization=org,
    )
    assert result["ok"] is True
    from projects.models import Project as P

    assert P.objects.filter(title="신규 프로젝트").exists()


# Amendment A5: search returns inline results
def test_preview_search(user, org, candidate):
    result = preview_action(
        intent="search_candidate",
        entities={"keywords": "홍길동"},
        project=None,
        user=user,
        organization=org,
    )
    assert result["ok"] is True
    assert result["intent"] == "search_candidate"


# Amendment A6: contact_record with duplicate check
def test_confirm_contact_record_releases_reserved(project, candidate, user, org):
    # Create a RESERVED lock first
    Contact.objects.create(
        project=project,
        candidate=candidate,
        consultant=user,
        result=Contact.Result.RESERVED,
        channel=Contact.Channel.PHONE,
        locked_until=timezone.now() + timezone.timedelta(days=7),
    )
    result = confirm_action(
        intent="contact_record",
        entities={
            "candidate_id": str(candidate.pk),
            "channel": "전화",
            "result": "관심",
        },
        project=project,
        user=user,
        organization=org,
    )
    assert result["ok"] is True
    # RESERVED lock should be released (locked_until <= now)
    reserved = Contact.objects.filter(
        project=project,
        candidate=candidate,
        result=Contact.Result.RESERVED,
    ).first()
    assert reserved.locked_until <= timezone.now()
