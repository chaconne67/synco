"""P18: Email integration tests — check_email_resumes command, Gmail client, monitor."""

import uuid
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.core.management import call_command

from accounts.models import (
    EmailMonitorConfig,
    Membership,
    Organization,
    User,
)
from clients.models import Client
from projects.models import Project, ProjectStatus, ResumeUpload
from projects.services.email.monitor import _match_project, process_email_config


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Org")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="consultant1", password="testpass123")
    Membership.objects.create(user=u, organization=org)
    return u


@pytest.fixture
def client_company(db, org):
    return Client.objects.create(name="Rayence", organization=org)


@pytest.fixture
def project(db, org, client_company, user):
    return Project.objects.create(
        client=client_company,
        organization=org,
        title="Test Project",
        status=ProjectStatus.SEARCHING,
        created_by=user,
    )


@pytest.fixture
def email_config(user):
    config = EmailMonitorConfig(user=user)
    config.set_credentials(
        {
            "access_token": "ya29.test",
            "refresh_token": "1//refresh",
            "client_id": "test.apps.googleusercontent.com",
            "client_secret": "secret",
        }
    )
    config.save()
    return config


@pytest.fixture
def media_root(tmp_path):
    """Configure default storage for file upload tests."""
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
    }
    return settings.MEDIA_ROOT


class TestCheckEmailResumesCommand:
    @patch("projects.management.commands.check_email_resumes.process_email_config")
    @patch("projects.management.commands.check_email_resumes.process_pending_upload")
    def test_command_with_mocked_gmail(
        self, mock_process_upload, mock_process_config, email_config
    ):
        mock_process_config.return_value = 2

        out = StringIO()
        call_command("check_email_resumes", stdout=out)

        mock_process_config.assert_called_once()
        assert "Email resume check complete" in out.getvalue()

    @patch("projects.management.commands.check_email_resumes.process_email_config")
    @patch("projects.management.commands.check_email_resumes.process_pending_upload")
    def test_command_handles_exception(
        self, mock_process_upload, mock_process_config, email_config
    ):
        mock_process_config.side_effect = Exception("Gmail error")

        out = StringIO()
        call_command("check_email_resumes", stdout=out)
        # Should not raise, just log and continue
        assert "Email resume check complete" in out.getvalue()


@pytest.mark.django_db(transaction=True)
class TestEmailDedup:
    @patch("projects.services.email.monitor.GmailClient")
    def test_integrity_error_caught_and_skipped(self, mock_gmail_cls, media_root):
        """Duplicate email attachment -> IntegrityError -> skipped."""
        # Create objects within the transactional test
        org = Organization.objects.create(name="Dedup Org")
        user = User.objects.create_user(username="dedup_user", password="testpass123")
        Membership.objects.create(user=user, organization=org)

        config = EmailMonitorConfig(user=user)
        config.set_credentials(
            {
                "access_token": "ya29.test",
                "refresh_token": "1//refresh",
                "client_id": "test.apps.googleusercontent.com",
                "client_secret": "secret",
            }
        )
        config.save()

        mock_client = MagicMock()
        mock_client.get_new_messages.return_value = [
            {"id": "msg1", "subject": "Resume", "from": "sender@test.com"},
        ]
        mock_client.get_resume_attachments.return_value = [
            {"id": "att1", "filename": "resume.pdf", "size": 1000},
        ]
        mock_client.download_attachment.return_value = b"fake pdf content"
        mock_gmail_cls.return_value = mock_client

        # Create first upload to cause IntegrityError on second
        ResumeUpload.objects.create(
            organization=org,
            file_name="resume.pdf",
            file_type=ResumeUpload.FileType.PDF,
            source=ResumeUpload.Source.EMAIL,
            status=ResumeUpload.Status.PENDING,
            email_message_id="msg1",
            email_attachment_id="att1",
            created_by=user,
        )

        # process_email_config should handle the IntegrityError gracefully
        count = process_email_config(config)
        assert count == 0  # Duplicate was skipped


class TestProjectMatching:
    def test_ref_uuid_matches_project(self, project, org):
        subject = f"New resume [REF-{project.pk}] attached"
        result = _match_project(subject, org)
        assert result == project

    def test_no_match_returns_none(self, org):
        subject = "New resume attached"
        result = _match_project(subject, org)
        assert result is None

    def test_wrong_uuid_returns_none(self, org):
        fake_uuid = uuid.uuid4()
        subject = f"Resume [REF-{fake_uuid}]"
        result = _match_project(subject, org)
        assert result is None


class TestTelegramNotification:
    def test_no_binding_skipped(self, org, user):
        """No telegram binding -> notification silently skipped."""
        upload = ResumeUpload.objects.create(
            organization=org,
            file_name="resume.pdf",
            file_type=ResumeUpload.FileType.PDF,
            source=ResumeUpload.Source.EMAIL,
            status=ResumeUpload.Status.EXTRACTED,
            created_by=user,
        )

        from projects.management.commands.check_email_resumes import _notify_if_needed

        # Should not raise even without binding
        _notify_if_needed(upload)
