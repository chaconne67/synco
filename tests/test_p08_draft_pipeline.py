"""P08: AI Document Pipeline tests.

Tests for SubmissionDraft model, state transitions, views (auth, org isolation,
HTMX), AI services (mocked), audio validation, Word conversion, masking,
and submit-without-document blocking.
"""

import json
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import Client as TestClient
from django.urls import reverse
from django.utils import timezone

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import (
    Contact,
    DEFAULT_MASKING_CONFIG,
    DraftStatus,
    OutputFormat,
    OutputLanguage,
    Project,
    Submission,
    SubmissionDraft,
    SubmissionTemplate,
)
from projects.services.draft_pipeline import (
    InvalidDraftTransition,
    transition_draft,
)


# --- Fixtures ---


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Draft Test Firm")


@pytest.fixture
def org2(db):
    return Organization.objects.create(name="Other Draft Firm")


@pytest.fixture
def user_with_org(db, org):
    user = User.objects.create_user(username="draft_tester", password="test1234")
    Membership.objects.create(user=user, organization=org)
    return user


@pytest.fixture
def user_with_org2(db, org2):
    user = User.objects.create_user(username="draft_tester2", password="test1234")
    Membership.objects.create(user=user, organization=org2)
    return user


@pytest.fixture
def auth_client(user_with_org):
    c = TestClient()
    c.login(username="draft_tester", password="test1234")
    return c


@pytest.fixture
def auth_client2(user_with_org2):
    c = TestClient()
    c.login(username="draft_tester2", password="test1234")
    return c


@pytest.fixture
def client_obj(org):
    return Client.objects.create(name="Draft Acme", industry="IT", organization=org)


@pytest.fixture
def project(client_obj, org, user_with_org):
    p = Project.objects.create(
        client=client_obj,
        organization=org,
        title="Draft Test Project",
        created_by=user_with_org,
    )
    p.assigned_consultants.add(user_with_org)
    return p


@pytest.fixture
def candidate(org):
    return Candidate.objects.create(
        name="홍길동",
        name_en="Hong Gildong",
        owned_by=org,
        current_company="테스트 주식회사",
        current_position="과장",
        total_experience_years=10,
    )


@pytest.fixture
def interested_contact(project, candidate, user_with_org):
    return Contact.objects.create(
        project=project,
        candidate=candidate,
        consultant=user_with_org,
        channel=Contact.Channel.PHONE,
        contacted_at=timezone.now(),
        result=Contact.Result.INTERESTED,
    )


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


@pytest.fixture
def submission(project, candidate, user_with_org, interested_contact):
    return Submission.objects.create(
        project=project,
        candidate=candidate,
        consultant=user_with_org,
        template=SubmissionTemplate.XD_KO,
    )


@pytest.fixture
def draft(submission):
    return SubmissionDraft.objects.create(submission=submission)


# --- Model Tests ---


class TestSubmissionDraftModel:
    def test_draft_creation_defaults(self, submission):
        """SubmissionDraft 생성 시 기본값 확인."""
        draft = SubmissionDraft.objects.create(submission=submission)
        assert draft.status == DraftStatus.PENDING
        assert draft.masking_config == DEFAULT_MASKING_CONFIG
        assert draft.output_format == OutputFormat.WORD
        assert draft.output_language == OutputLanguage.KO
        assert draft.auto_draft_json == {}
        assert draft.auto_corrections == []

    def test_draft_onetoone_constraint(self, submission):
        """같은 Submission에 두 번째 draft 생성 차단."""
        SubmissionDraft.objects.create(submission=submission)
        with pytest.raises(IntegrityError):
            SubmissionDraft.objects.create(submission=submission)

    def test_draft_cascade_delete(self, submission):
        """Submission 삭제 시 draft도 함께 삭제."""
        SubmissionDraft.objects.create(submission=submission)
        submission.delete()
        assert SubmissionDraft.objects.count() == 0

    def test_masking_config_default_on_empty(self, submission):
        """masking_config이 빈 값이면 save 시 기본값으로 채워진다."""
        draft = SubmissionDraft(submission=submission, masking_config={})
        draft.save()
        assert draft.masking_config == DEFAULT_MASKING_CONFIG


# --- State Transition Tests ---


