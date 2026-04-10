"""P18: View tests for resume upload, process, link, discard, retry, unassigned, assign."""

import uuid
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as TestClient

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Project, ProjectStatus, ResumeUpload
from projects.services.resume.transitions import transition_status


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Org")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="consultant1", password="testpass123")
    Membership.objects.create(user=u, organization=org)
    return u


@pytest.fixture
def other_org(db):
    return Organization.objects.create(name="Other Org")


@pytest.fixture
def other_org_user(db, other_org):
    u = User.objects.create_user(username="outsider", password="testpass123")
    Membership.objects.create(user=u, organization=other_org)
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
def auth_client(user):
    c = TestClient()
    c.force_login(user)
    return c


@pytest.fixture
def other_auth_client(other_org_user):
    c = TestClient()
    c.force_login(other_org_user)
    return c


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


class TestResumeUploadView:
    def test_upload_valid_file(self, auth_client, project, media_root):
        f = SimpleUploadedFile(
            "resume.pdf", b"fake pdf", content_type="application/pdf"
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/resumes/upload/",
            {"files": f},
        )
        assert resp.status_code == 200
        upload = ResumeUpload.objects.filter(project=project).first()
        assert upload is not None
        assert upload.status == ResumeUpload.Status.PENDING
        assert upload.file_name == "resume.pdf"

    def test_upload_oversized_file(self, auth_client, project, media_root):
        f = SimpleUploadedFile(
            "big.pdf",
            b"x" * (21 * 1024 * 1024),
            content_type="application/pdf",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/resumes/upload/",
            {"files": f},
        )
        assert resp.status_code == 200
        # No upload created, error returned in context
        assert ResumeUpload.objects.filter(project=project).count() == 0

    def test_upload_wrong_type(self, auth_client, project, media_root):
        f = SimpleUploadedFile("notes.txt", b"text file", content_type="text/plain")
        resp = auth_client.post(
            f"/projects/{project.pk}/resumes/upload/",
            {"files": f},
        )
        assert resp.status_code == 200
        assert ResumeUpload.objects.filter(project=project).count() == 0


def _mock_process(upload):
    """Helper to mock-process an upload to extracted status."""
    transition_status(upload, ResumeUpload.Status.EXTRACTING)
    transition_status(upload, ResumeUpload.Status.EXTRACTED)
    upload.refresh_from_db()
    return upload


class TestResumeProcessView:
    @patch("projects.views.process_pending_upload", side_effect=_mock_process)
    def test_process_pending_uploads(
        self, mock_process, auth_client, project, org, user, media_root
    ):
        f = SimpleUploadedFile(
            "resume.pdf", b"fake pdf", content_type="application/pdf"
        )
        batch_id = uuid.uuid4()
        ResumeUpload.objects.create(
            organization=org,
            project=project,
            file=f,
            file_name="resume.pdf",
            file_type=ResumeUpload.FileType.PDF,
            status=ResumeUpload.Status.PENDING,
            upload_batch=batch_id,
            created_by=user,
        )

        resp = auth_client.post(
            f"/projects/{project.pk}/resumes/process/",
            {"batch_id": str(batch_id)},
        )
        assert resp.status_code == 200


class TestResumeStatusView:
    def test_status_scoped_to_user_project_batch(self, auth_client, project, org, user):
        batch_id = uuid.uuid4()
        ResumeUpload.objects.create(
            organization=org,
            project=project,
            file_name="mine.pdf",
            file_type=ResumeUpload.FileType.PDF,
            status=ResumeUpload.Status.PENDING,
            upload_batch=batch_id,
            created_by=user,
        )

        resp = auth_client.get(
            f"/projects/{project.pk}/resumes/status/?batch={batch_id}",
        )
        assert resp.status_code == 200


def _mock_link(upload, candidate):
    """Helper to mock the link process."""
    upload.candidate = candidate
    upload.save(update_fields=["candidate", "updated_at"])
    transition_status(upload, ResumeUpload.Status.LINKED)
    upload.refresh_from_db()
    return upload


