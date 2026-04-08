# P10: Job Posting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a posting section to the project overview tab with AI-generated job portal posting text and posting site tracking.

**Architecture:** New `PostingSite` model + `posting_file_name` field on `Project`. AI posting service calls Gemini API following the existing `jd_analysis.py` pattern. 7 new views following the established HTMX CRUD pattern (204 + HX-Trigger). Posting section is included in the existing overview tab template.

**Tech Stack:** Django 5.2, HTMX, Tailwind CSS, Gemini API (google-genai), pytest

---

## File Structure

| File | Responsibility |
|------|---------------|
| `projects/models.py` | Add `PostingSiteChoice`, `PostingSite` model, `posting_file_name` field on `Project` |
| `projects/migrations/0007_p10_posting_site.py` | Auto-generated migration for above |
| `projects/services/posting.py` | **New.** `generate_posting()`, `get_posting_filename()` — Gemini API call + filename rules |
| `projects/services/posting_prompts.py` | **New.** System/user prompt templates for posting generation |
| `projects/forms.py` | Add `PostingEditForm`, `PostingSiteForm` |
| `projects/views.py` | Add 7 posting views: generate, edit, download, sites list, site add/update/delete |
| `projects/urls.py` | Add 7 posting URL patterns |
| `projects/templates/projects/partials/posting_section.html` | **New.** Posting section for overview tab (공지 + 포스팅 현황) |
| `projects/templates/projects/partials/posting_edit.html` | **New.** Posting text edit form |
| `projects/templates/projects/partials/posting_sites.html` | **New.** Posting sites list partial (HTMX target) |
| `projects/templates/projects/partials/posting_site_form.html` | **New.** Inline add/edit form for posting site |
| `projects/templates/projects/partials/tab_overview.html` | Modify: include posting_section.html |
| `tests/test_p10_posting.py` | **New.** All tests for P10 |

---

### Task 1: PostingSite Model + Migration

**Files:**
- Modify: `projects/models.py`
- Create: `projects/migrations/0007_p10_posting_site.py` (auto-generated)
- Test: `tests/test_p10_posting.py`

- [ ] **Step 1: Write the model test**

Create `tests/test_p10_posting.py`:

```python
"""P10: Job Posting tests.

Tests for PostingSite model, posting generation service, posting views,
posting site CRUD, organization isolation, and HTMX behavior.
"""

import pytest
from django.test import Client as TestClient
from django.utils import timezone

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import (
    PostingSite,
    PostingSiteChoice,
    Project,
    ProjectStatus,
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
    user = User.objects.create_user(
        username="p10_tester", password="test1234", first_name="전", last_name="병권"
    )
    Membership.objects.create(user=user, organization=org)
    return user


@pytest.fixture
def user_with_org2(db, org2):
    user = User.objects.create_user(username="p10_tester2", password="test1234")
    Membership.objects.create(user=user, organization=org2)
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
def client_obj(org):
    return Client.objects.create(
        name="Rayence", industry="의료기기", size="중견", region="경기도", organization=org
    )


@pytest.fixture
def client_obj2(org2):
    return Client.objects.create(
        name="Other Corp", industry="IT", organization=org2
    )


@pytest.fixture
def project(client_obj, org, user_with_org):
    p = Project.objects.create(
        client=client_obj,
        organization=org,
        title="품질기획팀장",
        jd_text="품질경영시스템 기획 및 운영 총괄. ISO 13485 인증 관리. 경력 15년 이상.",
        created_by=user_with_org,
        status=ProjectStatus.SEARCHING,
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
        assert PostingSite.objects.filter(
            project=posting_site.project, is_active=True
        ).count() == 0
        assert PostingSite.objects.filter(
            project=posting_site.project
        ).count() == 1

    def test_posting_file_name_on_project(self, project):
        project.posting_file_name = "(260408) Rayence_품질기획팀장_전병권.txt"
        project.save()
        project.refresh_from_db()
        assert "Rayence" in project.posting_file_name
```

- [ ] **Step 2: Add models to projects/models.py**

Add at the end of `projects/models.py`, before any closing comments:

```python
class PostingSiteChoice(models.TextChoices):
    JOBKOREA = "jobkorea", "잡코리아"
    SARAMIN = "saramin", "사람인"
    INCRUIT = "incruit", "인크루트"
    LINKEDIN = "linkedin", "LinkedIn"
    WANTED = "wanted", "원티드"
    CATCH = "catch", "캐치"
    OTHER = "other", "기타"


class PostingSite(BaseModel):
    """포스팅 사이트별 게시 현황."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="posting_sites",
    )
    site = models.CharField(
        max_length=20,
        choices=PostingSiteChoice.choices,
    )
    posted_at = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    applicant_count = models.PositiveIntegerField(default=0)
    url = models.URLField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "site"],
                name="unique_posting_site_per_project",
            )
        ]

    def __str__(self) -> str:
        return f"{self.project} - {self.get_site_display()}"
```

