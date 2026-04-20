"""P18: Linker service tests — link_resume_to_candidate."""

import uuid
from unittest.mock import patch

import pytest

from accounts.models import User
from candidates.models import Candidate
from candidates.services.candidate_identity import CandidateComparisonContext
from clients.models import Client
from projects.models import Contact, Project, ProjectStatus, ResumeUpload
from projects.services.resume.linker import link_resume_to_candidate
from projects.services.resume.transitions import transition_status



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


@pytest.fixture
def extracted_upload(project, user):
    """A ResumeUpload in 'extracted' status with extraction_result."""
    upload = ResumeUpload.objects.create(
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
        })
    transition_status(upload, ResumeUpload.Status.EXTRACTING)
    upload = transition_status(upload, ResumeUpload.Status.EXTRACTED)
    return upload


class TestLinkResumeToCandidate:
    @patch("projects.services.resume.linker.save_pipeline_result")
    @patch(
        "projects.services.resume.linker.identify_candidate_for_org", return_value=None
    )
    def test_new_candidate_created_with_owned_by(
        self, mock_identify, mock_save, extracted_upload, user
    ):
        candidate = Candidate.objects.create(
            name="김철수",
            email="test@example.com",
            owned_by=None)
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
        self, mock_identify, mock_save, extracted_upload, user
    ):
        candidate = Candidate.objects.create(
            name="김철수",
            email="test@example.com")
        mock_save.return_value = candidate

        link_resume_to_candidate(extracted_upload, user=user, force_new=True)
        mock_identify.assert_not_called()

    def test_invalid_status_raises_value_error(self, user, project):
        upload = ResumeUpload.objects.create(
            project=project,
            file_name="pending.pdf",
            file_type=ResumeUpload.FileType.PDF,
            status=ResumeUpload.Status.PENDING,
            created_by=user,
            extraction_result={"extracted": {"name": "Test"}})
        with pytest.raises(ValueError, match="Cannot link upload"):
            link_resume_to_candidate(upload, user=user)

    @patch("projects.services.resume.linker.save_pipeline_result")
    @patch(
        "projects.services.resume.linker.identify_candidate_for_org", return_value=None
    )
    def test_contact_created_for_project(
        self, mock_identify, mock_save, extracted_upload, user
    ):
        candidate = Candidate.objects.create(
            name="김철수",
            email="test@example.com")
        mock_save.return_value = candidate

        link_resume_to_candidate(extracted_upload, user=user)

        assert Contact.objects.filter(
            project=extracted_upload.project,
            candidate=candidate).exists()
        contact = Contact.objects.get(
            project=extracted_upload.project,
            candidate=candidate)
        assert contact.consultant == user
        assert contact.result == Contact.Result.INTERESTED

    @patch("projects.services.resume.linker.save_pipeline_result")
    @patch("projects.services.resume.linker.identify_candidate_for_org")
    def test_existing_candidate_matched_via_identity(
        self, mock_identify, mock_save, extracted_upload, user
    ):
        """Existing candidate matched via org-scoped identity -> linked to that candidate."""
        existing_candidate = Candidate.objects.create(
            name="김철수",
            email="test@example.com")
        # identity matcher returns existing candidate context
        mock_identify.return_value = CandidateComparisonContext(
            candidate=existing_candidate,
            compared_resume=None,
            match_reason="email",
            previous_data={})
        # save_pipeline_result uses comparison_context to update existing
        mock_save.return_value = existing_candidate

        result = link_resume_to_candidate(extracted_upload, user=user)
        result.refresh_from_db()

        assert result.status == ResumeUpload.Status.LINKED
        assert result.candidate == existing_candidate
        # identity was called (not skipped like force_new)
        mock_identify.assert_called_once()
        # comparison_context was passed to save_pipeline_result
        call_kwargs = mock_save.call_args
        assert call_kwargs.kwargs.get("comparison_context") is not None

    @patch("projects.services.resume.linker.save_pipeline_result")
    @patch(
        "projects.services.resume.linker.identify_candidate_for_org", return_value=None
    )
    def test_concurrent_link_uses_get_or_create_for_contact(
        self, mock_identify, mock_save, extracted_upload, user
    ):
        """Concurrent link calls use get_or_create for Contact, preventing duplicates."""
        candidate = Candidate.objects.create(
            name="김철수",
            email="test@example.com")
        mock_save.return_value = candidate

        # First link
        link_resume_to_candidate(extracted_upload, user=user)

        # Create another upload for same project
        upload2 = ResumeUpload.objects.create(
            project=extracted_upload.project,
            file_name="resume2.pdf",
            file_type=ResumeUpload.FileType.PDF,
            source=ResumeUpload.Source.MANUAL,
            status=ResumeUpload.Status.PENDING,
            upload_batch=uuid.uuid4(),
            created_by=user,
            extraction_result={
                "extracted": {"name": "김철수", "email": "test@example.com"},
                "raw_text_used": "resume text 2",
            })
        transition_status(upload2, ResumeUpload.Status.EXTRACTING)
        upload2 = transition_status(upload2, ResumeUpload.Status.EXTRACTED)

        # Second link to same candidate+project — should use get_or_create
        link_resume_to_candidate(upload2, user=user)

        # Only one Contact for this candidate+project
        contacts = Contact.objects.filter(
            project=extracted_upload.project,
            candidate=candidate)
        assert contacts.count() == 1
