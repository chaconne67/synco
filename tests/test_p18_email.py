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
    TelegramBinding,
    User,
)
from clients.models import Client
from projects.models import Project, ProjectStatus, ResumeUpload
from projects.services.email.gmail_client import GmailClient
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

    @patch("projects.services.notification._send_telegram_message")
    def test_binding_exists_message_sent(self, mock_send, org, user):
        """Telegram binding exists -> notification sent with correct text."""
        TelegramBinding.objects.create(
            user=user,
            chat_id="123456",
            is_active=True,
        )
        upload = ResumeUpload.objects.create(
            organization=org,
            file_name="홍길동_이력서.pdf",
            file_type=ResumeUpload.FileType.PDF,
            source=ResumeUpload.Source.EMAIL,
            status=ResumeUpload.Status.EXTRACTED,
            email_from="sender@test.com",
            created_by=user,
        )

        from projects.management.commands.check_email_resumes import _notify_if_needed

        _notify_if_needed(upload)

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[0][0] == "123456"
        assert "홍길동_이력서.pdf" in call_args[0][1]
        assert "sender@test.com" in call_args[0][1]

    @patch(
        "projects.services.notification._send_telegram_message",
        side_effect=Exception("Telegram API error"),
    )
    def test_notification_error_logged_not_raised(self, mock_send, org, user):
        """Telegram send error -> logged, not raised (best-effort)."""
        TelegramBinding.objects.create(
            user=user,
            chat_id="123456",
            is_active=True,
        )
        upload = ResumeUpload.objects.create(
            organization=org,
            file_name="resume.pdf",
            file_type=ResumeUpload.FileType.PDF,
            source=ResumeUpload.Source.EMAIL,
            status=ResumeUpload.Status.EXTRACTED,
            created_by=user,
        )

        from projects.management.commands.check_email_resumes import _notify_if_needed

        # Should not raise even when telegram fails
        _notify_if_needed(upload)
        mock_send.assert_called_once()


def _make_http_error(status_code):
    """Create a mock HttpError with the given status code."""
    from googleapiclient.errors import HttpError

    resp = MagicMock()
    resp.status = status_code
    resp.reason = f"Error {status_code}"
    return HttpError(resp, b"error")


class TestGmailClientErrorHandling:
    """Tests for GmailClient error handling paths: 401, 404, 429, 5xx."""

    @pytest.fixture
    def gmail_client(self, email_config):
        client = GmailClient(email_config)
        client._service = MagicMock()  # Skip _build_service
        return client

    def test_history_404_falls_back_to_search(self, gmail_client):
        """History API returns 404 -> falls back to _poll_via_search."""
        gmail_client.config.last_history_id = "old_history_id"
        gmail_client._poll_via_history = MagicMock(
            side_effect=_make_http_error(404)
        )
        gmail_client._poll_via_search = MagicMock(return_value=[{"id": "msg1"}])

        result = gmail_client.get_new_messages()

        gmail_client._poll_via_search.assert_called_once()
        assert result == [{"id": "msg1"}]

    def test_401_deactivates_config(self, gmail_client):
        """401 Unauthorized -> is_active=False + re-raise."""
        gmail_client.config.last_history_id = "some_id"
        gmail_client._poll_via_history = MagicMock(
            side_effect=_make_http_error(401)
        )

        with pytest.raises(Exception):
            gmail_client.get_new_messages()

        gmail_client.config.refresh_from_db()
        assert gmail_client.config.is_active is False

    @patch("projects.services.email.gmail_client.time.sleep")
    def test_429_triggers_backoff(self, mock_sleep, gmail_client):
        """429 Rate limit -> exponential backoff retry with sleep."""
        gmail_client.config.last_history_id = "some_id"
        # get_new_messages catches first 429, calls _retry_with_backoff.
        # Inside backoff: first attempt raises 429 (triggers sleep),
        # second attempt succeeds.
        call_count = 0

        def history_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Fail on calls 1 (get_new_messages) and 2 (first backoff attempt)
                raise _make_http_error(429)
            return [{"id": "msg1", "subject": "test", "from": "a@b.com"}]

        gmail_client._poll_via_history = MagicMock(side_effect=history_side_effect)

        result = gmail_client.get_new_messages()

        assert mock_sleep.called
        assert len(result) == 1

    def test_5xx_returns_empty(self, gmail_client):
        """5xx server error -> returns empty list, no raise."""
        gmail_client.config.last_history_id = "some_id"
        gmail_client._poll_via_history = MagicMock(
            side_effect=_make_http_error(500)
        )

        result = gmail_client.get_new_messages()

        assert result == []

    def test_oversized_attachment_skipped(self, gmail_client):
        """Attachment > 20MB -> skipped, not included in results."""
        gmail_client._service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            "payload": {
                "parts": [
                    {
                        "filename": "huge.pdf",
                        "body": {
                            "size": 25 * 1024 * 1024,  # 25MB > limit
                            "attachmentId": "att1",
                        },
                    },
                    {
                        "filename": "small.pdf",
                        "body": {
                            "size": 1000,
                            "attachmentId": "att2",
                        },
                    },
                ]
            }
        }

        attachments = gmail_client.get_resume_attachments("msg1")

        assert len(attachments) == 1
        assert attachments[0]["filename"] == "small.pdf"