Also add `posting_file_name` field to `Project` model, after `posting_text`:

```python
    posting_file_name = models.CharField(max_length=300, blank=True)
```

- [ ] **Step 3: Generate migration**

Run: `uv run python manage.py makemigrations projects -n p10_posting_site`
Expected: Creates `projects/migrations/0007_p10_posting_site.py`

- [ ] **Step 4: Apply migration**

Run: `uv run python manage.py migrate`
Expected: `Applying projects.0007_p10_posting_site... OK`

- [ ] **Step 5: Run model tests**

Run: `uv run pytest tests/test_p10_posting.py::TestPostingSiteModel -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add projects/models.py projects/migrations/0007_p10_posting_site.py tests/test_p10_posting.py
git commit -m "feat(p10): add PostingSite model and posting_file_name field"
```

---

### Task 2: Posting Service (AI Generation + Filename)

**Files:**
- Create: `projects/services/posting_prompts.py`
- Create: `projects/services/posting.py`
- Test: `tests/test_p10_posting.py` (append)

- [ ] **Step 1: Write posting prompt templates**

Create `projects/services/posting_prompts.py`:

```python
"""공지 생성용 Gemini 프롬프트."""

POSTING_SYSTEM_PROMPT = """\
당신은 헤드헌팅 전문 채용 공고 작성 전문가입니다.
JD(직무기술서)를 기반으로 잡포털에 게시할 공지 텍스트를 작성합니다.

## 원칙
1. 회사명을 절대 노출하지 마세요. 업종과 규모로 간접 표현합니다.
2. 잡포털 표준 양식을 따릅니다.
3. 한국어로 작성합니다.
4. 정보가 없는 항목은 '협의'로 표기하거나 생략합니다.
5. 올해는 2026년입니다.

## 출력 양식 (텍스트만 출력, JSON 아님)

[포지션] (포지션명과 직급)
[업종] (업종 + 규모 간접 표현, 회사명 절대 미포함)
[주요업무]
· 업무1
· 업무2
[자격요건]
· 요건1
· 요건2
[근무지] (근무지 또는 '협의')
[처우] (연봉 정보 또는 '협의')

## 주의사항
- 고객사명, 브랜드명, 제품 고유명은 절대 포함하지 마세요.
- 업종+규모 간접 표현 예시: "중견 의료기기 제조사", "대기업 반도체사", "외국계 소프트웨어사"
- 규모 정보가 없으면 업종만 사용: "의료기기 제조사"
"""

POSTING_USER_PROMPT_TEMPLATE = """\
아래 정보를 바탕으로 잡포털 게시용 공지 텍스트를 작성하세요.

## JD 원문
{jd_text}

## 고객사 정보 (공지에 회사명 노출 금지)
- 회사명: {client_name} (절대 공지에 포함하지 마세요)
- 업종: {client_industry}
- 규모: {client_size}
- 지역: {client_region}

## 구조화된 요구조건 (참고용, 있는 경우만)
{requirements_text}
"""
```

- [ ] **Step 2: Write the service test**

Append to `tests/test_p10_posting.py`:

```python
from projects.services.posting import generate_posting, get_posting_filename


class TestPostingFilename:
    def test_filename_format(self, project, user_with_org):
        """파일명이 (YYMMDD) 회사명_포지션명_담당자명.txt 형식."""
        filename = get_posting_filename(project, user_with_org)
        # Contains .txt extension
        assert filename.endswith(".txt")
        # Contains client name
        assert "Rayence" in filename
        # Contains project title (position)
        assert "품질기획팀장" in filename
        # Contains user full_name
        assert "전" in filename or "병권" in filename

    def test_filename_date_prefix(self, project, user_with_org):
        """파일명 앞에 (YYMMDD) 날짜가 포함."""
        filename = get_posting_filename(project, user_with_org)
        # Starts with (YYMMDD)
        assert filename.startswith("(")
        assert ")" in filename


class TestGeneratePosting:
    def test_no_jd_text_raises(self, client_obj, org, user_with_org):
        """JD 텍스트 없으면 ValueError."""
        empty_project = Project.objects.create(
            client=client_obj,
            organization=org,
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
```

- [ ] **Step 3: Write the posting service**

Create `projects/services/posting.py`:

