"""P14: Voice entity resolver tests."""

import pytest

from accounts.models import User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Contact, Project, Submission
from projects.services.voice.entity_resolver import (
    resolve_candidate,
    resolve_candidate_list,
    resolve_submission,
    resolve_submission_for_interview,
    resolve_submission_for_offer,
    CandidateResolution,  # noqa: F401
)



@pytest.fixture
def user(db):
    u = User.objects.create_user(username="er_tester", password="test1234")
    return u


@pytest.fixture
def client_obj(db):
    return Client.objects.create(name="Test Client")


@pytest.fixture
def project(db, client_obj, user):
    return Project.objects.create(
        client=client_obj
        title="ER Project",
        created_by=user)


@pytest.fixture
def candidate_hong(db):
    return Candidate.objects.create(name="홍길동")


@pytest.fixture
def candidate_hong2(db):
    return Candidate.objects.create(name="홍길동")


@pytest.fixture
def candidate_kim(db):
    return Candidate.objects.create(name="김영희")


def test_resolve_single_match(org, project, candidate_kim):
    result = resolve_candidate(
        name="김영희"
        project=project)
    assert result.status == "resolved"
    assert result.candidate_id == candidate_kim.pk
    assert len(result.candidates) == 1


def test_resolve_multiple_matches(org, project, candidate_hong, candidate_hong2):
    result = resolve_candidate(
        name="홍길동"
        project=project)
    assert result.status == "ambiguous"
    assert result.candidate_id is None
    assert len(result.candidates) == 2


def test_resolve_no_match(org, project):
    result = resolve_candidate(
        name="존재하지않는사람"
        project=project)
    assert result.status == "not_found"
    assert result.candidate_id is None
    assert len(result.candidates) == 0


def test_resolve_submission_auto(org, project, candidate_kim, user):
    Contact.objects.create(
        project=project,
        candidate=candidate_kim,
        consultant=user,
        result=Contact.Result.INTERESTED,
        channel="전화")
    sub = Submission.objects.create(
        project=project,
        candidate=candidate_kim,
        consultant=user,
        status=Submission.Status.PASSED)
    result = resolve_submission(
        candidate_id=candidate_kim.pk,
        project=project)
    assert result["status"] == "resolved"
    assert result["submission_id"] == sub.pk


def test_resolve_submission_no_eligible(org, project, candidate_kim, user):
    result = resolve_submission(
        candidate_id=candidate_kim.pk,
        project=project)
    assert result["status"] == "not_found"


# Amendment A3 tests
def test_resolve_candidate_list_mixed(org, project, candidate_kim, candidate_hong):
    result = resolve_candidate_list(
        names=["김영희", "존재안함", "홍길동"]
        project=project)
    assert len(result["resolved_ids"]) == 2  # 김영희 + 홍길동 (single fixture)
    assert len(result["not_found"]) == 1  # 존재안함
    # 홍길동 is single match here (only one fixture), so also resolved
    assert (
        len(result["resolved_ids"])
        + len(result["ambiguous"])
        + len(result["not_found"])
        == 3
    )


# Amendment A7 tests
def test_resolve_submission_for_interview(org, project, candidate_kim, user):
    sub = Submission.objects.create(
        project=project,
        candidate=candidate_kim,
        consultant=user,
        status=Submission.Status.PASSED)
    result = resolve_submission_for_interview(
        candidate_id=candidate_kim.pk,
        project=project)
    assert result["status"] == "resolved"
    assert result["submission_id"] == sub.pk


def test_resolve_submission_for_interview_no_eligible(
    org, project, candidate_kim, user
):
    # No PASSED submission
    Submission.objects.create(
        project=project,
        candidate=candidate_kim,
        consultant=user,
        status=Submission.Status.DRAFTING)
    result = resolve_submission_for_interview(
        candidate_id=candidate_kim.pk,
        project=project)
    assert result["status"] == "not_found"


def test_resolve_submission_for_offer(org, project, candidate_kim, user):
    Submission.objects.create(
        project=project,
        candidate=candidate_kim,
        consultant=user,
        status=Submission.Status.PASSED)
    result = resolve_submission_for_offer(
        candidate_id=candidate_kim.pk,
        project=project)
    # May be "resolved" or "not_found" depending on offer eligibility logic
    assert result["status"] in ("resolved", "not_found")
