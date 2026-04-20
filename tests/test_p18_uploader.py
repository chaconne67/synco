"""P18: Uploader service tests — validate_file, create_upload, process_pending_upload."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import User
from clients.models import Client
from projects.models import Project, ProjectStatus, ResumeUpload
from projects.services.resume.uploader import (
    FileValidationError,
    create_upload,
    process_pending_upload,
    validate_file)



@pytest.fixture
def user(db):
    u = User.objects.create_user(username="consultant1", password="testpass123", level=1)
    return u


@pytest.fixture
def client_company(db):
    return Client.objects.create(name="Rayence")


@pytest.fixture
def project(db, client_company, user):
    return Project.objects.create(
        client=client_company,
        title="Test Project",
        status=ProjectStatus.OPEN,
        created_by=user)


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


class TestValidateFile:
    def test_valid_pdf_accepted(self):
        f = SimpleUploadedFile(
            "resume.pdf", b"fake pdf", content_type="application/pdf"
        )
        ext, file_type = validate_file(f)
        assert ext == ".pdf"
        assert file_type == ResumeUpload.FileType.PDF

    def test_valid_docx_accepted(self):
        f = SimpleUploadedFile(
            "resume.docx",
            b"fake docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        ext, file_type = validate_file(f)
        assert ext == ".docx"
        assert file_type == ResumeUpload.FileType.DOCX

    def test_valid_doc_accepted(self):
        f = SimpleUploadedFile(
            "resume.doc",
            b"fake doc",
            content_type="application/msword")
        ext, file_type = validate_file(f)
        assert ext == ".doc"
        assert file_type == ResumeUpload.FileType.DOC

    def test_oversized_file_rejected(self):
        # 21MB file
        f = SimpleUploadedFile(
            "big.pdf",
            b"x" * (21 * 1024 * 1024),
            content_type="application/pdf")
        with pytest.raises(FileValidationError, match="20MB"):
            validate_file(f)

    def test_wrong_extension_rejected(self):
        f = SimpleUploadedFile("resume.txt", b"text", content_type="text/plain")
        with pytest.raises(FileValidationError, match="지원하지 않는"):
            validate_file(f)

    def test_wrong_mime_type_rejected(self):
        f = SimpleUploadedFile("resume.pdf", b"fake", content_type="text/plain")
        with pytest.raises(FileValidationError, match="잘못된 파일"):
            validate_file(f)


class TestCreateUpload:
    def test_creates_pending_upload(self, project, user, media_root):
        f = SimpleUploadedFile(
            "resume.pdf", b"fake pdf", content_type="application/pdf"
        )
        batch = uuid.uuid4()
        upload = create_upload(
            file=f,
            project=project,
            user=user,
            upload_batch=batch)
        assert upload.status == ResumeUpload.Status.PENDING
        assert upload.file_name == "resume.pdf"
        assert upload.file_type == ResumeUpload.FileType.PDF
        assert upload.upload_batch == batch
        assert upload.project == project


class TestProcessPendingUpload:
    @pytest.fixture
    def pending_upload(self, project, user, media_root):
        f = SimpleUploadedFile(
            "resume.pdf", b"fake pdf", content_type="application/pdf"
        )
        return create_upload(
            file=f,
            project=project,
            user=user,
            upload_batch=uuid.uuid4())

    @patch(
        "projects.services.resume.uploader.identify_candidate_for_org",
        return_value=None)
    @patch(
        "projects.services.resume.uploader.run_extraction_with_retry",
        return_value={
            "extracted": {"name": "김철수", "email": "test@example.com"},
            "raw_text_used": "resume text",
            "diagnosis": {"verdict": "pass"},
        })
    @patch("projects.services.resume.uploader.parse_filename", return_value={})
    @patch(
        "projects.services.resume.uploader.preprocess_resume_text",
        side_effect=lambda x: x)
    @patch(
        "projects.services.resume.uploader.extract_text", return_value="resume raw text"
    )
    def test_successful_extraction(
        self,
        mock_extract,
        mock_preprocess,
        mock_parse,
        mock_run,
        mock_identify,
        pending_upload):
        result = process_pending_upload(pending_upload)
        result.refresh_from_db()
        assert result.status == ResumeUpload.Status.EXTRACTED
        assert result.extraction_result["extracted"]["name"] == "김철수"

    @patch(
        "projects.services.resume.uploader.extract_text",
        side_effect=Exception("Parse error"))
    def test_extraction_failure(self, mock_extract, pending_upload):
        result = process_pending_upload(pending_upload)
        result.refresh_from_db()
        assert result.status == ResumeUpload.Status.FAILED
        assert "Parse error" in result.error_message

    @patch("projects.services.resume.uploader.identify_candidate_for_org")
    @patch(
        "projects.services.resume.uploader.run_extraction_with_retry",
        return_value={
            "extracted": {"name": "김철수", "email": "dup@example.com"},
            "raw_text_used": "resume text",
            "diagnosis": {"verdict": "pass"},
        })
    @patch("projects.services.resume.uploader.parse_filename", return_value={})
    @patch(
        "projects.services.resume.uploader.preprocess_resume_text",
        side_effect=lambda x: x)
    @patch(
        "projects.services.resume.uploader.extract_text", return_value="resume raw text"
    )
    def test_duplicate_detected(
        self,
        mock_extract,
        mock_preprocess,
        mock_parse,
        mock_run,
        mock_identify,
        pending_upload):
        """Extraction succeeds then identity match marks as duplicate."""
        mock_context = MagicMock()
        mock_context.candidate = MagicMock()
        mock_identify.return_value = mock_context

        result = process_pending_upload(pending_upload)
        result.refresh_from_db()
        assert result.status == ResumeUpload.Status.DUPLICATE
