"""P14: MeetingRecord model tests."""

import pytest
from unittest.mock import MagicMock, patch

from django.utils import timezone

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Contact, MeetingRecord, Project
from projects.services.voice.meeting_analyzer import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    analyze_meeting,
    apply_meeting_insights,
    validate_meeting_file,
)


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


# ---------------------------------------------------------------------------
# Meeting Analyzer tests
# ---------------------------------------------------------------------------


def test_constants_exported():
    assert ".mp3" in ALLOWED_EXTENSIONS
    assert MAX_FILE_SIZE == 100 * 1024 * 1024


def test_validate_meeting_file_valid():
    f = MagicMock()
    f.name = "meeting.mp3"
    f.size = 50 * 1024 * 1024  # 50MB
    errors = validate_meeting_file(f)
    assert errors == []


def test_validate_meeting_file_too_large():
    f = MagicMock()
    f.name = "meeting.mp3"
    f.size = 200 * 1024 * 1024  # 200MB
    errors = validate_meeting_file(f)
    assert len(errors) == 1
    assert "크기" in errors[0]


def test_validate_meeting_file_bad_extension():
    f = MagicMock()
    f.name = "meeting.exe"
    f.size = 1024
    errors = validate_meeting_file(f)
    assert len(errors) == 1
    assert "형식" in errors[0]


@patch("projects.services.voice.meeting_analyzer._get_gemini_client")
@patch("projects.services.voice.meeting_analyzer.transcribe")
def test_analyze_meeting(mock_transcribe, mock_gemini_fn, project, candidate, user):
    record = MeetingRecord.objects.create(
        project=project,
        candidate=candidate,
        audio_file="meetings/audio/test.webm",
        created_by=user,
    )

    mock_transcribe.return_value = "현재 연봉은 8천만원이고 이직 의향이 있습니다."

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"interest_level": "높음", "current_salary": "8천만원", "desired_salary": "", "available_date": "", "career_highlights": "", "concerns": "", "action_items": "", "mood": "긍정적", "notes": ""}'
    mock_client.models.generate_content.return_value = mock_response
    mock_gemini_fn.return_value = mock_client

    analyze_meeting(record.pk)

    record.refresh_from_db()
    assert record.status == MeetingRecord.Status.READY
    assert record.transcript != ""
    assert record.analysis_json.get("interest_level") == "높음"


def test_apply_meeting_insights_notes(project, candidate, user):
    """Test that selected non-special fields are appended to contact notes."""
    record = MeetingRecord.objects.create(
        project=project,
        candidate=candidate,
        audio_file="meetings/audio/test.webm",
        status=MeetingRecord.Status.READY,
        analysis_json={
            "interest_level": "높음",
            "current_salary": "8천만원",
            "desired_salary": "1억",
            "mood": "긍정적",
        },
        created_by=user,
    )

    selected = ["current_salary", "desired_salary"]
    apply_meeting_insights(record=record, selected_fields=selected, user=user)

    record.refresh_from_db()
    assert record.status == MeetingRecord.Status.APPLIED
    assert record.applied_by == user
    assert record.applied_at is not None

    contact = Contact.objects.filter(project=project, candidate=candidate).first()
    assert contact is not None
    assert "8천만원" in contact.notes


# Amendment A11: interest_level -> Contact.result
def test_apply_meeting_insights_interest_level(project, candidate, user):
    # First create a contact to update
    Contact.objects.create(
        project=project,
        candidate=candidate,
        consultant=user,
        channel="전화",
        result=Contact.Result.RESPONDED,
        contacted_at=timezone.now(),
    )
    record = MeetingRecord.objects.create(
        project=project,
        candidate=candidate,
        audio_file="meetings/audio/test.webm",
        status=MeetingRecord.Status.READY,
        analysis_json={"interest_level": "높음"},
        created_by=user,
    )
    apply_meeting_insights(record=record, selected_fields=["interest_level"], user=user)
    contact = (
        Contact.objects.filter(
            project=project,
            candidate=candidate,
        )
        .exclude(result=Contact.Result.RESERVED)
        .order_by("-contacted_at")
        .first()
    )
    assert contact.result == Contact.Result.INTERESTED