```python
"""공지 생성 서비스: AI 텍스트 생성 + 파일명 규칙."""

import json
import logging
from datetime import date

from django.conf import settings
from google import genai

from .posting_prompts import POSTING_SYSTEM_PROMPT, POSTING_USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-preview-05-20"


def _get_gemini_client() -> genai.Client:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in settings")
    return genai.Client(api_key=api_key)


def generate_posting(project, max_retries: int = 3) -> str:
    """JD + 고객사 정보를 기반으로 잡포털 공지 텍스트를 생성한다.

    Args:
        project: Project instance (client, jd_raw_text/jd_text, requirements 참조)
        max_retries: Gemini API 재시도 횟수

    Returns:
        생성된 공지 텍스트 (str)

    Raises:
        ValueError: JD 텍스트가 없는 경우
        RuntimeError: Gemini API 호출 실패 (max_retries 초과)
    """
    jd_text = project.jd_raw_text or project.jd_text
    if not jd_text or not jd_text.strip():
        raise ValueError("JD를 먼저 등록해주세요.")

    client = project.client
    requirements_text = ""
    if project.requirements:
        requirements_text = json.dumps(project.requirements, ensure_ascii=False, indent=2)
    else:
        requirements_text = "(구조화된 요구조건 없음 — JD 원문에서 직접 추출하세요)"

    user_prompt = POSTING_USER_PROMPT_TEMPLATE.format(
        jd_text=jd_text,
        client_name=client.name if client else "",
        client_industry=client.industry if client else "",
        client_size=client.get_size_display() if client and client.size else "",
        client_region=client.region if client else "",
        requirements_text=requirements_text,
    )

    gemini_client = _get_gemini_client()

    for attempt in range(max_retries):
        try:
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=POSTING_SYSTEM_PROMPT,
                    max_output_tokens=4000,
                    temperature=0.3,
                ),
            )

            text = response.text.strip()
            if not text:
                logger.warning(
                    "Posting generation: empty response (attempt %d/%d)",
                    attempt + 1,
                    max_retries,
                )
                continue

            return text

        except Exception:
            logger.warning(
                "Posting generation failed (attempt %d/%d)",
                attempt + 1,
                max_retries,
                exc_info=True,
            )

    raise RuntimeError("공지 생성에 실패했습니다. 잠시 후 다시 시도해주세요.")


def get_posting_filename(project, user) -> str:
    """파일명 규칙: (YYMMDD) 회사명_포지션명_담당자명.txt

    Args:
        project: Project instance
        user: User instance (request.user)

    Returns:
        파일명 문자열
    """
    today = date.today()
    date_str = today.strftime("%y%m%d")

    client_name = project.client.name if project.client else "Unknown"
    position = project.title or "포지션미정"
    consultant_name = user.get_full_name() or user.username

    return f"({date_str}) {client_name}_{position}_{consultant_name}.txt"
```

- [ ] **Step 4: Run service tests**

Run: `uv run pytest tests/test_p10_posting.py::TestPostingFilename tests/test_p10_posting.py::TestGeneratePosting -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/posting.py projects/services/posting_prompts.py tests/test_p10_posting.py
git commit -m "feat(p10): add posting generation service with Gemini API"
```

---

### Task 3: Forms (PostingEditForm + PostingSiteForm)

**Files:**
- Modify: `projects/forms.py`
- Test: `tests/test_p10_posting.py` (append)

- [ ] **Step 1: Write form tests**

Append to `tests/test_p10_posting.py`:

```python
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
```

- [ ] **Step 2: Add forms to projects/forms.py**

Add at the end of `projects/forms.py`:

```python
# ---------------------------------------------------------------------------
# P10: Posting forms
# ---------------------------------------------------------------------------


class PostingEditForm(forms.Form):
    """공지 텍스트 편집 폼."""

    posting_text = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": INPUT_CSS,
                "rows": 15,
                "placeholder": "공지 내용을 입력하세요",
            }
        ),
        label="공지 내용",
    )


class PostingSiteForm(forms.ModelForm):
    class Meta:
        model = PostingSite
        fields = ["site", "posted_at", "applicant_count", "url", "notes"]
        widgets = {
            "site": forms.Select(attrs={"class": INPUT_CSS}),
            "posted_at": forms.DateInput(
                attrs={"class": INPUT_CSS, "type": "date"},
                format="%Y-%m-%d",
            ),
            "applicant_count": forms.NumberInput(
                attrs={"class": INPUT_CSS, "min": 0}
            ),
            "url": forms.URLInput(
                attrs={"class": INPUT_CSS, "placeholder": "포스팅 URL (선택)"}
            ),
            "notes": forms.Textarea(
                attrs={"class": INPUT_CSS, "rows": 2, "placeholder": "메모"}
            ),
        }
        labels = {
            "site": "사이트",
            "posted_at": "게시일",
            "applicant_count": "지원자 수",
            "url": "URL",
            "notes": "메모",
        }
```

Also add the import at the top of `projects/forms.py` in the model imports:

```python
from .models import Contact, Interview, JDSource, Offer, PostingSite, Project, Submission
```

- [ ] **Step 3: Run form tests**

