"""P14: Voice action executor tests."""

import pytest
from django.utils import timezone

from accounts.models import User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Contact, Project
from projects.services.voice.action_executor import preview_action, confirm_action



@pytest.fixture
def user(db):
    u = User.objects.create_user(username="ae_tester", password="test1234")
    return u


@pytest.fixture
def client_obj(db):
    return Client.objects.create(name="레이언스")


@pytest.fixture
def project(db, client_obj, user):
    return Project.objects.create(
        client=client_obj
        title="AE Test",
        created_by=user)


@pytest.fixture
def candidate(db):
    return Candidate.objects.create(name="홍길동")


def test_preview_contact_record(project, candidate, user):
    result = preview_action(
        intent="contact_record",
        entities={
            "candidate_id": str(candidate.pk),
            "channel": "전화",
            "result": "관심",
            "contacted_at": timezone.now().isoformat(),
        },
        project=project,
        user=user)
    assert result["ok"] is True
    assert result["intent"] == "contact_record"
    assert "홍길동" in result["summary"]
    assert Contact.objects.filter(project=project, candidate=candidate).count() == 0


def test_confirm_contact_record(project, candidate, user):
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
        user=user)
    assert result["ok"] is True
    assert Contact.objects.filter(project=project, candidate=candidate).count() == 1
    contact = Contact.objects.get(project=project, candidate=candidate)
    assert contact.result == Contact.Result.INTERESTED
    assert contact.channel == Contact.Channel.PHONE


def test_preview_status_query(project, user):
    result = preview_action(
        intent="status_query",
        entities={"project_name": project.title},
        project=project,
        user=user)
    assert result["ok"] is True
    assert result["intent"] == "status_query"


def test_preview_navigate(user):
    result = preview_action(
        intent="navigate",
        entities={"target_page": "projects"},
        project=None,
        user=user)
    assert result["ok"] is True
    assert result["url"] is not None


# Amendment A1: Test new intents
def test_preview_project_create(user, client_obj):
    result = preview_action(
        intent="project_create",
        entities={"client": "레이언스", "title": "신규 프로젝트"},
        project=None,
        user=user)
    assert result["ok"] is True
    assert result["intent"] == "project_create"


def test_confirm_project_create(user, client_obj):
    result = confirm_action(
        intent="project_create",
        entities={"client": "레이언스", "title": "신규 프로젝트"},
        project=None,
        user=user)
    assert result["ok"] is True
    from projects.models import Project as P

    assert P.objects.filter(title="신규 프로젝트").exists()


# Amendment A5: search returns inline results
def test_preview_search(user, candidate):
    result = preview_action(
        intent="search_candidate",
        entities={"keywords": "홍길동"},
        project=None,
        user=user)
    assert result["ok"] is True
    assert result["intent"] == "search_candidate"


# Amendment A6: contact_record with duplicate check
def test_confirm_contact_record_releases_reserved(project, candidate, user):
    # Create a RESERVED lock first
    Contact.objects.create(
        project=project,
        candidate=candidate,
        consultant=user,
        result=Contact.Result.RESERVED,
        channel=Contact.Channel.PHONE,
        locked_until=timezone.now() + timezone.timedelta(days=7))
    result = confirm_action(
        intent="contact_record",
        entities={
            "candidate_id": str(candidate.pk),
            "channel": "전화",
            "result": "관심",
        },
        project=project,
        user=user)
    assert result["ok"] is True
    # RESERVED lock should be released (locked_until <= now)
    reserved = Contact.objects.filter(
        project=project,
        candidate=candidate,
        result=Contact.Result.RESERVED).first()
    assert reserved.locked_until <= timezone.now()


# Amendment A12: submission_create rejects non-INTERESTED candidate
def test_preview_submission_create_rejects_non_interested(
    project, candidate, user
):
    result = preview_action(
        intent="submission_create",
        entities={"candidate_id": str(candidate.pk)},
        project=project,
        user=user)
    assert result["ok"] is False
    assert "관심" in result.get("error", "")


# Amendment A12: submission_create rejects duplicate submission
def test_preview_submission_create_rejects_duplicate(project, candidate, user):
    from projects.models import Submission

    Contact.objects.create(
        project=project,
        candidate=candidate,
        consultant=user,
        result=Contact.Result.INTERESTED,
        channel=Contact.Channel.PHONE)
    Submission.objects.create(
        project=project,
        candidate=candidate,
        consultant=user)
    result = preview_action(
        intent="submission_create",
        entities={"candidate_id": str(candidate.pk)},
        project=project,
        user=user)
    assert result["ok"] is False
    assert "이미" in result.get("error", "")


# Amendment A12: interview_schedule rejects non-PASSED submission
def test_preview_interview_schedule_rejects_no_passed(project, candidate, user):
    result = preview_action(
        intent="interview_schedule",
        entities={"candidate_id": str(candidate.pk)},
        project=project,
        user=user)
    assert result["ok"] is False


# Amendment A12: offer_create rejects non-eligible submission
def test_preview_offer_create_rejects_no_eligible(project, candidate, user):
    result = preview_action(
        intent="offer_create",
        entities={"candidate_id": str(candidate.pk)},
        project=project,
        user=user)
    assert result["ok"] is False


# Amendment A12: todo_query
def test_preview_todo_query(user):
    result = preview_action(
        intent="todo_query",
        entities={},
        project=None,
        user=user)
    assert result["ok"] is True
    assert result["intent"] == "todo_query"


# Amendment A12: meeting_navigate
def test_preview_meeting_navigate(user):
    result = preview_action(
        intent="meeting_navigate",
        entities={},
        project=None,
        user=user)
    assert result["ok"] is True
    assert result["action"] == "show_meeting_panel"


# Amendment A12: contact_reserve
def test_confirm_contact_reserve(project, candidate, user):
    result = confirm_action(
        intent="contact_reserve",
        entities={"candidate_ids": [str(candidate.pk)]},
        project=project,
        user=user)
    assert result["ok"] is True
    assert Contact.objects.filter(
        project=project,
        candidate=candidate,
        result=Contact.Result.RESERVED).exists()