class TestDraftTransitions:
    def test_valid_transition_pending_to_generated(self, draft):
        """허용된 전이: pending -> draft_generated."""
        transition_draft(draft, DraftStatus.DRAFT_GENERATED)
        assert draft.status == DraftStatus.DRAFT_GENERATED

    def test_invalid_transition_pending_to_finalized(self, draft):
        """허용되지 않은 전이: pending -> finalized."""
        with pytest.raises(InvalidDraftTransition):
            transition_draft(draft, DraftStatus.FINALIZED)

    def test_skip_consultation(self, submission):
        """상담 건너뛰기: draft_generated -> finalized."""
        draft = SubmissionDraft.objects.create(
            submission=submission, status=DraftStatus.DRAFT_GENERATED
        )
        transition_draft(draft, DraftStatus.FINALIZED)
        assert draft.status == DraftStatus.FINALIZED

    def test_consultation_then_finalize(self, submission):
        """상담 후 정리: draft_generated -> consultation_added -> finalized."""
        draft = SubmissionDraft.objects.create(
            submission=submission, status=DraftStatus.DRAFT_GENERATED
        )
        transition_draft(draft, DraftStatus.CONSULTATION_ADDED)
        assert draft.status == DraftStatus.CONSULTATION_ADDED
        transition_draft(draft, DraftStatus.FINALIZED)
        assert draft.status == DraftStatus.FINALIZED

    def test_regression_reviewed_to_finalized(self, submission):
        """회귀 전이: reviewed -> finalized (재정리)."""
        draft = SubmissionDraft.objects.create(
            submission=submission, status=DraftStatus.REVIEWED
        )
        transition_draft(draft, DraftStatus.FINALIZED)
        assert draft.status == DraftStatus.FINALIZED

    def test_regression_converted_to_reviewed(self, submission):
        """회귀 전이: converted -> reviewed (재검토)."""
        draft = SubmissionDraft.objects.create(
            submission=submission, status=DraftStatus.CONVERTED
        )
        transition_draft(draft, DraftStatus.REVIEWED)
        assert draft.status == DraftStatus.REVIEWED

    def test_full_pipeline_transitions(self, submission):
        """전체 파이프라인 순서대로 전이."""
        draft = SubmissionDraft.objects.create(submission=submission)
        transition_draft(draft, DraftStatus.DRAFT_GENERATED)
        transition_draft(draft, DraftStatus.CONSULTATION_ADDED)
        transition_draft(draft, DraftStatus.FINALIZED)
        transition_draft(draft, DraftStatus.REVIEWED)
        transition_draft(draft, DraftStatus.CONVERTED)
        assert draft.status == DraftStatus.CONVERTED


# --- View Auth/Security Tests ---


class TestDraftViewSecurity:
    def test_draft_view_login_required(self, client, project, submission):
        """비로그인 시 draft 뷰 접근 차단."""
        url = reverse("projects:submission_draft", args=[project.pk, submission.pk])
        response = client.get(url)
        assert response.status_code == 302

    def test_draft_view_org_isolation(self, auth_client2, project, submission):
        """다른 조직의 submission draft 접근 차단."""
        url = reverse("projects:submission_draft", args=[project.pk, submission.pk])
        response = auth_client2.get(url)
        assert response.status_code == 404

    def test_generate_login_required(self, client, project, submission):
        """비로그인 시 generate 접근 차단."""
        url = reverse("projects:draft_generate", args=[project.pk, submission.pk])
        response = client.post(url)
        assert response.status_code == 302

    def test_all_draft_urls_resolve(self, project, submission):
        """모든 draft URL이 정상 resolve."""
        url_names = [
            "submission_draft",
            "draft_generate",
            "draft_consultation",
            "draft_consultation_audio",
            "draft_finalize",
            "draft_review",
            "draft_convert",
            "draft_preview",
        ]
        for name in url_names:
            url = reverse(f"projects:{name}", args=[project.pk, submission.pk])
            assert url is not None


# --- View Functional Tests ---