Run: `uv run pytest tests/test_p10_posting.py::TestPostingEditForm tests/test_p10_posting.py::TestPostingSiteForm -v`
Expected: All 4 tests PASS

- [ ] **Step 4: Commit**

```bash
git add projects/forms.py tests/test_p10_posting.py
git commit -m "feat(p10): add PostingEditForm and PostingSiteForm"
```

---

### Task 4: Views — Posting Generate + Edit + Download

**Files:**
- Modify: `projects/views.py`
- Modify: `projects/urls.py`
- Test: `tests/test_p10_posting.py` (append)

- [ ] **Step 1: Write view tests for generate/edit/download**

Append to `tests/test_p10_posting.py`:

```python
from django.urls import reverse


class TestPostingGenerateView:
    def test_login_required(self, project):
        c = TestClient()
        url = reverse("projects:posting_generate", args=[project.pk])
        resp = c.post(url)
        assert resp.status_code == 302

    def test_generate_no_jd(self, auth_client, client_obj, org, user_with_org):
        """JD 없는 프로젝트에서 생성 시도 시 에러."""
        empty = Project.objects.create(
            client=client_obj, organization=org, title="Empty",
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

    def test_org_isolation(self, auth_client, project_other_org):
        url = reverse("projects:posting_generate", args=[project_other_org.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 404


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
```

- [ ] **Step 2: Add posting views to projects/views.py**

Add these imports at the top of `projects/views.py`:

```python
from projects.services import posting as posting_service
from .forms import (
    ContactForm,
    InterviewForm,
    InterviewResultForm,
    OfferForm,
    PostingEditForm,
    PostingSiteForm,
    ProjectForm,
    SubmissionFeedbackForm,
    SubmissionForm,
)
from .models import (
    Contact,
    DEFAULT_MASKING_CONFIG,
    DraftStatus,
    Interview,
    Offer,
    OutputLanguage,
    PostingSite,
    PostingSiteChoice,
    Project,
    ProjectStatus,
    Submission,
    SubmissionDraft,
)
```

Add at the end of `projects/views.py` (before the file ends):

```python
# ---------------------------------------------------------------------------
# P10: Posting Management
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["POST"])
def posting_generate(request, pk):
    """AI 공지 초안 생성."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    try:
        text = posting_service.generate_posting(project)
    except ValueError as e:
        return render(
            request,
            "projects/partials/posting_section.html",
            {"project": project, "error": str(e)},
        )
    except RuntimeError as e:
        return render(
            request,
            "projects/partials/posting_section.html",
            {"project": project, "error": str(e)},
        )

    project.posting_text = text
    project.posting_file_name = posting_service.get_posting_filename(
        project, request.user
    )
    project.save(update_fields=["posting_text", "posting_file_name", "updated_at"])

    posting_sites = project.posting_sites.filter(is_active=True)
    total_applicants = sum(s.applicant_count for s in posting_sites)

    return render(
        request,
        "projects/partials/posting_section.html",
        {
            "project": project,
            "posting_sites": posting_sites,
            "total_applicants": total_applicants,
        },
    )


@login_required
def posting_edit(request, pk):
    """공지 내용 편집. GET=폼, POST=저장."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if request.method == "POST":
        form = PostingEditForm(request.POST)
        if form.is_valid():
            project.posting_text = form.cleaned_data["posting_text"]
            project.save(update_fields=["posting_text", "updated_at"])

            posting_sites = project.posting_sites.filter(is_active=True)
            total_applicants = sum(s.applicant_count for s in posting_sites)

            return render(
                request,
                "projects/partials/posting_section.html",
                {
                    "project": project,
                    "posting_sites": posting_sites,
                    "total_applicants": total_applicants,
                },
            )
    else:
        form = PostingEditForm(initial={"posting_text": project.posting_text})

    return render(
        request,
        "projects/partials/posting_edit.html",
        {"project": project, "form": form},
    )


@login_required
def posting_download(request, pk):
    """공지 파일 다운로드 (.txt)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if not project.posting_text:
        return HttpResponse(status=404)

    filename = project.posting_file_name or "posting.txt"

    response = HttpResponse(
        project.posting_text,
        content_type="text/plain; charset=utf-8",
    )
    # RFC 5987 encoded filename for Korean characters
    from urllib.parse import quote

    response["Content-Disposition"] = (
        f"attachment; filename*=UTF-8''{quote(filename)}"
    )
    return response
```

- [ ] **Step 3: Add URL patterns to projects/urls.py**

Add after the P09 Offer URLs:

```python
    # P10: Posting 관리
    path(
        "<uuid:pk>/posting/generate/",
        views.posting_generate,
        name="posting_generate",
    ),
    path(
        "<uuid:pk>/posting/edit/",
        views.posting_edit,
        name="posting_edit",
    ),
    path(
        "<uuid:pk>/posting/download/",
        views.posting_download,
        name="posting_download",
    ),
```