# Amendment A11: mood -> not applied to DB
def test_apply_meeting_insights_mood_skipped(project, candidate, user):
    record = MeetingRecord.objects.create(
        project=project,
        candidate=candidate,
        audio_file="meetings/audio/test.webm",
        status=MeetingRecord.Status.READY,
        analysis_json={"mood": "긍정적"},
        created_by=user,
    )
    apply_meeting_insights(record=record, selected_fields=["mood"], user=user)
    record.refresh_from_db()
    assert record.status == MeetingRecord.Status.APPLIED
    # No contact created for mood-only
    assert Contact.objects.filter(project=project, candidate=candidate).count() == 0


# Amendment A11: action_items -> RESERVED Contact
def test_apply_meeting_insights_action_items(project, candidate, user):
    record = MeetingRecord.objects.create(
        project=project,
        candidate=candidate,
        audio_file="meetings/audio/test.webm",
        status=MeetingRecord.Status.READY,
        analysis_json={"action_items": "1주일 후 팔로업 전화"},
        created_by=user,
    )
    apply_meeting_insights(record=record, selected_fields=["action_items"], user=user)
    reserved = Contact.objects.filter(
        project=project,
        candidate=candidate,
        result=Contact.Result.RESERVED,
    ).first()
    assert reserved is not None
    assert "액션 아이템" in reserved.notes


# Amendment A12: duration validation (mock ffprobe)
@patch("projects.services.voice.meeting_analyzer._get_audio_duration")
def test_validate_meeting_file_duration_too_long(mock_duration):
    mock_duration.return_value = 130 * 60.0  # 130 minutes > 120 max
    f = MagicMock()
    f.name = "meeting.mp3"
    f.size = 50 * 1024 * 1024
    f.temporary_file_path.return_value = "/tmp/test.mp3"
    errors = validate_meeting_file(f)
    assert any("120" in e for e in errors)


# Amendment A12: candidate ownership validation in upload view
@pytest.mark.django_db
def test_meeting_upload_invalid_candidate(
    project, candidate, user, org, settings, tmp_path
):
    """Upload with candidate not owned by org returns 404."""
    import json

    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.test import Client as TestClient

    settings.STORAGES = {
        **getattr(settings, "STORAGES", {}),
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path)},
        },
    }

    other_org = Organization.objects.create(name="Other Org")
    other_candidate = Candidate.objects.create(name="외부인", owned_by=other_org)

    c = TestClient()
    c.login(username="voice_tester", password="test1234")

    audio = SimpleUploadedFile(
        "meeting.mp3", b"fake audio data", content_type="audio/mpeg"
    )
    resp = c.post(
        "/voice/meeting-upload/",
        {
            "audio": audio,
            "project_id": str(project.pk),
            "candidate_id": str(other_candidate.pk),
        },
    )

    data = json.loads(resp.content)
    assert resp.status_code == 404
    assert "후보자" in data.get("error", "")


# Amendment A12: async processing kickoff test
@pytest.mark.django_db
@patch("projects.views_voice.analyze_meeting")
def test_meeting_upload_starts_async_processing(
    mock_analyze, project, candidate, user, org, settings, tmp_path
):
    """Upload triggers async analysis thread."""
    import json
    import time

    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.test import Client as TestClient

    # Configure default storage to use temp dir for file uploads
    settings.STORAGES = {
        **getattr(settings, "STORAGES", {}),
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path)},
        },
    }

    c = TestClient()
    c.login(username="voice_tester", password="test1234")

    audio = SimpleUploadedFile(
        "meeting.mp3", b"fake audio data", content_type="audio/mpeg"
    )
    resp = c.post(
        "/voice/meeting-upload/",
        {
            "audio": audio,
            "project_id": str(project.pk),
            "candidate_id": str(candidate.pk),
        },
    )

    data = json.loads(resp.content)
    assert resp.status_code == 200
    assert data["ok"] is True
    assert "meeting_id" in data
    # Give async thread time to call analyze_meeting
    time.sleep(0.5)
    assert mock_analyze.called
