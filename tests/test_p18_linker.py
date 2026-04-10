"""P18: Linker service tests — link_resume_to_candidate."""

import uuid
from unittest.mock import patch

import pytest

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Contact, Project, ProjectStatus, ResumeUpload
from projects.services.resume.linker import link_resume_to_candidate
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
def extracted_upload(project, org, user):
    """A ResumeUpload in 'extracted' status with extraction_result."""
    upload = ResumeUpload.objects.create(
        organization=org,
        project=project,
        file_name="resume.pdf",
        file_type=ResumeUpload.FileType.PDF,
        source=ResumeUpload.Source.MANUAL,
        status=ResumeUpload.Status.PENDING,
        upload_batch=uuid.uuid4(),
        created_by=user,
        extraction_result={
            "extracted": {
                "name": "김철수",
                "email": "test@example.com",
            },
            "raw_text_used": "resume text",
            "diagnosis": {"verdict": "pass"},
        },
    )
    transition_status(upload, ResumeUpload.Status.EXTRACTING)
    upload = transition_status(upload, ResumeUpload.Status.EXTRACTED)
    return upload


class TestLinkResumeToCandidate:
    @patch("projects.services.resume.linker.save_pipeline_result")
    @patch(
        "projects.services.resume.linker.identify_candidate_for_org", return_value=None
    )
    def test_new_candidate_created_with_owned_by(
        self, mock_identify, mock_save, extracted_upload, user, org
    ):
        candidate = Candidate.objects.create(
            name="김철수",
            email="test@example.com",
            owned_by=None,
        )
        mock_save.return_value = candidate

        result = link_resume_to_candidate(extracted_upload, user=user)
        result.refresh_from_db()
        candidate.refresh_from_db()

        assert result.status == ResumeUpload.Status.LINKED
        assert result.candidate == candidate
        assert candidate.owned_by == org

    @patch("projects.services.resume.linker.save_pipeline_result")
    @patch("projects.services.resume.linker.identify_candidate_for_org")
    def test_force_new_creates_new_even_with_match(
        self, mock_identify, mock_save, extracted_upload, user, org
    ):
        candidate = Candidate.objects.create(
            name="김철수",
            email="test@example.com",
            owned_by=org,
        )
        mock_save.return_value = candidate

        link_resume_to_candidate(extracted_upload, user=user, force_new=True)
        mock_identify.assert_not_called()

    def test_invalid_status_raises_value_error(self, org, user, project):
        upload = ResumeUpload.objects.create(
            organization=org,
            project=project,
            file_name="pending.pdf",
            file_type=ResumeUpload.FileType.PDF,
            status=ResumeUpload.Status.PENDING,
            created_by=user,
            extraction_result={"extracted": {"name": "Test"}},
        )
        with pytest.raises(ValueError, match="Cannot link upload"):
            link_resume_to_candidate(upload, user=user)

    @patch("projects.services.resume.linker.save_pipeline_result")
    @patch(
        "projects.services.resume.linker.identify_candidate_for_org", return_value=None
    )
    def test_contact_created_for_project(
        self, mock_identify, mock_save, extracted_upload, user, org
    ):
        candidate = Candidate.objects.create(
            name="김철수",
            email="test@example.com",
            owned_by=org,
        )
        mock_save.return_value = candidate

        link_resume_to_candidate(extracted_upload, user=user)

        assert Contact.objects.filter(
            project=extracted_upload.project,
            candidate=candidate,
        ).exists()
        contact = Contact.objects.get(
            project=extracted_upload.project,
            candidate=candidate,
        )
        assert contact.consultant == user
        assert contact.result == Contact.Result.INTERESTED
