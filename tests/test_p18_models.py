"""P18: Model tests for ResumeUpload and EmailMonitorConfig."""

import uuid

import pytest
from django.db import IntegrityError

from accounts.models import EmailMonitorConfig, User
from clients.models import Client
from projects.models import Project, ProjectStatus, ResumeUpload
from projects.services.resume.transitions import (
    ALLOWED_TRANSITIONS,
    transition_status)



@pytest.fixture
def user(db):
    u = User.objects.create_user(username="consultant1", password="testpass123")
    return u


@pytest.fixture
def client_company(db):
    return Client.objects.create(name="Rayence")


@pytest.fixture
def project(db, client_company, user):
    return Project.objects.create(
        client=client_company
        title="Test Project",
        status=ProjectStatus.SEARCHING,
        created_by=user)


class TestResumeUploadCreation:
    def test_create_with_all_fields(self, project, user):
        upload = ResumeUpload.objects.create(
            project=project,
            file_name="resume.pdf",
            file_type=ResumeUpload.FileType.PDF,
            source=ResumeUpload.Source.MANUAL,
            status=ResumeUpload.Status.PENDING,
            upload_batch=uuid.uuid4(),
            created_by=user,
            email_subject="Test subject",
            email_from="test@example.com",
            email_message_id="msg123",
            email_attachment_id="att456")
        assert upload.pk is not None
        assert isinstance(upload.pk, uuid.UUID)
        assert upload.created_at is not None
        assert upload.updated_at is not None
        assert upload.status == ResumeUpload.Status.PENDING
        assert upload.file_type == ResumeUpload.FileType.PDF
        assert upload.source == ResumeUpload.Source.MANUAL
        assert upload.retry_count == 0

    def test_unique_email_attachment_constraint(self, project, user):
        """Two uploads with same (org, email_message_id, email_attachment_id, source=email) should raise IntegrityError."""
        common = dict(
            project=project,
            file_name="resume.pdf",
            file_type=ResumeUpload.FileType.PDF,
            source=ResumeUpload.Source.EMAIL,
            status=ResumeUpload.Status.PENDING,
            email_message_id="msg-001",
            email_attachment_id="att-001",
            created_by=user)
        ResumeUpload.objects.create(**common)
        with pytest.raises(IntegrityError):
            ResumeUpload.objects.create(**common)

    def test_base_model_uuid_pk(self, user):
        upload = ResumeUpload.objects.create(
            file_name="test.docx",
            file_type=ResumeUpload.FileType.DOCX,
            created_by=user)
        assert isinstance(upload.pk, uuid.UUID)

    def test_base_model_timestamps(self, user):
        upload = ResumeUpload.objects.create(
            file_name="test.doc",
            file_type=ResumeUpload.FileType.DOC,
            created_by=user)
        assert upload.created_at is not None
        assert upload.updated_at is not None


class TestEmailMonitorConfigEncryption:
    def test_credential_encryption_roundtrip(self, user):
        config = EmailMonitorConfig.objects.create(
            user=user,
            gmail_credentials=b"placeholder")
        creds = {
            "access_token": "ya29.secret",
            "refresh_token": "1//0frefresh",
            "client_id": "123.apps.googleusercontent.com",
            "client_secret": "GOCSPX-secret",
        }
        config.set_credentials(creds)
        config.save()

        config.refresh_from_db()
        decrypted = config.get_credentials()
        assert decrypted == creds
        assert decrypted["access_token"] == "ya29.secret"


class TestStateTransitions:
    def test_valid_transitions(self, user):
        upload = ResumeUpload.objects.create(
            file_name="valid.pdf",
            file_type=ResumeUpload.FileType.PDF,
            status=ResumeUpload.Status.PENDING,
            created_by=user)
        # pending -> extracting
        upload = transition_status(upload, ResumeUpload.Status.EXTRACTING)
        assert upload.status == ResumeUpload.Status.EXTRACTING

        # extracting -> extracted
        upload = transition_status(upload, ResumeUpload.Status.EXTRACTED)
        assert upload.status == ResumeUpload.Status.EXTRACTED

        # extracted -> linked
        upload = transition_status(upload, ResumeUpload.Status.LINKED)
        assert upload.status == ResumeUpload.Status.LINKED

    def test_invalid_transition_raises(self, user):
        upload = ResumeUpload.objects.create(
            file_name="invalid.pdf",
            file_type=ResumeUpload.FileType.PDF,
            status=ResumeUpload.Status.PENDING,
            created_by=user)
        # pending -> linked is not allowed
        with pytest.raises(ValueError, match="Invalid transition"):
            transition_status(upload, ResumeUpload.Status.LINKED)

    def test_terminal_states_have_no_transitions(self):
        assert ALLOWED_TRANSITIONS[ResumeUpload.Status.LINKED] == set()
        assert ALLOWED_TRANSITIONS[ResumeUpload.Status.DISCARDED] == set()

    def test_failed_to_pending_retry(self, user):
        upload = ResumeUpload.objects.create(
            file_name="fail.pdf",
            file_type=ResumeUpload.FileType.PDF,
            status=ResumeUpload.Status.PENDING,
            created_by=user)
        upload = transition_status(upload, ResumeUpload.Status.EXTRACTING)
        upload = transition_status(upload, ResumeUpload.Status.FAILED)
        # failed -> pending (retry)
        upload = transition_status(upload, ResumeUpload.Status.PENDING)
        assert upload.status == ResumeUpload.Status.PENDING
