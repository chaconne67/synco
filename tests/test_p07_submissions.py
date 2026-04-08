"""P07: Submission CRUD tests.

Tests for submission CRUD, file upload/download, state transitions,
project status auto-transition, organization isolation, and contact tab link.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as TestClient
from django.urls import reverse
from django.utils import timezone

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import (
    Contact,
    Interview,
    Offer,
    Project,
    ProjectStatus,
    Submission,
)
from projects.services.submission import (
    InvalidTransition,
    apply_client_feedback,
    maybe_advance_project_status,
    submit_to_client,
)


# --- Fixtures ---


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def org2(db):
    return Organization.objects.create(name="Other Firm")


@pytest.fixture
def user_with_org(db, org):
    user = User.objects.create_user(username="sub_tester", password="test1234")
    Membership.objects.create(user=user, organization=org)
    return user


@pytest.fixture
def user_with_org2(db, org2):
    user = User.objects.create_user(username="sub_tester2", password="test1234")
    Membership.objects.create(user=user, organization=org2)
    return user


@pytest.fixture
def auth_client(user_with_org):
    c = TestClient()
    c.login(username="sub_tester", password="test1234")
    return c


@pytest.fixture
def auth_client2(user_with_org2):
    c = TestClient()
    c.login(username="sub_tester2", password="test1234")
    return c


@pytest.fixture
def client_obj(org):
    return Client.objects.create(name="Acme Corp", industry="IT", organization=org)


@pytest.fixture
def client_obj2(org2):
    return Client.objects.create(
        name="Other Corp", industry="Finance", organization=org2
    )


@pytest.fixture
def project(client_obj, org, user_with_org):
    p = Project.objects.create(
        client=client_obj,
        organization=org,
        title="Test Project",
        created_by=user_with_org,
    )
    p.assigned_consultants.add(user_with_org)
    return p


@pytest.fixture
def project_other_org(client_obj2, org2, user_with_org2):
    return Project.objects.create(
        client=client_obj2,
        organization=org2,
        title="Other Org Project",
        created_by=user_with_org2,
    )


@pytest.fixture
def candidate(org):
    return Candidate.objects.create(name="홍길동", owned_by=org)


@pytest.fixture
def candidate2(org):
    return Candidate.objects.create(name="김영희", owned_by=org)


@pytest.fixture
def interested_contact(project, candidate, user_with_org):
    """컨택 결과 '관심'인 Contact."""
    return Contact.objects.create(
        project=project,
        candidate=candidate,
        consultant=user_with_org,
        channel=Contact.Channel.PHONE,
        contacted_at=timezone.now(),
        result=Contact.Result.INTERESTED,
    )


@pytest.fixture
def interested_contact2(project, candidate2, user_with_org):
    """두 번째 관심 Contact."""
    return Contact.objects.create(
        project=project,
        candidate=candidate2,
        consultant=user_with_org,
        channel=Contact.Channel.EMAIL,
        contacted_at=timezone.now(),
        result=Contact.Result.INTERESTED,
    )


@pytest.fixture
def submission(project, candidate, user_with_org, interested_contact):
    return Submission.objects.create(
        project=project,
        candidate=candidate,
        consultant=user_with_org,
    )


@pytest.fixture
def submitted_submission(project, candidate, user_with_org, interested_contact):
    return Submission.objects.create(
        project=project,
        candidate=candidate,
        consultant=user_with_org,
        status=Submission.Status.SUBMITTED,
        submitted_at=timezone.now(),
    )


# --- Login Required ---


class TestSubmissionLoginRequired:
    """7개 URL 모두 미로그인 시 redirect 검증."""

    def test_tab_requires_login(self, project):
        c = TestClient()
        url = reverse("projects:project_tab_submissions", args=[project.pk])
        resp = c.get(url)
        assert resp.status_code == 302

    def test_create_requires_login(self, project):
        c = TestClient()
        url = reverse("projects:submission_create", args=[project.pk])
        resp = c.get(url)
        assert resp.status_code == 302

    def test_update_requires_login(self, project, submission):
        c = TestClient()
        url = reverse("projects:submission_update", args=[project.pk, submission.pk])
        resp = c.get(url)
        assert resp.status_code == 302

    def test_delete_requires_login(self, project, submission):
        c = TestClient()
        url = reverse("projects:submission_delete", args=[project.pk, submission.pk])
        resp = c.post(url)
        assert resp.status_code == 302

    def test_submit_requires_login(self, project, submission):
        c = TestClient()
        url = reverse("projects:submission_submit", args=[project.pk, submission.pk])
        resp = c.post(url)
        assert resp.status_code == 302

    def test_feedback_requires_login(self, project, submission):
        c = TestClient()
        url = reverse("projects:submission_feedback", args=[project.pk, submission.pk])
        resp = c.get(url)
        assert resp.status_code == 302

    def test_download_requires_login(self, project, submission):
        c = TestClient()
        url = reverse("projects:submission_download", args=[project.pk, submission.pk])
        resp = c.get(url)
        assert resp.status_code == 302


# --- Organization Isolation ---


class TestSubmissionOrgIsolation:
    """타 조직 프로젝트의 Submission 접근 시 404."""

    def test_create_other_org_404(self, auth_client2, project):
        url = reverse("projects:submission_create", args=[project.pk])
        resp = auth_client2.get(url)
        assert resp.status_code == 404

    def test_update_other_org_404(self, auth_client2, project, submission):
        url = reverse("projects:submission_update", args=[project.pk, submission.pk])
        resp = auth_client2.get(url)
        assert resp.status_code == 404

    def test_delete_other_org_404(self, auth_client2, project, submission):
        url = reverse("projects:submission_delete", args=[project.pk, submission.pk])
        resp = auth_client2.post(url)
        assert resp.status_code == 404

    def test_submit_other_org_404(self, auth_client2, project, submission):
        url = reverse("projects:submission_submit", args=[project.pk, submission.pk])
        resp = auth_client2.post(url)
        assert resp.status_code == 404

    def test_feedback_other_org_404(self, auth_client2, project, submission):
        url = reverse("projects:submission_feedback", args=[project.pk, submission.pk])
        resp = auth_client2.get(url)
        assert resp.status_code == 404

    def test_download_other_org_404(self, auth_client2, project, submission):
        url = reverse("projects:submission_download", args=[project.pk, submission.pk])
        resp = auth_client2.get(url)
        assert resp.status_code == 404


# --- CRUD ---


class TestSubmissionCRUD:
    def test_create_with_interested_candidate(
        self, auth_client, project, candidate, interested_contact
    ):
        """관심 후보자로 Submission 생성 → 204."""
        url = reverse("projects:submission_create", args=[project.pk])
        resp = auth_client.post(
            url,
            {"candidate": str(candidate.pk), "template": "xd_ko", "notes": "test"},
        )
        assert resp.status_code == 204
        assert Submission.objects.filter(project=project, candidate=candidate).exists()

    def test_create_prefill_candidate(
        self, auth_client, project, candidate, interested_contact
    ):
        """?candidate= query param으로 후보자 미리 선택."""
        url = reverse("projects:submission_create", args=[project.pk])
        resp = auth_client.get(url + f"?candidate={candidate.pk}")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert str(candidate.pk) in content

    def test_create_non_interested_candidate_not_in_dropdown(
        self, auth_client, project, candidate, org
    ):
        """미응답 후보자는 드롭다운에 미표시 (관심 Contact 없음)."""
        # candidate has no Contact with INTERESTED result
        url = reverse("projects:submission_create", args=[project.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert candidate.name not in content

    def test_create_duplicate_blocked(
        self, auth_client, project, candidate, interested_contact, submission
    ):
        """같은 프로젝트+후보자 중복 등록 차단."""
        url = reverse("projects:submission_create", args=[project.pk])
        resp = auth_client.post(
            url,
            {"candidate": str(candidate.pk), "template": "xd_ko"},
        )
        # Form should re-render (not 204) since candidate is already excluded from dropdown
        # The candidate won't appear in the queryset due to exclusion logic
        assert resp.status_code == 200  # Form re-rendered with errors

    def test_update_submission(self, auth_client, project, submission):
        """Submission 수정 → 저장."""
        url = reverse("projects:submission_update", args=[project.pk, submission.pk])
        resp = auth_client.post(
            url,
            {
                "candidate": str(submission.candidate.pk),
                "template": "xd_en",
                "notes": "updated notes",
            },
        )
        assert resp.status_code == 204
        submission.refresh_from_db()
        assert submission.template == "xd_en"
        assert submission.notes == "updated notes"

    def test_delete_submission(self, auth_client, project, submission):
        """Submission 삭제 → 204."""
        url = reverse("projects:submission_delete", args=[project.pk, submission.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 204
        assert not Submission.objects.filter(pk=submission.pk).exists()

    def test_delete_blocked_with_interview(
        self, auth_client, project, submitted_submission
    ):
        """면접 이력 존재 시 삭제 차단."""
        Interview.objects.create(
            submission=submitted_submission,
            round=1,
            scheduled_at=timezone.now(),
            type=Interview.Type.IN_PERSON,
        )
        url = reverse(
            "projects:submission_delete",
            args=[project.pk, submitted_submission.pk],
        )
        resp = auth_client.post(url)
        assert resp.status_code == 400
        assert Submission.objects.filter(pk=submitted_submission.pk).exists()

    def test_delete_blocked_with_offer(
        self, auth_client, project, submitted_submission
    ):
        """오퍼 존재 시 삭제 차단."""
        Offer.objects.create(submission=submitted_submission)
        url = reverse(
            "projects:submission_delete",
            args=[project.pk, submitted_submission.pk],
        )
        resp = auth_client.post(url)
        assert resp.status_code == 400
        assert Submission.objects.filter(pk=submitted_submission.pk).exists()


# --- Template Selection ---


class TestTemplateSelection:
    def test_all_four_templates_selectable(
        self, auth_client, project, candidate, interested_contact
    ):
        """4가지 양식 모두 선택/저장 가능."""
        for template_value in ["xd_ko", "xd_ko_en", "xd_en", "custom"]:
            # Clean up previous
            Submission.objects.filter(project=project, candidate=candidate).delete()
            url = reverse("projects:submission_create", args=[project.pk])
            resp = auth_client.post(
                url,
                {"candidate": str(candidate.pk), "template": template_value},
            )
            assert resp.status_code == 204, f"Failed for template: {template_value}"
            sub = Submission.objects.get(project=project, candidate=candidate)
            assert sub.template == template_value


# --- File Upload/Download ---


@pytest.fixture
def media_root(tmp_path, settings):
    """Override MEDIA_ROOT to temp directory with default storage."""
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
    }
    return settings.MEDIA_ROOT


class TestFileUploadDownload:
    def test_upload_pdf(
        self, auth_client, project, candidate, interested_contact, media_root
    ):
        """PDF 업로드 → 다운로드 가능."""
        url = reverse("projects:submission_create", args=[project.pk])
        pdf_file = SimpleUploadedFile(
            "test.pdf", b"%PDF-1.4 test content", content_type="application/pdf"
        )
        resp = auth_client.post(
            url,
            {
                "candidate": str(candidate.pk),
                "template": "xd_ko",
                "document_file": pdf_file,
            },
        )
        assert resp.status_code == 204
        sub = Submission.objects.get(project=project, candidate=candidate)
        assert sub.document_file

        # Download
        dl_url = reverse("projects:submission_download", args=[project.pk, sub.pk])
        dl_resp = auth_client.get(dl_url)
        assert dl_resp.status_code == 200

    def test_upload_docx(
        self, auth_client, project, candidate, interested_contact, media_root
    ):
        """DOCX 업로드 → 다운로드 가능."""
        url = reverse("projects:submission_create", args=[project.pk])
        docx_file = SimpleUploadedFile(
            "test.docx",
            b"PK\x03\x04 docx content",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        resp = auth_client.post(
            url,
            {
                "candidate": str(candidate.pk),
                "template": "xd_ko",
                "document_file": docx_file,
            },
        )
        assert resp.status_code == 204

    def test_upload_invalid_extension_rejected(
        self, auth_client, project, candidate, interested_contact, media_root
    ):
        """.exe 등 비허용 확장자 거부."""
        url = reverse("projects:submission_create", args=[project.pk])
        exe_file = SimpleUploadedFile(
            "test.exe", b"MZ executable", content_type="application/octet-stream"
        )
        resp = auth_client.post(
            url,
            {
                "candidate": str(candidate.pk),
                "template": "xd_ko",
                "document_file": exe_file,
            },
        )
        assert resp.status_code == 200  # Form re-rendered with errors
        assert not Submission.objects.filter(
            project=project, candidate=candidate
        ).exists()

    def test_download_no_file_404(self, auth_client, project, submission):
        """파일 없는 Submission 다운로드 시 404."""
        url = reverse("projects:submission_download", args=[project.pk, submission.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 404


# --- State Transitions ---


class TestStateTransitions:
    def test_submit_drafting_to_submitted(self, auth_client, project, submission):
        """작성중 → 제출 전환 + submitted_at 기록."""
        url = reverse("projects:submission_submit", args=[project.pk, submission.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 204
        submission.refresh_from_db()
        assert submission.status == Submission.Status.SUBMITTED
        assert submission.submitted_at is not None

    def test_submit_already_submitted_fails(
        self, auth_client, project, submitted_submission
    ):
        """이미 제출된 건 재제출 불가."""
        url = reverse(
            "projects:submission_submit",
            args=[project.pk, submitted_submission.pk],
        )
        resp = auth_client.post(url)
        assert resp.status_code == 400

    def test_submit_passed_fails(
        self, auth_client, project, candidate, interested_contact, user_with_org
    ):
        """통과 상태에서 제출 불가."""
        sub = Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            status=Submission.Status.PASSED,
        )
        url = reverse("projects:submission_submit", args=[project.pk, sub.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 400

    def test_feedback_submitted_to_passed(
        self, auth_client, project, submitted_submission
    ):
        """제출 → 통과 (피드백 입력)."""
        url = reverse(
            "projects:submission_feedback",
            args=[project.pk, submitted_submission.pk],
        )
        resp = auth_client.post(
            url,
            {"result": Submission.Status.PASSED, "feedback": "Great candidate"},
        )
        assert resp.status_code == 204
        submitted_submission.refresh_from_db()
        assert submitted_submission.status == Submission.Status.PASSED
        assert submitted_submission.client_feedback == "Great candidate"

    def test_feedback_submitted_to_rejected(
        self, auth_client, project, submitted_submission
    ):
        """제출 → 탈락 (피드백 입력)."""
        url = reverse(
            "projects:submission_feedback",
            args=[project.pk, submitted_submission.pk],
        )
        resp = auth_client.post(
            url,
            {"result": Submission.Status.REJECTED, "feedback": "Not a fit"},
        )
        assert resp.status_code == 204
        submitted_submission.refresh_from_db()
        assert submitted_submission.status == Submission.Status.REJECTED

    def test_feedback_drafting_fails(self, auth_client, project, submission):
        """작성중 상태에서 피드백 불가."""
        url = reverse("projects:submission_feedback", args=[project.pk, submission.pk])
        resp = auth_client.post(
            url,
            {"result": Submission.Status.PASSED, "feedback": "test"},
        )
        assert resp.status_code == 400

    def test_feedback_already_passed_fails(
        self, auth_client, project, candidate, interested_contact, user_with_org
    ):
        """통과 상태에서 피드백 재입력 불가."""
        sub = Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            status=Submission.Status.PASSED,
        )
        url = reverse("projects:submission_feedback", args=[project.pk, sub.pk])
        resp = auth_client.post(
            url,
            {"result": Submission.Status.REJECTED, "feedback": "changed mind"},
        )
        assert resp.status_code == 400

    def test_feedback_already_rejected_fails(
        self, auth_client, project, candidate, interested_contact, user_with_org
    ):
        """탈락 상태에서 피드백 재입력 불가."""
        sub = Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            status=Submission.Status.REJECTED,
        )
        url = reverse("projects:submission_feedback", args=[project.pk, sub.pk])
        resp = auth_client.post(
            url,
            {"result": Submission.Status.PASSED, "feedback": "reconsidered"},
        )
        assert resp.status_code == 400

    def test_client_feedback_at_recorded(
        self, auth_client, project, submitted_submission
    ):
        """피드백 입력 시 client_feedback_at 기록."""
        url = reverse(
            "projects:submission_feedback",
            args=[project.pk, submitted_submission.pk],
        )
        auth_client.post(
            url,
            {"result": Submission.Status.PASSED, "feedback": "ok"},
        )
        submitted_submission.refresh_from_db()
        assert submitted_submission.client_feedback_at is not None


# --- Project Status Auto-transition ---


class TestProjectStatusAutoTransition:
    def test_first_submission_new_to_recommending(
        self, auth_client, project, candidate, interested_contact
    ):
        """첫 Submission 생성 시 NEW → RECOMMENDING."""
        assert project.status == ProjectStatus.NEW
        url = reverse("projects:submission_create", args=[project.pk])
        auth_client.post(
            url,
            {"candidate": str(candidate.pk), "template": "xd_ko"},
        )
        project.refresh_from_db()
        assert project.status == ProjectStatus.RECOMMENDING

    def test_first_submission_searching_to_recommending(
        self, auth_client, project, candidate, interested_contact
    ):
        """첫 Submission 생성 시 SEARCHING → RECOMMENDING."""
        project.status = ProjectStatus.SEARCHING
        project.save(update_fields=["status"])
        url = reverse("projects:submission_create", args=[project.pk])
        auth_client.post(
            url,
            {"candidate": str(candidate.pk), "template": "xd_ko"},
        )
        project.refresh_from_db()
        assert project.status == ProjectStatus.RECOMMENDING

    def test_already_recommending_no_change(self, project):
        """이미 RECOMMENDING 이상이면 변경 없음."""
        project.status = ProjectStatus.RECOMMENDING
        project.save(update_fields=["status"])
        result = maybe_advance_project_status(project)
        assert result is False
        project.refresh_from_db()
        assert project.status == ProjectStatus.RECOMMENDING


# --- Contact Tab Link ---


class TestContactTabSubmissionLink:
    def test_interested_contact_shows_link(
        self, auth_client, project, interested_contact
    ):
        """관심 결과 건에 '추천 서류 작성' 링크 표시."""
        url = reverse("projects:project_tab_contacts", args=[project.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "추천 서류 작성" in content

    def test_non_interested_no_link(
        self, auth_client, project, candidate, user_with_org
    ):
        """미응답 건에는 추천 서류 작성 링크 미표시."""
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel=Contact.Channel.PHONE,
            contacted_at=timezone.now(),
            result=Contact.Result.NO_RESPONSE,
        )
        url = reverse("projects:project_tab_contacts", args=[project.pk])
        resp = auth_client.get(url)
        content = resp.content.decode()
        assert "추천 서류 작성" not in content

    def test_already_submitted_shows_complete(
        self, auth_client, project, interested_contact, submission
    ):
        """이미 Submission이 있으면 '추천 등록 완료' 표시."""
        url = reverse("projects:project_tab_contacts", args=[project.pk])
        resp = auth_client.get(url)
        content = resp.content.decode()
        assert "추천 등록 완료" in content


# --- HTMX Behavior ---


class TestHTMXBehavior:
    def test_create_returns_204_with_trigger(
        self, auth_client, project, candidate, interested_contact
    ):
        """생성 성공 시 204 + HX-Trigger: submissionChanged."""
        url = reverse("projects:submission_create", args=[project.pk])
        resp = auth_client.post(
            url,
            {"candidate": str(candidate.pk), "template": "xd_ko"},
        )
        assert resp.status_code == 204
        assert resp.headers.get("HX-Trigger") == "submissionChanged"

    def test_tab_has_auto_refresh_trigger(self, auth_client, project):
        """탭에 submissionChanged hx-trigger 존재."""
        url = reverse("projects:project_tab_submissions", args=[project.pk])
        resp = auth_client.get(url)
        content = resp.content.decode()
        assert "submissionChanged" in content


# --- Model Constraints ---


class TestModelConstraints:
    def test_submission_new_fields_default(
        self, project, candidate, user_with_org, interested_contact
    ):
        """기존 Submission 생성 코드가 새 필드 없이도 동작."""
        sub = Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
        )
        assert sub.template == ""
        assert sub.client_feedback_at is None
        assert sub.notes == ""

    def test_unique_constraint(
        self, project, candidate, user_with_org, interested_contact
    ):
        """같은 프로젝트+후보자 중복 등록 차단."""
        from django.db import IntegrityError

        Submission.objects.create(
            project=project, candidate=candidate, consultant=user_with_org
        )
        with pytest.raises(IntegrityError):
            Submission.objects.create(
                project=project, candidate=candidate, consultant=user_with_org
            )


# --- Service Layer Unit Tests ---


class TestSubmissionService:
    def test_submit_to_client_success(self, submission):
        """submit_to_client: 작성중 → 제출."""
        result = submit_to_client(submission)
        assert result.status == Submission.Status.SUBMITTED
        assert result.submitted_at is not None

    def test_submit_to_client_invalid(self, submitted_submission):
        """submit_to_client: 제출 상태에서 실패."""
        with pytest.raises(InvalidTransition):
            submit_to_client(submitted_submission)

    def test_apply_client_feedback_passed(self, submitted_submission):
        """apply_client_feedback: 제출 → 통과."""
        result = apply_client_feedback(
            submitted_submission, Submission.Status.PASSED, "Great"
        )
        assert result.status == Submission.Status.PASSED
        assert result.client_feedback == "Great"
        assert result.client_feedback_at is not None

    def test_apply_client_feedback_rejected(self, submitted_submission):
        """apply_client_feedback: 제출 → 탈락."""
        result = apply_client_feedback(
            submitted_submission, Submission.Status.REJECTED, "Not fit"
        )
        assert result.status == Submission.Status.REJECTED

    def test_apply_client_feedback_invalid_state(self, submission):
        """apply_client_feedback: 작성중 상태에서 실패."""
        with pytest.raises(InvalidTransition):
            apply_client_feedback(submission, Submission.Status.PASSED, "test")

    def test_apply_client_feedback_invalid_result(self, submitted_submission):
        """apply_client_feedback: 유효하지 않은 결과."""
        with pytest.raises(InvalidTransition):
            apply_client_feedback(
                submitted_submission, Submission.Status.DRAFTING, "test"
            )

    def test_maybe_advance_new(self, project):
        """maybe_advance_project_status: NEW → RECOMMENDING."""
        result = maybe_advance_project_status(project)
        assert result is True
        project.refresh_from_db()
        assert project.status == ProjectStatus.RECOMMENDING

    def test_maybe_advance_searching(self, project):
        """maybe_advance_project_status: SEARCHING → RECOMMENDING."""
        project.status = ProjectStatus.SEARCHING
        project.save(update_fields=["status"])
        result = maybe_advance_project_status(project)
        assert result is True
        project.refresh_from_db()
        assert project.status == ProjectStatus.RECOMMENDING

    def test_maybe_advance_already_beyond(self, project):
        """maybe_advance_project_status: RECOMMENDING → no change."""
        project.status = ProjectStatus.RECOMMENDING
        project.save(update_fields=["status"])
        result = maybe_advance_project_status(project)
        assert result is False