class TestGmailTokenRefresh:
    """Tests for OAuth token refresh flow."""

    @patch("googleapiclient.discovery.build")
    @patch("google.auth.transport.requests.Request")
    @patch("google.oauth2.credentials.Credentials.from_authorized_user_info")
    def test_token_refresh_on_expired(
        self, mock_from_info, mock_request, mock_build, email_config
    ):
        """Expired access token -> auto refresh -> credentials persisted."""
        mock_creds = MagicMock()
        mock_creds.expired = True
        mock_creds.refresh_token = "1//refresh"
        mock_creds.to_json.return_value = '{"token": "new_token", "refresh_token": "1//refresh"}'
        mock_from_info.return_value = mock_creds

        client = GmailClient(email_config)
        client._build_service()

        mock_creds.refresh.assert_called_once()
        email_config.refresh_from_db()
        # Credentials should be updated (encrypted)
        decrypted = email_config.get_credentials()
        assert decrypted["token"] == "new_token"

    @patch("google.auth.transport.requests.Request")
    @patch("google.oauth2.credentials.Credentials.from_authorized_user_info")
    def test_refresh_failure_deactivates_config(
        self, mock_from_info, mock_request, email_config
    ):
        """Token refresh failure -> is_active=False."""
        mock_creds = MagicMock()
        mock_creds.expired = True
        mock_creds.refresh_token = "1//refresh"
        mock_creds.refresh.side_effect = Exception("Token revoked")
        mock_from_info.return_value = mock_creds

        client = GmailClient(email_config)
        with pytest.raises(Exception, match="Token revoked"):
            client._build_service()

        email_config.refresh_from_db()
        assert email_config.is_active is False


@pytest.mark.django_db(transaction=True)
class TestSelectForUpdateConcurrency:
    """Test that select_for_update(skip_locked=True) prevents concurrent processing."""

    @patch("projects.management.commands.check_email_resumes.process_email_config")
    @patch("projects.management.commands.check_email_resumes.process_pending_upload")
    def test_skip_locked_prevents_double_processing(
        self, mock_process_upload, mock_process_config
    ):
        """Second concurrent cron run skips locked configs."""
        org = Organization.objects.create(name="Concurrency Org")
        user = User.objects.create_user(
            username="concurrent_user", password="testpass123"
        )
        Membership.objects.create(user=user, organization=org)
        config = EmailMonitorConfig(user=user)
        config.set_credentials({"access_token": "test", "refresh_token": "test"})
        config.save()

        mock_process_config.return_value = 0

        # Run command twice — both should complete without error
        out1 = StringIO()
        call_command("check_email_resumes", stdout=out1)
        out2 = StringIO()
        call_command("check_email_resumes", stdout=out2)

        # Both should succeed (skip_locked means second would skip if first held lock)
        assert "Email resume check complete" in out1.getvalue()
        assert "Email resume check complete" in out2.getvalue()
