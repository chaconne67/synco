"""P10: Job Posting tests.

Tests for PostingSite model, posting generation service, posting views,
posting site CRUD, organization isolation, and HTMX behavior.
"""

import pytest
from django.test import Client as TestClient
from django.utils import timezone

from accounts.models import User
from clients.models import Client
from projects.models import (
    PostingSite,
    PostingSiteChoice,
    Project,
    ProjectStatus,
)


# --- Fixtures ---


@pytest.fixture
def user_with_org(db):
    user = User.objects.create_user(
        username="p10_tester", password="test1234", first_name="전", last_name="병권",
        level=2,
    )
    return user


@pytest.fixture
def user_with_org2(db):
    user = User.objects.create_user(username="p10_tester2", password="test1234", level=2)
    return user


@pytest.fixture
def auth_client(user_with_org):
    c = TestClient()
    c.login(username="p10_tester", password="test1234")
    return c


@pytest.fixture
def auth_client2(user_with_org2):
    c = TestClient()
    c.login(username="p10_tester2", password="test1234")
    return c


@pytest.fixture
def client_obj(db):
    return Client.objects.create(
        name="Rayence",
        industry="의료기기",
        size="중견",
        region="경기도",
    )


@pytest.fixture
def client_obj2(db):
    return Client.objects.create(name="Other Corp", industry="IT")


@pytest.fixture
def project(client_obj, user_with_org):
    p = Project.objects.create(
        client=client_obj,
        title="품질기획팀장",
        jd_text="품질경영시스템 기획 및 운영 총괄. ISO 13485 인증 관리. 경력 15년 이상.",
        created_by=user_with_org,
        status=ProjectStatus.SEARCHING,
    )
    p.assigned_consultants.add(user_with_org)
    return p


@pytest.fixture
def project_other_org(client_obj2, user_with_org2):
    return Project.objects.create(
        client=client_obj2,
        title="Other Org Project",
        created_by=user_with_org2,
    )


@pytest.fixture
def posting_site(project):
    return PostingSite.objects.create(
        project=project,
        site=PostingSiteChoice.JOBKOREA,
        posted_at=timezone.now().date(),
        applicant_count=3,
    )


# --- Model Tests ---


class TestPostingSiteModel:
    def test_create_posting_site(self, project):
        site = PostingSite.objects.create(
            project=project,
            site=PostingSiteChoice.SARAMIN,
            posted_at=timezone.now().date(),
            applicant_count=5,
        )
        assert site.project == project
        assert site.site == PostingSiteChoice.SARAMIN
        assert site.applicant_count == 5
        assert site.is_active is True

    def test_unique_constraint(self, posting_site, project):
        """Same project + same site should raise IntegrityError."""
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            PostingSite.objects.create(
                project=project,
                site=PostingSiteChoice.JOBKOREA,
            )

    def test_soft_delete(self, posting_site):
        posting_site.is_active = False
        posting_site.save()
        assert (
            PostingSite.objects.filter(
                project=posting_site.project, is_active=True
            ).count()
            == 0
        )
        assert PostingSite.objects.filter(project=posting_site.project).count() == 1

    def test_posting_file_name_on_project(self, project):
        project.posting_file_name = "(260408) Rayence_품질기획팀장_전병권.txt"
        project.save()
        project.refresh_from_db()
        assert "Rayence" in project.posting_file_name


# --- Service Tests ---

from projects.services.posting import generate_posting, get_posting_filename


class TestPostingFilename:
    def test_filename_format(self, project, user_with_org):
        """파일명이 (YYMMDD) 회사명_포지션명_담당자명.txt 형식."""
        import re

        filename = get_posting_filename(project, user_with_org)
        # Full format regex: (YYMMDD) name_name_name.txt
        assert re.match(r"\(\d{6}\) .+_.+_.+\.txt", filename), f"Unexpected: {filename}"
        # Contains client name
        assert "Rayence" in filename
        # Contains project title (position)
        assert "품질기획팀장" in filename
        # Contains user full_name
        user_name = user_with_org.get_full_name()
        assert user_name in filename, f"Expected '{user_name}' in '{filename}'"

    def test_filename_date_prefix(self, project, user_with_org):
        """파일명 앞에 (YYMMDD) 날짜가 포함."""
        import re

        filename = get_posting_filename(project, user_with_org)
        assert re.match(r"\(\d{6}\) ", filename), f"Date prefix missing: {filename}"