- [ ] **Step 4: Run view tests**

Run: `uv run pytest tests/test_p10_posting.py::TestPostingGenerateView tests/test_p10_posting.py::TestPostingEditView tests/test_p10_posting.py::TestPostingDownloadView -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/views.py projects/urls.py tests/test_p10_posting.py
git commit -m "feat(p10): add posting generate, edit, download views"
```

---

### Task 5: Views — PostingSite CRUD

**Files:**
- Modify: `projects/views.py`
- Modify: `projects/urls.py`
- Test: `tests/test_p10_posting.py` (append)

- [ ] **Step 1: Write PostingSite CRUD view tests**

Append to `tests/test_p10_posting.py`:

```python
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
        resp = auth_client.post(url, {
            "site": "saramin",
            "posted_at": "2026-04-08",
            "applicant_count": 0,
        })
        assert resp.status_code == 204
        assert PostingSite.objects.filter(
            project=project, site=PostingSiteChoice.SARAMIN
        ).exists()

    def test_add_duplicate_rejected(self, auth_client, project, posting_site):
        """같은 사이트 중복 등록 시 에러."""
        url = reverse("projects:posting_site_add", args=[project.pk])
        resp = auth_client.post(url, {
            "site": "jobkorea",
            "posted_at": "2026-04-08",
            "applicant_count": 0,
        })
        # Should return the form with error, not 204
        assert resp.status_code == 200

    def test_org_isolation(self, auth_client, project_other_org):
        url = reverse("projects:posting_site_add", args=[project_other_org.pk])
        resp = auth_client.post(url, {"site": "saramin"})
        assert resp.status_code == 404


class TestPostingSiteUpdateView:
    def test_login_required(self, project, posting_site):
        c = TestClient()
        url = reverse("projects:posting_site_update", args=[project.pk, posting_site.pk])
        resp = c.post(url)
        assert resp.status_code == 302

    def test_update_applicant_count(self, auth_client, project, posting_site):
        url = reverse("projects:posting_site_update", args=[project.pk, posting_site.pk])
        resp = auth_client.post(url, {
            "site": "jobkorea",
            "posted_at": "2026-04-08",
            "applicant_count": 10,
        })
        assert resp.status_code == 204
        posting_site.refresh_from_db()
        assert posting_site.applicant_count == 10


class TestPostingSiteDeleteView:
    def test_login_required(self, project, posting_site):
        c = TestClient()
        url = reverse("projects:posting_site_delete", args=[project.pk, posting_site.pk])
        resp = c.post(url)
        assert resp.status_code == 302

    def test_soft_delete(self, auth_client, project, posting_site):
        """삭제 시 is_active=False (소프트 삭제)."""
        url = reverse("projects:posting_site_delete", args=[project.pk, posting_site.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 204
        posting_site.refresh_from_db()
        assert posting_site.is_active is False

    def test_org_isolation(self, auth_client, project_other_org, org2):
        other_client = Client.objects.filter(organization=org2).first()
        site = PostingSite.objects.create(
            project=project_other_org,
            site=PostingSiteChoice.SARAMIN,
        )
        url = reverse("projects:posting_site_delete", args=[project_other_org.pk, site.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 404
```

- [ ] **Step 2: Add PostingSite CRUD views to projects/views.py**

Append after the `posting_download` view:

```python
@login_required
def posting_sites(request, pk):
    """포스팅 사이트 목록 (HTMX partial)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    sites = project.posting_sites.filter(is_active=True)
    total_applicants = sum(s.applicant_count for s in sites)

    return render(
        request,
        "projects/partials/posting_sites.html",
        {
            "project": project,
            "posting_sites": sites,
            "total_applicants": total_applicants,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def posting_site_add(request, pk):
    """포스팅 사이트 추가."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if request.method == "POST":
        form = PostingSiteForm(request.POST)
        if form.is_valid():
            site = form.save(commit=False)
            site.project = project
            try:
                site.save()
            except Exception:
                # UniqueConstraint violation
                form.add_error("site", "이미 등록된 사이트입니다.")
                return render(
                    request,
                    "projects/partials/posting_site_form.html",
                    {"form": form, "project": project, "is_edit": False},
                )
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "postingSiteChanged"},
            )
    else:
        form = PostingSiteForm()

    return render(
        request,
        "projects/partials/posting_site_form.html",
        {"form": form, "project": project, "is_edit": False},
    )


@login_required
@require_http_methods(["GET", "POST"])
def posting_site_update(request, pk, site_pk):
    """포스팅 사이트 수정."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    site = get_object_or_404(PostingSite, pk=site_pk, project=project)

    if request.method == "POST":
        form = PostingSiteForm(request.POST, instance=site)
        if form.is_valid():
            form.save()
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "postingSiteChanged"},
            )
    else:
        form = PostingSiteForm(instance=site)

    return render(
        request,
        "projects/partials/posting_site_form.html",
        {"form": form, "project": project, "site": site, "is_edit": True},
    )


@login_required
@require_http_methods(["POST"])
def posting_site_delete(request, pk, site_pk):
    """포스팅 사이트 비활성화 (소프트 삭제)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    site = get_object_or_404(PostingSite, pk=site_pk, project=project)

    site.is_active = False
    site.save(update_fields=["is_active", "updated_at"])

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "postingSiteChanged"},
    )
```