class TestResumeLinkView:
    @patch("projects.views.link_resume_to_candidate")
    def test_link_creates_candidate(
        self, mock_link, auth_client, project, org, user, media_root
    ):
        upload = ResumeUpload.objects.create(
            organization=org,
            project=project,
            file_name="resume.pdf",
            file_type=ResumeUpload.FileType.PDF,
            status=ResumeUpload.Status.PENDING,
            created_by=user,
            extraction_result={
                "extracted": {"name": "김철수", "email": "test@example.com"},
                "raw_text_used": "resume text",
                "diagnosis": {"verdict": "pass"},
            },
        )
        transition_status(upload, ResumeUpload.Status.EXTRACTING)
        transition_status(upload, ResumeUpload.Status.EXTRACTED)

        candidate = Candidate.objects.create(
            name="김철수",
            email="test@example.com",
            owned_by=org,
        )

        def do_link(u, **kwargs):
            return _mock_link(u, candidate)

        mock_link.side_effect = do_link

        resp = auth_client.post(
            f"/projects/{project.pk}/resumes/{upload.pk}/link/",
        )
        assert resp.status_code == 200


class TestResumeDiscardView:
    def test_discard_deletes_file(self, auth_client, project, org, user):
        upload = ResumeUpload.objects.create(
            organization=org,
            project=project,
            file_name="resume.pdf",
            file_type=ResumeUpload.FileType.PDF,
            status=ResumeUpload.Status.PENDING,
            created_by=user,
        )
        transition_status(upload, ResumeUpload.Status.EXTRACTING)
        transition_status(upload, ResumeUpload.Status.EXTRACTED)

        resp = auth_client.post(
            f"/projects/{project.pk}/resumes/{upload.pk}/discard/",
        )
        assert resp.status_code == 200
        upload.refresh_from_db()
        assert upload.status == ResumeUpload.Status.DISCARDED


class TestResumeRetryView:
    @patch("projects.views.process_pending_upload", side_effect=lambda u: u)
    def test_retry_increments_count(
        self, mock_process, auth_client, project, org, user, media_root
    ):
        upload = ResumeUpload.objects.create(
            organization=org,
            project=project,
            file_name="resume.pdf",
            file_type=ResumeUpload.FileType.PDF,
            status=ResumeUpload.Status.PENDING,
            created_by=user,
        )
        transition_status(upload, ResumeUpload.Status.EXTRACTING)
        transition_status(upload, ResumeUpload.Status.FAILED)

        resp = auth_client.post(
            f"/projects/{project.pk}/resumes/{upload.pk}/retry/",
        )
        assert resp.status_code == 200
        upload.refresh_from_db()
        assert upload.retry_count == 1

    def test_retry_max_exceeded(self, auth_client, project, org, user):
        upload = ResumeUpload.objects.create(
            organization=org,
            project=project,
            file_name="resume.pdf",
            file_type=ResumeUpload.FileType.PDF,
            status=ResumeUpload.Status.FAILED,
            retry_count=3,
            created_by=user,
        )

        resp = auth_client.post(
            f"/projects/{project.pk}/resumes/{upload.pk}/retry/",
        )
        assert resp.status_code == 400


class TestAuthorization:
    def test_wrong_org_returns_404(self, other_auth_client, project):
        resp = other_auth_client.get(
            f"/projects/{project.pk}/resumes/status/",
        )
        assert resp.status_code == 404


class TestUnassignedResumes:
    def test_unassigned_list(self, auth_client, org, user):
        ResumeUpload.objects.create(
            organization=org,
            project=None,
            file_name="orphan.pdf",
            file_type=ResumeUpload.FileType.PDF,
            status=ResumeUpload.Status.EXTRACTED,
            created_by=user,
        )
        resp = auth_client.get("/projects/resumes/unassigned/")
        assert resp.status_code == 200


class TestAssignToProject:
    def test_assign_updates_project(self, auth_client, org, user, project):
        upload = ResumeUpload.objects.create(
            organization=org,
            project=None,
            file_name="orphan.pdf",
            file_type=ResumeUpload.FileType.PDF,
            status=ResumeUpload.Status.EXTRACTED,
            created_by=user,
        )

        resp = auth_client.post(
            f"/projects/resumes/{upload.pk}/assign/{project.pk}/",
        )
        assert resp.status_code == 200
        upload.refresh_from_db()
        assert upload.project == project
