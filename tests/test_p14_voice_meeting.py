"""P14: MeetingRecord model tests."""
import pytest

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import MeetingRecord, Project


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="voice_tester", password="test1234")
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
        title="Voice Agent Test Project",
        created_by=user,
    )


@pytest.fixture
def candidate(db, org):
    return Candidate.objects.create(name="홍길동", owned_by=org)


def test_meeting_record_creation(project, candidate, user):
    record = MeetingRecord.objects.create(
        project=project,
        candidate=candidate,
        audio_file="meetings/audio/test.webm",
        created_by=user,
    )
    assert record.status == MeetingRecord.Status.UPLOADED
    assert record.transcript == ""
    assert record.analysis_json == {}
    assert record.edited_json == {}
    assert record.error_message == ""
    assert record.applied_at is None
    assert record.applied_by is None


def test_meeting_record_status_transitions(project, candidate, user):
    record = MeetingRecord.objects.create(
        project=project,
        candidate=candidate,
        audio_file="meetings/audio/test.webm",
        created_by=user,
    )
    # Simulate status progression
    for status in ["transcribing", "analyzing", "ready"]:
        record.status = status
        record.save()
        record.refresh_from_db()
        assert record.status == status