- [ ] **Step 3: Add PostingSite URL patterns to projects/urls.py**

Append after posting download URL:

```python
    path(
        "<uuid:pk>/posting/sites/",
        views.posting_sites,
        name="posting_sites",
    ),
    path(
        "<uuid:pk>/posting/sites/new/",
        views.posting_site_add,
        name="posting_site_add",
    ),
    path(
        "<uuid:pk>/posting/sites/<uuid:site_pk>/edit/",
        views.posting_site_update,
        name="posting_site_update",
    ),
    path(
        "<uuid:pk>/posting/sites/<uuid:site_pk>/delete/",
        views.posting_site_delete,
        name="posting_site_delete",
    ),
```

- [ ] **Step 4: Run PostingSite CRUD tests**

Run: `uv run pytest tests/test_p10_posting.py::TestPostingSitesView tests/test_p10_posting.py::TestPostingSiteAddView tests/test_p10_posting.py::TestPostingSiteUpdateView tests/test_p10_posting.py::TestPostingSiteDeleteView -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/views.py projects/urls.py tests/test_p10_posting.py
git commit -m "feat(p10): add PostingSite CRUD views with soft delete"
```

---

### Task 6: Templates — Posting Section + Sites + Edit

**Files:**
- Create: `projects/templates/projects/partials/posting_section.html`
- Create: `projects/templates/projects/partials/posting_sites.html`
- Create: `projects/templates/projects/partials/posting_site_form.html`
- Create: `projects/templates/projects/partials/posting_edit.html`
- Modify: `projects/templates/projects/partials/tab_overview.html`
- Modify: `projects/views.py` (update `_build_overview_context` and `project_tab_overview`)

- [ ] **Step 1: Create posting_section.html**

Create `projects/templates/projects/partials/posting_section.html`:

```html
<section id="posting-section" class="bg-white rounded-lg border border-gray-100 p-5">
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-[15px] font-semibold text-gray-500">공지</h2>
  </div>

  {% if error %}
  <div class="text-[14px] text-red-500 mb-3">{{ error }}</div>
  {% endif %}

  {% if project.posting_text %}
    <!-- 파일명 + 액션 버튼 -->
    <div class="flex items-center justify-between mb-3">
      <span class="text-[14px] text-gray-600 truncate">
        {{ project.posting_file_name|default:"posting.txt" }}
      </span>
      <div class="flex items-center gap-2">
        <button hx-get="{% url 'projects:posting_edit' project.pk %}"
                hx-target="#posting-section"
                hx-swap="outerHTML"
                class="text-[13px] text-primary hover:text-primary-dark font-medium transition">
          공지 편집
        </button>
        <a href="{% url 'projects:posting_download' project.pk %}"
           class="text-[13px] text-primary hover:text-primary-dark font-medium transition">
          다운로드
        </a>
        <button onclick="navigator.clipboard.writeText(document.getElementById('posting-preview-text').innerText)"
                class="text-[13px] text-gray-500 hover:text-gray-700 font-medium transition">
          클립보드 복사
        </button>
      </div>
    </div>

    <!-- 공지 미리보기 -->
    <div class="bg-gray-50 rounded-lg p-4 mb-4">
      <p id="posting-preview-text" class="text-[14px] text-gray-700 whitespace-pre-wrap">{{ project.posting_text }}</p>
    </div>
  {% else %}
    <!-- 공지 미생성 상태 -->
    {% if project.jd_text or project.jd_raw_text %}
    <div class="text-center py-4">
      <p class="text-[14px] text-gray-400 mb-3">공지가 아직 생성되지 않았습니다.</p>
      <button hx-post="{% url 'projects:posting_generate' project.pk %}"
              hx-target="#posting-section"
              hx-swap="outerHTML"
              hx-indicator="#posting-loading"
              class="px-4 py-2 bg-primary text-white text-[14px] rounded-lg hover:bg-primary-dark transition">
        공지 생성
      </button>
      <div id="posting-loading" class="htmx-indicator mt-2">
        <span class="text-[13px] text-gray-400">생성 중...</span>
      </div>
    </div>
    {% else %}
    <p class="text-[14px] text-gray-400">JD를 먼저 등록해주세요.</p>
    {% endif %}
  {% endif %}

  <!-- 포스팅 현황 -->
  <div class="border-t border-gray-100 pt-4 mt-4"
       hx-get="{% url 'projects:posting_sites' project.pk %}"
       hx-trigger="postingSiteChanged from:body"
       hx-target="#posting-sites-area">
    <div id="posting-sites-area">
      {% include "projects/partials/posting_sites.html" %}
    </div>
  </div>
</section>
```