class TestGeneratePosting:
    def test_no_jd_text_raises(self, client_obj, user_with_org):
        """JD 텍스트 없으면 ValueError."""
        empty_project = Project.objects.create(
            client=client_obj,
            title="Empty JD",
            created_by=user_with_org,
        )
        with pytest.raises(ValueError, match="JD"):
            generate_posting(empty_project)

    def test_generate_posting_success(self, project, monkeypatch):
        """Gemini 호출 성공 시 posting_text 반환."""
        fake_response_text = "[포지션] 품질기획 팀장급\n[업종] 중견 의료기기 제조사"

        class FakeResponse:
            text = fake_response_text

        class FakeModels:
            def generate_content(self, **kwargs):
                return FakeResponse()

        class FakeClient:
            models = FakeModels()

        monkeypatch.setattr(
            "projects.services.posting._get_gemini_client",
            lambda: FakeClient(),
        )

        result = generate_posting(project)
        assert "품질기획" in result
        assert "Rayence" not in result  # company name not in posting text

    def test_generate_posting_reads_jd_raw_text_first(self, project, monkeypatch):
        """jd_raw_text가 있으면 jd_text보다 우선."""
        project.jd_raw_text = "RAW JD 원문 내용"
        project.save()

        captured_prompts = []

        class FakeResponse:
            text = "[포지션] 테스트"

        class FakeModels:
            def generate_content(self, **kwargs):
                captured_prompts.append(kwargs.get("contents", ""))
                return FakeResponse()

        class FakeClient:
            models = FakeModels()

        monkeypatch.setattr(
            "projects.services.posting._get_gemini_client",
            lambda: FakeClient(),
        )

        generate_posting(project)
        assert "RAW JD 원문 내용" in captured_prompts[0]


# --- Form Tests ---

from projects.forms import PostingEditForm, PostingSiteForm


class TestPostingEditForm:
    def test_valid_form(self):
        form = PostingEditForm(data={"posting_text": "공지 내용입니다."})
        assert form.is_valid()

    def test_empty_text_invalid(self):
        form = PostingEditForm(data={"posting_text": ""})
        assert not form.is_valid()


class TestPostingSiteForm:
    def test_valid_form(self):
        form = PostingSiteForm(
            data={
                "site": "saramin",
                "posted_at": "2026-04-08",
                "applicant_count": 3,
            }
        )
        assert form.is_valid()

    def test_missing_site_invalid(self):
        form = PostingSiteForm(data={"posted_at": "2026-04-08"})
        assert not form.is_valid()


# --- View Tests: Generate / Edit / Download ---

from django.urls import reverse