class TestDraftViews:
    def test_submission_draft_get_or_create(self, auth_client, project, submission):
        """draft 뷰 진입 시 draft가 없으면 자동 생성."""
        assert not SubmissionDraft.objects.filter(submission=submission).exists()

        url = reverse("projects:submission_draft", args=[project.pk, submission.pk])
        response = auth_client.get(url)
        assert response.status_code == 200
        assert SubmissionDraft.objects.filter(submission=submission).exists()

    def test_submission_draft_shows_pending(self, auth_client, project, submission):
        """pending 상태에서 초안 생성 버튼이 표시."""
        url = reverse("projects:submission_draft", args=[project.pk, submission.pk])
        response = auth_client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert "AI 초안 생성" in content

    @patch("projects.services.draft_generator.generate_draft")
    def test_draft_generate_success(
        self, mock_generate, auth_client, project, submission
    ):
        """AI 초안 생성 성공."""

        def fake_generate(draft):
            draft.auto_draft_json = {"summary": "테스트 요약"}
            draft.auto_corrections = []
            draft.status = DraftStatus.DRAFT_GENERATED
            draft.save()

        mock_generate.side_effect = fake_generate

        url = reverse("projects:draft_generate", args=[project.pk, submission.pk])
        response = auth_client.post(url)
        assert response.status_code == 200

        draft = SubmissionDraft.objects.get(submission=submission)
        assert draft.status == DraftStatus.DRAFT_GENERATED

    @patch("projects.services.draft_generator.generate_draft")
    def test_draft_generate_failure(
        self, mock_generate, auth_client, project, submission
    ):
        """Gemini API 실패 시 에러 표시."""
        mock_generate.side_effect = RuntimeError("API Error")

        url = reverse("projects:draft_generate", args=[project.pk, submission.pk])
        response = auth_client.post(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert "API Error" in content

    def test_consultation_text_input(self, auth_client, project, submission):
        """상담 내용 직접 입력 저장."""
        # Create draft in DRAFT_GENERATED state
        SubmissionDraft.objects.create(
            submission=submission, status=DraftStatus.DRAFT_GENERATED
        )

        url = reverse("projects:draft_consultation", args=[project.pk, submission.pk])
        response = auth_client.post(
            url, {"consultation_input": "이직 동기: 더 좋은 기회"}
        )
        assert response.status_code == 200

        draft = SubmissionDraft.objects.get(submission=submission)
        assert draft.consultation_input == "이직 동기: 더 좋은 기회"

    def test_review_update_content(self, auth_client, project, submission):
        """검토 단계에서 내용 수정."""
        draft = SubmissionDraft.objects.create(
            submission=submission,
            status=DraftStatus.FINALIZED,
            final_content_json={"summary": "원본"},
        )

        url = reverse("projects:draft_review", args=[project.pk, submission.pk])
        new_content = json.dumps({"summary": "수정됨"})
        response = auth_client.post(url, {"final_content": new_content})
        assert response.status_code == 200

        draft.refresh_from_db()
        assert draft.final_content_json["summary"] == "수정됨"
        assert draft.status == DraftStatus.REVIEWED

    def test_review_invalid_json(self, auth_client, project, submission):
        """검토 시 유효하지 않은 JSON 거부."""
        SubmissionDraft.objects.create(
            submission=submission,
            status=DraftStatus.FINALIZED,
            final_content_json={"summary": "원본"},
        )

        url = reverse("projects:draft_review", args=[project.pk, submission.pk])
        response = auth_client.post(url, {"final_content": "not valid json{"})
        assert response.status_code == 400

    def test_finalize_invalid_status(self, auth_client, project, submission):
        """pending 상태에서 finalize 차단."""
        SubmissionDraft.objects.create(
            submission=submission, status=DraftStatus.PENDING
        )

        url = reverse("projects:draft_finalize", args=[project.pk, submission.pk])
        response = auth_client.post(url)
        assert response.status_code == 400

    def test_convert_before_review_blocked(self, auth_client, project, submission):
        """검토 완료 전 변환 차단."""
        SubmissionDraft.objects.create(
            submission=submission, status=DraftStatus.FINALIZED
        )

        url = reverse("projects:draft_convert", args=[project.pk, submission.pk])
        response = auth_client.post(url)
        assert response.status_code == 400


# --- Audio Validation Tests ---


class TestAudioValidation:
    def test_audio_invalid_format(self, auth_client, project, submission):
        """지원하지 않는 오디오 형식 거부."""
        SubmissionDraft.objects.create(
            submission=submission, status=DraftStatus.DRAFT_GENERATED
        )
        audio = SimpleUploadedFile("test.txt", b"not audio", content_type="text/plain")
        url = reverse(
            "projects:draft_consultation_audio",
            args=[project.pk, submission.pk],
        )
        response = auth_client.post(url, {"audio_file": audio})
        assert response.status_code == 400
        assert "지원하지 않는" in response.content.decode()

    def test_audio_empty_file(self, auth_client, project, submission):
        """빈 오디오 파일 거부."""
        SubmissionDraft.objects.create(
            submission=submission, status=DraftStatus.DRAFT_GENERATED
        )
        audio = SimpleUploadedFile("test.webm", b"", content_type="audio/webm")
        url = reverse(
            "projects:draft_consultation_audio",
            args=[project.pk, submission.pk],
        )
        response = auth_client.post(url, {"audio_file": audio})
        assert response.status_code == 400
        assert "빈 오디오" in response.content.decode()

    def test_audio_no_file(self, auth_client, project, submission):
        """오디오 파일 미첨부 시 거부."""
        SubmissionDraft.objects.create(
            submission=submission, status=DraftStatus.DRAFT_GENERATED
        )
        url = reverse(
            "projects:draft_consultation_audio",
            args=[project.pk, submission.pk],
        )
        response = auth_client.post(url)
        assert response.status_code == 400


# --- Converter Tests ---


class TestDraftConverter:
    def test_apply_masking(self):
        """마스킹이 올바르게 적용되는지 확인."""
        from projects.services.draft_converter import _apply_masking

        data = {
            "personal_info": {
                "name": "홍길동",
                "email": "test@test.com",
                "phone": "010-1234-5678",
                "address": "서울시",
                "birth_year": 1990,
            },
            "summary": "테스트",
        }
        config = {
            "salary": False,
            "birth_detail": True,
            "contact": True,
            "current_company": False,
        }
        masked = _apply_masking(data, config)
        assert masked["personal_info"]["name"] == "홍길동"
        assert masked["personal_info"]["email"] == "[마스킹]"
        assert masked["personal_info"]["phone"] == "[마스킹]"
        assert masked["personal_info"]["address"] == "[마스킹]"
        assert masked["personal_info"]["birth_year"] == "[마스킹]"

    def test_apply_masking_no_mask(self):
        """마스킹 비활성화 시 원본 유지."""
        from projects.services.draft_converter import _apply_masking

        data = {
            "personal_info": {
                "name": "홍길동",
                "email": "test@test.com",
            }
        }
        config = {
            "salary": False,
            "birth_detail": False,
            "contact": False,
            "current_company": False,
        }
        masked = _apply_masking(data, config)
        assert masked["personal_info"]["email"] == "test@test.com"

    def test_convert_to_word(self, submission, media_root):
        """Word 파일 변환 성공."""
        from projects.services.draft_converter import convert_to_word

        draft = SubmissionDraft.objects.create(
            submission=submission,
            status=DraftStatus.REVIEWED,
            final_content_json={
                "personal_info": {"name": "홍길동", "name_en": "Hong"},
                "summary": "테스트 요약",
                "careers": [
                    {
                        "company": "테스트사",
                        "position": "과장",
                        "period": "2020.01 ~ 2024.12",
                    }
                ],
            },
        )
        convert_to_word(draft)
        draft.refresh_from_db()
        assert draft.output_file
        assert draft.output_file.name.endswith(".docx")

    def test_convert_without_data(self, submission, media_root):
        """최종 정리 데이터 없이 변환 시 에러."""
        from projects.services.draft_converter import convert_to_word

        draft = SubmissionDraft.objects.create(
            submission=submission,
            status=DraftStatus.REVIEWED,
            final_content_json={},
        )
        with pytest.raises(RuntimeError, match="최종 정리 데이터"):
            convert_to_word(draft)

    def test_convert_copies_to_submission(
        self, auth_client, project, submission, media_root
    ):
        """변환 시 output_file이 Submission.document_file에 복사."""
        SubmissionDraft.objects.create(
            submission=submission,
            status=DraftStatus.REVIEWED,
            final_content_json={
                "personal_info": {"name": "홍길동"},
                "summary": "테스트",
            },
        )

        url = reverse("projects:draft_convert", args=[project.pk, submission.pk])
        response = auth_client.post(url)
        assert response.status_code == 200

        submission.refresh_from_db()
        assert submission.document_file


# --- Submit Validation Tests ---


class TestSubmitValidation:
    def test_submit_without_document_blocked(self, submission):
        """document_file 없이 제출 시 차단."""
        from projects.services.submission import (
            InvalidTransition,
            submit_to_client,
        )

        submission.document_file = ""
        submission.save()
        with pytest.raises(InvalidTransition, match="서류 파일"):
            submit_to_client(submission)

    def test_submit_with_document_succeeds(self, submission, media_root):
        """document_file 있을 때 제출 성공."""
        from projects.services.submission import submit_to_client

        submission.document_file = SimpleUploadedFile("test.docx", b"fake content")
        submission.save()
        result = submit_to_client(submission)
        assert result.status == Submission.Status.SUBMITTED


# --- Preview Tests ---


class TestDraftPreview:
    def test_preview_with_final_content(self, auth_client, project, submission):
        """final_content_json이 있으면 최종 데이터 미리보기."""
        SubmissionDraft.objects.create(
            submission=submission,
            auto_draft_json={"summary": "초안"},
            final_content_json={"summary": "최종"},
        )
        url = reverse("projects:draft_preview", args=[project.pk, submission.pk])
        response = auth_client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert "최종" in content

    def test_preview_with_auto_draft(self, auth_client, project, submission):
        """final_content_json이 없으면 auto_draft_json 미리보기."""
        SubmissionDraft.objects.create(
            submission=submission,
            auto_draft_json={"summary": "초안 내용"},
            final_content_json={},
        )
        url = reverse("projects:draft_preview", args=[project.pk, submission.pk])
        response = auth_client.get(url)
        assert response.status_code == 200