- [ ] **Step 2: Create posting_sites.html**

Create `projects/templates/projects/partials/posting_sites.html`:

```html
<div class="flex items-center justify-between mb-3">
  <h3 class="text-[14px] font-medium text-gray-500">포스팅 현황</h3>
  <button hx-get="{% url 'projects:posting_site_add' project.pk %}"
          hx-target="#posting-site-form-area"
          hx-swap="innerHTML"
          class="text-[13px] text-primary hover:text-primary-dark font-medium transition">
    + 포스팅 추가
  </button>
</div>

<div id="posting-site-form-area"></div>

{% if posting_sites %}
<div class="space-y-2">
  {% for site in posting_sites %}
  <div class="flex items-center justify-between text-[14px] py-1.5">
    <div class="flex items-center gap-3">
      <span class="text-green-500">&#10003;</span>
      <span class="text-gray-800 font-medium w-20">{{ site.get_site_display }}</span>
      <span class="text-gray-400">{{ site.posted_at|date:"m/d"|default:"미게시" }}</span>
      <span class="text-gray-600">지원자: {{ site.applicant_count }}명</span>
    </div>
    <div class="flex items-center gap-2">
      <button hx-get="{% url 'projects:posting_site_update' project.pk site.pk %}"
              hx-target="#posting-site-form-area"
              hx-swap="innerHTML"
              class="text-[13px] text-gray-500 hover:text-primary transition">
        수정
      </button>
      <button hx-post="{% url 'projects:posting_site_delete' project.pk site.pk %}"
              hx-confirm="이 포스팅 사이트를 비활성화하시겠습니까?"
              class="text-[13px] text-gray-400 hover:text-red-500 transition">
        삭제
      </button>
    </div>
  </div>
  {% endfor %}
</div>

<div class="mt-3 pt-2 border-t border-gray-50 text-[14px] text-gray-600">
  합계 지원자: <span class="font-semibold text-gray-800">{{ total_applicants }}명</span>
</div>
{% else %}
<p class="text-[14px] text-gray-400">등록된 포스팅 사이트가 없습니다.</p>
{% endif %}
```

- [ ] **Step 3: Create posting_site_form.html**

Create `projects/templates/projects/partials/posting_site_form.html`:

```html
<div class="bg-gray-50 rounded-lg p-4 mb-3">
  <h4 class="text-[14px] font-medium text-gray-700 mb-3">
    {% if is_edit %}포스팅 수정{% else %}포스팅 추가{% endif %}
  </h4>
  <form {% if is_edit %}
          hx-post="{% url 'projects:posting_site_update' project.pk site.pk %}"
        {% else %}
          hx-post="{% url 'projects:posting_site_add' project.pk %}"
        {% endif %}
        hx-target="#posting-site-form-area"
        hx-swap="innerHTML">
    {% csrf_token %}

    <div class="grid grid-cols-2 gap-3 mb-3">
      <div>
        <label class="block text-[13px] text-gray-500 mb-1">{{ form.site.label }}</label>
        {{ form.site }}
        {% if form.site.errors %}
        <p class="text-[12px] text-red-500 mt-0.5">{{ form.site.errors.0 }}</p>
        {% endif %}
      </div>
      <div>
        <label class="block text-[13px] text-gray-500 mb-1">{{ form.posted_at.label }}</label>
        {{ form.posted_at }}
      </div>
    </div>

    <div class="grid grid-cols-2 gap-3 mb-3">
      <div>
        <label class="block text-[13px] text-gray-500 mb-1">{{ form.applicant_count.label }}</label>
        {{ form.applicant_count }}
      </div>
      <div>
        <label class="block text-[13px] text-gray-500 mb-1">{{ form.url.label }}</label>
        {{ form.url }}
      </div>
    </div>

    <div class="mb-3">
      <label class="block text-[13px] text-gray-500 mb-1">{{ form.notes.label }}</label>
      {{ form.notes }}
    </div>

    <div class="flex items-center gap-2">
      <button type="submit"
              class="px-3 py-1.5 bg-primary text-white text-[13px] rounded-lg hover:bg-primary-dark transition">
        저장
      </button>
      <button type="button"
              hx-get="{% url 'projects:posting_sites' project.pk %}"
              hx-target="#posting-sites-area"
              hx-swap="innerHTML"
              class="px-3 py-1.5 text-gray-500 text-[13px] hover:text-gray-700 transition">
        취소
      </button>
    </div>
  </form>
</div>
```