class TestPostingGenerateView:
    def test_login_required(self, project):
        c = TestClient()
        url = reverse("projects:posting_generate", args=[project.pk])
        resp = c.post(url)
        assert resp.status_code == 302

    def test_generate_no_jd(self, auth_client, client_obj, user_with_org):
        """JD 없는 프로젝트에서 생성 시도 시 에러."""
        empty = Project.objects.create(
            client=client_obj,
            title="Empty",
            created_by=user_with_org,
        )
        url = reverse("projects:posting_generate", args=[empty.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 200
        assert "JD" in resp.content.decode()

    def test_generate_success(self, auth_client, project, monkeypatch):
        """AI 생성 성공 시 posting_text가 저장."""
        monkeypatch.setattr(
            "projects.views.posting_service.generate_posting",
            lambda p: "[포지션] 테스트",
        )
        url = reverse("projects:posting_generate", args=[project.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 200
        project.refresh_from_db()
        assert project.posting_text == "[포지션] 테스트"
        assert project.posting_file_name.endswith(".txt")

    def test_generate_runtime_error_preserves_existing(
        self, auth_client, project, monkeypatch
    ):
        """I-06: Gemini 오류 시 기존 posting_text 보존."""
        project.posting_text = "기존 공지 내용"
        project.save()

        def raise_error(p):
            raise RuntimeError("공지 생성에 실패했습니다.")

        monkeypatch.setattr(
            "projects.views.posting_service.generate_posting",
            raise_error,
        )
        url = reverse("projects:posting_generate", args=[project.pk])
        resp = auth_client.post(url, {"overwrite": "true"})
        assert resp.status_code == 200
        assert "실패" in resp.content.decode()
        project.refresh_from_db()
        assert project.posting_text == "기존 공지 내용"

    def test_overwrite_protection(self, auth_client, project, monkeypatch):
        """I-07: 기존 내용 있고 overwrite 없으면 확인 UI 반환."""
        project.posting_text = "기존 내용"
        project.save()
        url = reverse("projects:posting_generate", args=[project.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 200
        project.refresh_from_db()
        assert project.posting_text == "기존 내용"  # not overwritten

    def test_overwrite_with_flag(self, auth_client, project, monkeypatch):
        """I-07: overwrite=true 시 새로 생성."""
        project.posting_text = "기존 내용"
        project.save()
        monkeypatch.setattr(
            "projects.views.posting_service.generate_posting",
            lambda p: "[포지션] 새 공지",
        )
        url = reverse("projects:posting_generate", args=[project.pk])
        resp = auth_client.post(url, {"overwrite": "true"})
        assert resp.status_code == 200
        project.refresh_from_db()
        assert project.posting_text == "[포지션] 새 공지"

    # test_org_isolation removed — single-tenant, no org isolation


class TestPostingEditView:
    def test_login_required(self, project):
        c = TestClient()
        url = reverse("projects:posting_edit", args=[project.pk])
        resp = c.get(url)
        assert resp.status_code == 302

    def test_get_edit_form(self, auth_client, project):
        project.posting_text = "기존 공지"
        project.save()
        url = reverse("projects:posting_edit", args=[project.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 200
        assert "기존 공지" in resp.content.decode()

    def test_post_edit_saves(self, auth_client, project):
        project.posting_text = "기존 공지"
        project.save()
        url = reverse("projects:posting_edit", args=[project.pk])
        resp = auth_client.post(url, {"posting_text": "수정된 공지"})
        assert resp.status_code == 200
        project.refresh_from_db()
        assert project.posting_text == "수정된 공지"


class TestPostingDownloadView:
    def test_login_required(self, project):
        c = TestClient()
        url = reverse("projects:posting_download", args=[project.pk])
        resp = c.get(url)
        assert resp.status_code == 302

    def test_download_with_content(self, auth_client, project):
        project.posting_text = "공지 내용"
        project.posting_file_name = "(260408) Test_Position_Tester.txt"
        project.save()
        url = reverse("projects:posting_download", args=[project.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 200
        assert resp["Content-Type"] == "text/plain; charset=utf-8"
        assert "attachment" in resp["Content-Disposition"]
        assert resp.content.decode("utf-8") == "공지 내용"

    def test_download_no_content_404(self, auth_client, project):
        url = reverse("projects:posting_download", args=[project.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 404


# --- View Tests: PostingSite CRUD ---


class TestPostingSitesView:
    def test_login_required(self, project):
        c = TestClient()
        url = reverse("projects:posting_sites", args=[project.pk])
        resp = c.get(url)
        assert resp.status_code == 302

    def test_list_active_only(self, auth_client, project, posting_site):
        """is_active=True만 표시."""
        PostingSite.objects.create(
            project=project,
            site=PostingSiteChoice.SARAMIN,
            is_active=False,
        )
        url = reverse("projects:posting_sites", args=[project.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "잡코리아" in content
        assert "사람인" not in content  # inactive, hidden


class TestPostingSiteAddView:
    def test_login_required(self, project):
        c = TestClient()
        url = reverse("projects:posting_site_add", args=[project.pk])
        resp = c.post(url)
        assert resp.status_code == 302

    def test_add_success(self, auth_client, project):
        url = reverse("projects:posting_site_add", args=[project.pk])
        resp = auth_client.post(
            url,
            {
                "site": "saramin",
                "posted_at": "2026-04-08",
                "applicant_count": 0,
            },
        )
        assert resp.status_code == 204
        assert PostingSite.objects.filter(
            project=project, site=PostingSiteChoice.SARAMIN
        ).exists()

    def test_add_duplicate_rejected(self, auth_client, project, posting_site):
        """같은 사이트 중복 등록 시 에러."""
        url = reverse("projects:posting_site_add", args=[project.pk])
        resp = auth_client.post(
            url,
            {
                "site": "jobkorea",
                "posted_at": "2026-04-08",
                "applicant_count": 0,
            },
        )
        # Should return the form with error, not 204
        assert resp.status_code == 200

    def test_reactivate_soft_deleted(self, auth_client, project):
        """I-04: 소프트삭제 후 같은 사이트 재등록 시 기존 레코드 재활성화."""
        site = PostingSite.objects.create(
            project=project,
            site=PostingSiteChoice.SARAMIN,
            is_active=False,
            applicant_count=5,
        )
        url = reverse("projects:posting_site_add", args=[project.pk])
        resp = auth_client.post(
            url,
            {
                "site": "saramin",
                "posted_at": "2026-04-08",
                "applicant_count": 0,
            },
        )
        assert resp.status_code == 204
        site.refresh_from_db()
        assert site.is_active is True
        assert site.applicant_count == 0  # updated from form
        # No new record created
        assert (
            PostingSite.objects.filter(
                project=project, site=PostingSiteChoice.SARAMIN
            ).count()
            == 1
        )

    def test_org_isolation(self, auth_client, project_other_org):
        url = reverse("projects:posting_site_add", args=[project_other_org.pk])
        resp = auth_client.post(url, {"site": "saramin"})
        assert resp.status_code == 404


class TestPostingSiteUpdateView:
    def test_login_required(self, project, posting_site):
        c = TestClient()
        url = reverse(
            "projects:posting_site_update", args=[project.pk, posting_site.pk]
        )
        resp = c.post(url)
        assert resp.status_code == 302

    def test_update_applicant_count(self, auth_client, project, posting_site):
        url = reverse(
            "projects:posting_site_update", args=[project.pk, posting_site.pk]
        )
        resp = auth_client.post(
            url,
            {
                "site": "jobkorea",
                "posted_at": "2026-04-08",
                "applicant_count": 10,
            },
        )
        assert resp.status_code == 204
        posting_site.refresh_from_db()
        assert posting_site.applicant_count == 10


class TestPostingSiteDeleteView:
    def test_login_required(self, project, posting_site):
        c = TestClient()
        url = reverse(
            "projects:posting_site_delete", args=[project.pk, posting_site.pk]
        )
        resp = c.post(url)
        assert resp.status_code == 302

    def test_soft_delete(self, auth_client, project, posting_site):
        """삭제 시 is_active=False (소프트 삭제)."""
        url = reverse(
            "projects:posting_site_delete", args=[project.pk, posting_site.pk]
        )
        resp = auth_client.post(url)
        assert resp.status_code == 204
        posting_site.refresh_from_db()
        assert posting_site.is_active is False

    def test_org_isolation(self, auth_client, project_other_org):
        site = PostingSite.objects.create(
            project=project_site=PostingSiteChoice.SARAMIN,
        )
        url = reverse(
            "projects:posting_site_delete", args=[project_other_org.pk, site.pk]
        )
        resp = auth_client.post(url)
        assert resp.status_code == 404


# --- Integration Tests ---


class TestOverviewTabIncludesPosting:
    def test_overview_shows_posting_section(self, auth_client, project):
        """개요 탭에 공지 섹션이 포함."""
        url = reverse("projects:project_tab_overview", args=[project.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "공지" in content

    def test_overview_shows_generate_button_when_no_posting(self, auth_client, project):
        """공지가 없으면 생성 버튼 표시."""
        url = reverse("projects:project_tab_overview", args=[project.pk])
        resp = auth_client.get(url)
        content = resp.content.decode()
        assert "공지 생성" in content

    def test_overview_shows_preview_when_posting_exists(self, auth_client, project):
        """공지가 있으면 미리보기 표시."""
        project.posting_text = "[포지션] 테스트 포지션"
        project.posting_file_name = "test.txt"
        project.save()
        url = reverse("projects:project_tab_overview", args=[project.pk])
        resp = auth_client.get(url)
        content = resp.content.decode()
        assert "테스트 포지션" in content
        assert "공지 편집" in content
        assert "다운로드" in content

    def test_overview_shows_posting_site_counts(
        self, auth_client, project, posting_site
    ):
        """포스팅 현황에 지원자 합계 표시."""
        url = reverse("projects:project_tab_overview", args=[project.pk])
        resp = auth_client.get(url)
        content = resp.content.decode()
        assert "잡코리아" in content
        assert "3명" in content