- [ ] **Step 4: Create posting_edit.html**

Create `projects/templates/projects/partials/posting_edit.html`:

```html
<section id="posting-section" class="bg-white rounded-lg border border-gray-100 p-5">
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-[15px] font-semibold text-gray-500">공지 편집</h2>
  </div>

  <form hx-post="{% url 'projects:posting_edit' project.pk %}"
        hx-target="#posting-section"
        hx-swap="outerHTML">
    {% csrf_token %}

    <div class="mb-4">
      {{ form.posting_text }}
      {% if form.posting_text.errors %}
      <p class="text-[12px] text-red-500 mt-1">{{ form.posting_text.errors.0 }}</p>
      {% endif %}
    </div>

    <div class="flex items-center gap-2">
      <button hx-post="{% url 'projects:posting_generate' project.pk %}"
              hx-target="#posting-section"
              hx-swap="outerHTML"
              hx-confirm="기존 내용을 덮어쓰시겠습니까? AI가 새로 생성합니다."
              type="button"
              class="px-3 py-1.5 text-orange-600 text-[13px] border border-orange-300 rounded-lg hover:bg-orange-50 transition">
        AI 재생성
      </button>
      <button type="submit"
              class="px-4 py-1.5 bg-primary text-white text-[13px] rounded-lg hover:bg-primary-dark transition">
        저장
      </button>
      <button hx-get="{% url 'projects:project_tab_overview' project.pk %}"
              hx-target="#tab-content"
              type="button"
              class="px-3 py-1.5 text-gray-500 text-[13px] hover:text-gray-700 transition">
        취소
      </button>
    </div>
  </form>
</section>
```

- [ ] **Step 5: Update _build_overview_context and project_tab_overview**

In `projects/views.py`, modify `_build_overview_context` to include posting data:

```python
def _build_overview_context(project):
    """개요 탭 공통 컨텍스트."""
    funnel = {
        "contacts": project.contacts.count(),
        "submissions": project.submissions.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
        "offers": Offer.objects.filter(submission__project=project).count(),
    }

    recent_contacts = project.contacts.select_related(
        "candidate", "consultant"
    ).order_by("-contacted_at")[:3]
    recent_submissions = project.submissions.select_related(
        "candidate", "consultant"
    ).order_by("-created_at")[:2]

    consultants = project.assigned_consultants.all()

    # P10: posting data
    posting_sites = project.posting_sites.filter(is_active=True)
    total_applicants = sum(s.applicant_count for s in posting_sites)

    return {
        "funnel": funnel,
        "recent_contacts": recent_contacts,
        "recent_submissions": recent_submissions,
        "consultants": consultants,
        "posting_sites": posting_sites,
        "total_applicants": total_applicants,
    }
```

- [ ] **Step 6: Update tab_overview.html to include posting section**

In `projects/templates/projects/partials/tab_overview.html`, add between the JD summary section and the funnel section (after line 84, before line 87):

```html
  <!-- P10: 공지 섹션 -->
  {% include "projects/partials/posting_section.html" %}
```

- [ ] **Step 7: Run all tests**

Run: `uv run pytest tests/test_p10_posting.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add projects/templates/projects/partials/posting_section.html \
    projects/templates/projects/partials/posting_sites.html \
    projects/templates/projects/partials/posting_site_form.html \
    projects/templates/projects/partials/posting_edit.html \
    projects/templates/projects/partials/tab_overview.html \
    projects/views.py
git commit -m "feat(p10): add posting section templates and overview tab integration"
```

---

### Task 7: Final Integration Test + Lint

**Files:**
- Test: `tests/test_p10_posting.py` (append)
- All modified files

- [ ] **Step 1: Write integration tests**

Append to `tests/test_p10_posting.py`:

```python
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

    def test_overview_shows_posting_site_counts(self, auth_client, project, posting_site):
        """포스팅 현황에 지원자 합계 표시."""
        url = reverse("projects:project_tab_overview", args=[project.pk])
        resp = auth_client.get(url)
        content = resp.content.decode()
        assert "잡코리아" in content
        assert "3명" in content
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/test_p10_posting.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run lint**

Run: `uv run ruff check projects/ tests/test_p10_posting.py`
Expected: No errors

Run: `uv run ruff format projects/ tests/test_p10_posting.py`
Expected: Files formatted

- [ ] **Step 4: Run entire project test suite**

Run: `uv run pytest -v --tb=short`
Expected: All tests PASS (no regressions)

- [ ] **Step 5: Commit**

```bash
git add tests/test_p10_posting.py
git commit -m "feat(p10): add integration tests for posting section in overview tab"
```
