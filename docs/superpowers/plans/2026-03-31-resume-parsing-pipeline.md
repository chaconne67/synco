# Resume Parsing Pipeline (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Google Drive의 .doc/.docx 이력서 파일을 자동으로 다운로드 → 텍스트 추출 → LLM 구조화 → 검증하여 Candidate DB로 전환하는 파이프라인 구축

**Architecture:** 새 `candidates` Django 앱에 Candidate/Resume/Education/Career 등 모델 생성. Google Drive API로 파일 동기화, antiword/python-docx로 텍스트 추출, LLM(call_llm_json)으로 구조화 추출, 3단계 검증(LLM confidence + 규칙 기반 + 교차 검증). Management command로 배치 실행.

**Tech Stack:** Django 5.2, PostgreSQL 16 + pgvector, Google Drive API (google-api-python-client), antiword + python-docx, common/llm.py (call_llm_json), HTMX + Tailwind

**Design Docs:**
- `docs/v2/design-office-hours.md` — Phase 1 상세 (9개 컴포넌트)
- `docs/v1/04-product/schema-pivot.md` — DB 스키마 상세
- `docs/v2/design-voice-search.md` — Phase 2 참조 (CandidateEmbedding 등)

---

## File Structure

```
candidates/                          # 새 Django 앱
├── __init__.py
├── models.py                        # Candidate, Category, Resume, Education, Career,
│                                    #   Certification, LanguageSkill, ExtractionLog
├── admin.py                         # Admin 등록
├── apps.py                          # AppConfig
├── urls.py                          # URL 라우팅
├── views.py                         # 리뷰 UI (needs_review 리스트, 수정/확인)
├── services/
│   ├── __init__.py
│   ├── drive_sync.py                # Google Drive 동기화 (파일 목록 + 다운로드)
│   ├── text_extraction.py           # .doc/.docx → raw text
│   ├── filename_parser.py           # 파일명에서 이름+생년 추출 + 그룹핑
│   ├── llm_extraction.py            # LLM 구조화 추출 (call_llm_json)
│   └── validation.py                # 3단계 검증 시스템
├── management/
│   └── commands/
│       └── import_resumes.py        # 배치 import 커맨드
├── fixtures/
│   └── categories.json              # 20개 카테고리 초기 데이터
├── migrations/
│   └── 0001_initial.py              # (자동 생성)
└── templates/
    └── candidates/
        ├── review_list.html         # 전체 페이지 (base.html 확장)
        ├── review_detail.html       # 전체 페이지 (base.html 확장)
        └── partials/
            ├── review_list_content.html   # HTMX partial
            └── review_detail_content.html # HTMX partial

tests/
├── test_candidates_models.py        # 모델 생성/유효성/관계 테스트
├── test_filename_parser.py          # 파일명 파싱 패턴 테스트
├── test_text_extraction.py          # 텍스트 추출 테스트
├── test_llm_extraction.py           # LLM 추출 (mock) 테스트
├── test_validation.py               # 검증 시스템 테스트
└── test_import_pipeline.py          # 파이프라인 idempotency 테스트

conftest.py                          # user fixture 확장 (기존)
main/settings.py                     # INSTALLED_APPS에 'candidates' 추가
main/urls.py                         # candidates URL include 추가
```

---

## Task 1: Django 앱 생성 + 모델 정의

**Files:**
- Create: `candidates/__init__.py`, `candidates/apps.py`, `candidates/admin.py`
- Create: `candidates/models.py`
- Create: `candidates/fixtures/categories.json`
- Modify: `main/settings.py` — INSTALLED_APPS에 추가
- Test: `tests/test_candidates_models.py`

### Step 1: 앱 뼈대 생성

- [ ] **1.1: Django app 생성**

```bash
cd /home/work/synco && uv run python manage.py startapp candidates
```

- [ ] **1.2: apps.py 확인 및 수정**

`candidates/apps.py`가 생성되어 있을 것. 내용 확인:
```python
from django.apps import AppConfig


class CandidatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "candidates"
```

- [ ] **1.3: settings.py에 앱 등록**

`main/settings.py`의 INSTALLED_APPS에 추가:
```python
INSTALLED_APPS = [
    # ...existing...
    # Local
    "accounts",
    "contacts",
    "meetings",
    "intelligence",
    "candidates",  # 추가
]
```

- [ ] **1.4: services 디렉토리 생성**

```bash
mkdir -p candidates/services
touch candidates/services/__init__.py
```

### Step 2: 모델 작성

- [ ] **2.1: models.py 작성**

`candidates/models.py` — schema-pivot.md 기반, Phase 1에 필요한 모델만:

```python
from django.conf import settings
from django.db import models

from common.mixins import BaseModel


class Category(BaseModel):
    """직무 카테고리 (20개 고정)."""

    name = models.CharField(max_length=50, unique=True)
    name_ko = models.CharField(max_length=50)
    candidate_count = models.IntegerField(default=0)

    class Meta:
        db_table = "categories"
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return f"{self.name} ({self.name_ko})"


class Candidate(BaseModel):
    """후보자 — 이력서에서 추출된 인물."""

    class Status(models.TextChoices):
        ACTIVE = "active", "활성"
        PLACED = "placed", "배치완료"
        INACTIVE = "inactive", "비활성"

    class Source(models.TextChoices):
        DRIVE_IMPORT = "drive_import", "드라이브 임포트"
        MANUAL = "manual", "수동 입력"
        REFERRAL = "referral", "추천"

    class ValidationStatus(models.TextChoices):
        AUTO_CONFIRMED = "auto_confirmed", "자동 확인"
        NEEDS_REVIEW = "needs_review", "검토 필요"
        CONFIRMED = "confirmed", "확인 완료"
        FAILED = "failed", "실패"

    name = models.CharField(max_length=50)
    name_en = models.CharField(max_length=100, blank=True)
    birth_year = models.SmallIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=1, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=200, blank=True)

    categories = models.ManyToManyField(Category, blank=True, related_name="candidates")
    primary_category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_candidates",
    )

    total_experience_years = models.SmallIntegerField(null=True, blank=True)
    current_company = models.CharField(max_length=100, blank=True)
    current_position = models.CharField(max_length=100, blank=True)
    current_salary = models.IntegerField(null=True, blank=True, help_text="만원")
    desired_salary = models.IntegerField(null=True, blank=True, help_text="만원")
    core_competencies = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True)

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    source = models.CharField(
        max_length=15, choices=Source.choices, default=Source.DRIVE_IMPORT
    )
    raw_text = models.TextField(blank=True, help_text="이력서 전문 텍스트 (검색용)")

    # 추출 품질 관리
    validation_status = models.CharField(
        max_length=15,
        choices=ValidationStatus.choices,
        default=ValidationStatus.NEEDS_REVIEW,
    )
    raw_extracted_json = models.JSONField(null=True, blank=True)
    confidence_score = models.FloatField(null=True, blank=True)
    field_confidences = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "candidates"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["birth_year"]),
            models.Index(fields=["total_experience_years"]),
            models.Index(fields=["validation_status"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.current_company or '미상'})"


class Resume(BaseModel):
    """원본 이력서 파일 메타데이터."""

    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", "대기"
        DOWNLOADED = "downloaded", "다운로드 완료"
        EXTRACTED = "extracted", "텍스트 추출 완료"
        PARSED = "parsed", "파싱 완료"
        FAILED = "failed", "실패"

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="resumes",
    )
    file_name = models.CharField(max_length=300)
    drive_file_id = models.CharField(max_length=100, unique=True)
    drive_folder = models.CharField(max_length=50)
    mime_type = models.CharField(max_length=50, blank=True)
    file_size = models.IntegerField(null=True, blank=True)
    raw_text = models.TextField(blank=True)
    is_primary = models.BooleanField(default=False)
    version = models.SmallIntegerField(default=1)
    processing_status = models.CharField(
        max_length=12,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
    )
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "resumes"
        ordering = ["-created_at"]

    def __str__(self):
        return self.file_name


class Education(BaseModel):
    """학력."""

    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name="educations"
    )
    institution = models.CharField(max_length=100)
    degree = models.CharField(max_length=20, blank=True)
    major = models.CharField(max_length=100, blank=True)
    gpa = models.CharField(max_length=20, blank=True)
    start_year = models.SmallIntegerField(null=True, blank=True)
    end_year = models.SmallIntegerField(null=True, blank=True)
    is_abroad = models.BooleanField(default=False)

    class Meta:
        db_table = "educations"
        ordering = ["-end_year"]

    def __str__(self):
        return f"{self.institution} {self.major}"


class Career(BaseModel):
    """경력."""

    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name="careers"
    )
    company = models.CharField(max_length=100)
    company_en = models.CharField(max_length=100, blank=True)
    position = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    start_date = models.CharField(max_length=20, blank=True)
    end_date = models.CharField(max_length=20, blank=True)
    is_current = models.BooleanField(default=False)
    duties = models.TextField(blank=True)
    achievements = models.TextField(blank=True)
    reason_left = models.CharField(max_length=200, blank=True)
    salary = models.IntegerField(null=True, blank=True, help_text="만원")
    order = models.SmallIntegerField(default=0)

    class Meta:
        db_table = "careers"
        ordering = ["order"]
        indexes = [
            models.Index(fields=["company"]),
        ]

    def __str__(self):
        return f"{self.company} - {self.position}"


class Certification(BaseModel):
    """자격증."""

    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name="certifications"
    )
    name = models.CharField(max_length=100)
    issuer = models.CharField(max_length=100, blank=True)
    acquired_date = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = "certifications"

    def __str__(self):
        return self.name


class LanguageSkill(BaseModel):
    """어학능력."""

    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name="language_skills"
    )
    language = models.CharField(max_length=30)
    test_name = models.CharField(max_length=50, blank=True)
    score = models.CharField(max_length=30, blank=True)
    level = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = "language_skills"

    def __str__(self):
        return f"{self.language} {self.test_name} {self.score}"


class ExtractionLog(BaseModel):
    """추출 품질 추적 + 사람 수정 내역."""

    class Action(models.TextChoices):
        AUTO_EXTRACT = "auto_extract", "자동 추출"
        HUMAN_EDIT = "human_edit", "수동 수정"
        HUMAN_CONFIRM = "human_confirm", "수동 확인"
        HUMAN_REJECT = "human_reject", "수동 거부"

    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name="extraction_logs"
    )
    resume = models.ForeignKey(
        Resume, on_delete=models.SET_NULL, null=True, blank=True
    )
    action = models.CharField(max_length=15, choices=Action.choices)
    field_name = models.CharField(max_length=50, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "extraction_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} - {self.candidate.name}"
```

- [ ] **2.2: admin.py 작성**

`candidates/admin.py`:

```python
from django.contrib import admin

from .models import (
    Candidate,
    Career,
    Category,
    Certification,
    Education,
    ExtractionLog,
    LanguageSkill,
    Resume,
)


class ResumeInline(admin.TabularInline):
    model = Resume
    extra = 0


class CareerInline(admin.TabularInline):
    model = Career
    extra = 0


class EducationInline(admin.TabularInline):
    model = Education
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "name_ko", "candidate_count"]


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ["name", "current_company", "validation_status", "confidence_score"]
    list_filter = ["validation_status", "status", "primary_category"]
    search_fields = ["name", "current_company"]
    inlines = [ResumeInline, CareerInline, EducationInline]


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ["file_name", "drive_folder", "processing_status", "candidate"]
    list_filter = ["processing_status", "drive_folder"]


@admin.register(ExtractionLog)
class ExtractionLogAdmin(admin.ModelAdmin):
    list_display = ["candidate", "action", "field_name", "created_at"]
    list_filter = ["action"]
```

### Step 3: 카테고리 Fixture

- [ ] **3.1: categories.json 작성**

```bash
mkdir -p candidates/fixtures
```

`candidates/fixtures/categories.json`:

```json
[
  {"model": "candidates.category", "fields": {"name": "Accounting", "name_ko": "회계", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "EHS", "name_ko": "환경안전", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "Engineer", "name_ko": "엔지니어", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "Finance", "name_ko": "재무", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "HR", "name_ko": "인사", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "Law", "name_ko": "법무", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "Logistics", "name_ko": "물류", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "Marketing", "name_ko": "마케팅", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "MD", "name_ko": "MD", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "MR", "name_ko": "MR", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "Plant", "name_ko": "플랜트", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "PR+AD", "name_ko": "홍보광고", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "Procurement", "name_ko": "구매", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "Production", "name_ko": "생산", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "Quality", "name_ko": "품질", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "R&D", "name_ko": "연구개발", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "Sales", "name_ko": "영업", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "SCM", "name_ko": "SCM", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "SI+IT", "name_ko": "IT", "candidate_count": 0}},
  {"model": "candidates.category", "fields": {"name": "VMD", "name_ko": "VMD", "candidate_count": 0}}
]
```

### Step 4: 마이그레이션 + 테스트

- [ ] **4.1: 마이그레이션 생성 및 적용**

```bash
uv run python manage.py makemigrations candidates
uv run python manage.py migrate
```

- [ ] **4.2: Fixture 로드**

```bash
uv run python manage.py loaddata categories
```

- [ ] **4.3: 모델 테스트 작성**

`tests/test_candidates_models.py`:

```python
import pytest
from candidates.models import (
    Candidate,
    Career,
    Category,
    Certification,
    Education,
    ExtractionLog,
    LanguageSkill,
    Resume,
)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Accounting", name_ko="회계")


@pytest.fixture
def candidate(db, category):
    c = Candidate.objects.create(
        name="강솔찬",
        birth_year=1985,
        current_company="현대엠시트",
        current_position="회계팀장",
        primary_category=category,
        source=Candidate.Source.DRIVE_IMPORT,
    )
    c.categories.add(category)
    return c


@pytest.fixture
def resume(db, candidate):
    return Resume.objects.create(
        candidate=candidate,
        file_name="강솔찬.85.나디아.현대엠시트.인천대.doc",
        drive_file_id="abc123",
        drive_folder="Accounting",
        is_primary=True,
    )


class TestCategory:
    def test_create(self, category):
        assert category.name == "Accounting"
        assert str(category) == "Accounting (회계)"

    def test_unique_name(self, category, db):
        with pytest.raises(Exception):
            Category.objects.create(name="Accounting", name_ko="회계2")


class TestCandidate:
    def test_create(self, candidate, category):
        assert candidate.name == "강솔찬"
        assert candidate.primary_category == category
        assert category in candidate.categories.all()

    def test_default_status(self, candidate):
        assert candidate.status == Candidate.Status.ACTIVE

    def test_default_validation_status(self, candidate):
        assert candidate.validation_status == Candidate.ValidationStatus.NEEDS_REVIEW

    def test_str(self, candidate):
        assert "강솔찬" in str(candidate)
        assert "현대엠시트" in str(candidate)


class TestResume:
    def test_create(self, resume, candidate):
        assert resume.candidate == candidate
        assert resume.is_primary is True
        assert resume.processing_status == Resume.ProcessingStatus.PENDING

    def test_unique_drive_file_id(self, resume, candidate, db):
        with pytest.raises(Exception):
            Resume.objects.create(
                candidate=candidate,
                file_name="other.doc",
                drive_file_id="abc123",
                drive_folder="Sales",
            )


class TestRelations:
    def test_candidate_resumes(self, candidate, resume):
        assert candidate.resumes.count() == 1

    def test_candidate_careers(self, candidate, db):
        Career.objects.create(
            candidate=candidate,
            company="현대엠시트",
            position="회계팀장",
            is_current=True,
            order=0,
        )
        Career.objects.create(
            candidate=candidate,
            company="나디아",
            position="선임회계사",
            order=1,
        )
        assert candidate.careers.count() == 2
        assert candidate.careers.first().order == 0

    def test_candidate_educations(self, candidate, db):
        Education.objects.create(
            candidate=candidate,
            institution="인천대학교",
            degree="bachelor",
            major="경영학",
            end_year=2012,
        )
        assert candidate.educations.count() == 1

    def test_candidate_certifications(self, candidate, db):
        Certification.objects.create(
            candidate=candidate,
            name="CPA",
            acquired_date="2013",
        )
        assert candidate.certifications.count() == 1

    def test_candidate_language_skills(self, candidate, db):
        LanguageSkill.objects.create(
            candidate=candidate,
            language="영어",
            test_name="TOEIC",
            score="900",
        )
        assert candidate.language_skills.count() == 1

    def test_extraction_log(self, candidate, resume, db):
        log = ExtractionLog.objects.create(
            candidate=candidate,
            resume=resume,
            action=ExtractionLog.Action.AUTO_EXTRACT,
            confidence=0.92,
        )
        assert candidate.extraction_logs.count() == 1
        assert log.confidence == 0.92
```

- [ ] **4.4: 테스트 실행**

```bash
uv run pytest tests/test_candidates_models.py -v
```

Expected: All tests PASS.

- [ ] **4.5: Commit**

```bash
git add candidates/ tests/test_candidates_models.py main/settings.py
git commit -m "feat: add candidates app with models, fixtures, and tests

New Django app for headhunting platform Phase 1.
Models: Candidate, Category, Resume, Education, Career,
Certification, LanguageSkill, ExtractionLog.
20 category fixtures loaded."
```

---

## Task 2: 파일명 파서

**Files:**
- Create: `candidates/services/filename_parser.py`
- Test: `tests/test_filename_parser.py`

- [ ] **2.1: 파일명 파서 테스트 작성**

`tests/test_filename_parser.py`:

```python
import pytest
from candidates.services.filename_parser import parse_filename, group_by_person


class TestParseFilename:
    """파일명에서 이름+생년 추출. 패턴: '강솔찬.85.나디아.현대엠시트.인천대.doc'"""

    def test_standard_format(self):
        result = parse_filename("강솔찬.85.나디아.현대엠시트.인천대.doc")
        assert result["name"] == "강솔찬"
        assert result["birth_year"] == 1985

    def test_two_digit_year_90s(self):
        result = parse_filename("김영희.92.삼성전자.서울대.doc")
        assert result["name"] == "김영희"
        assert result["birth_year"] == 1992

    def test_two_digit_year_00s(self):
        result = parse_filename("박지민.01.LG.doc")
        assert result["name"] == "박지민"
        assert result["birth_year"] == 2001

    def test_four_digit_year(self):
        result = parse_filename("이수정.1988.SK.doc")
        assert result["name"] == "이수정"
        assert result["birth_year"] == 1988

    def test_docx_extension(self):
        result = parse_filename("최민수.79.현대.docx")
        assert result["name"] == "최민수"
        assert result["birth_year"] == 1979

    def test_no_birth_year(self):
        result = parse_filename("홍길동.이력서.doc")
        assert result["name"] == "홍길동"
        assert result["birth_year"] is None

    def test_extra_metadata(self):
        result = parse_filename("강원용.81.나디아.현대엠시트.인천대.doc")
        assert result["name"] == "강원용"
        assert result["birth_year"] == 1981
        assert "나디아" in result["extra"]

    def test_hyphen_separator(self):
        result = parse_filename("강솔찬-85-현대엠시트.doc")
        assert result["name"] == "강솔찬"
        assert result["birth_year"] == 1985

    def test_underscore_separator(self):
        result = parse_filename("강솔찬_85_현대.doc")
        assert result["name"] == "강솔찬"
        assert result["birth_year"] == 1985

    def test_parentheses_year(self):
        result = parse_filename("강솔찬(85).현대.doc")
        assert result["name"] == "강솔찬"
        assert result["birth_year"] == 1985

    def test_unparseable(self):
        result = parse_filename("이력서양식.doc")
        assert result["name"] is None
        assert result["birth_year"] is None


class TestGroupByPerson:
    """같은 이름+생년 파일을 그룹으로 묶고, 그룹당 최신 파일만 선택."""

    def test_single_file(self):
        files = [
            {"file_name": "강솔찬.85.현대.doc", "modified_time": "2024-01-01T00:00:00Z"},
        ]
        groups = group_by_person(files)
        assert len(groups) == 1
        assert groups[0]["primary"]["file_name"] == "강솔찬.85.현대.doc"

    def test_multiple_versions(self):
        files = [
            {"file_name": "강솔찬.85.나디아.doc", "modified_time": "2020-01-01T00:00:00Z"},
            {"file_name": "강솔찬.85.현대.doc", "modified_time": "2024-06-01T00:00:00Z"},
        ]
        groups = group_by_person(files)
        assert len(groups) == 1
        assert groups[0]["primary"]["file_name"] == "강솔찬.85.현대.doc"
        assert len(groups[0]["others"]) == 1

    def test_different_people(self):
        files = [
            {"file_name": "강솔찬.85.현대.doc", "modified_time": "2024-01-01T00:00:00Z"},
            {"file_name": "김영희.92.삼성.doc", "modified_time": "2024-01-01T00:00:00Z"},
        ]
        groups = group_by_person(files)
        assert len(groups) == 2

    def test_unparseable_files_as_individual_groups(self):
        files = [
            {"file_name": "이력서양식.doc", "modified_time": "2024-01-01T00:00:00Z"},
            {"file_name": "강솔찬.85.현대.doc", "modified_time": "2024-01-01T00:00:00Z"},
        ]
        groups = group_by_person(files)
        assert len(groups) == 2
```

- [ ] **2.2: 테스트 실행 — 실패 확인**

```bash
uv run pytest tests/test_filename_parser.py -v
```

Expected: FAIL (module not found)

- [ ] **2.3: 파일명 파서 구현**

`candidates/services/filename_parser.py`:

```python
"""파일명에서 이름+생년 추출 및 동일 인물 그룹핑.

패턴 예시: '강솔찬.85.나디아.현대엠시트.인천대.doc'
구분자: . - _ 또는 괄호
"""

import re


# 한글 이름 (2-4글자) + 구분자 + 2~4자리 숫자(생년)
_PATTERNS = [
    # 이름.생년 or 이름-생년 or 이름_생년
    re.compile(
        r"^(?P<name>[가-힣]{2,4})[.\-_](?P<year>\d{2,4})[.\-_)(\s]"
    ),
    # 이름(생년)
    re.compile(
        r"^(?P<name>[가-힣]{2,4})\((?P<year>\d{2,4})\)"
    ),
]

# 이름만 (생년 없음)
_NAME_ONLY = re.compile(r"^(?P<name>[가-힣]{2,4})[.\-_(\s]")


def _normalize_year(year_str: str) -> int | None:
    """2자리/4자리 생년을 4자리로 변환."""
    if not year_str:
        return None
    year = int(year_str)
    if year >= 1950 and year <= 2010:
        return year
    if year >= 50 and year <= 99:
        return 1900 + year
    if year >= 0 and year <= 25:
        return 2000 + year
    return None


def parse_filename(file_name: str) -> dict:
    """파일명에서 이름, 생년, 추가 메타데이터 추출.

    Returns:
        {"name": str|None, "birth_year": int|None, "extra": list[str]}
    """
    # 확장자 제거
    base = re.sub(r"\.(docx?|pdf|hwp)$", "", file_name, flags=re.IGNORECASE)

    for pattern in _PATTERNS:
        m = pattern.search(base)
        if m:
            name = m.group("name")
            birth_year = _normalize_year(m.group("year"))
            # 나머지를 extra로
            rest = base[m.end() :].strip(".·-_ ")
            extra = [p for p in re.split(r"[.\-_]", rest) if p.strip()]
            return {"name": name, "birth_year": birth_year, "extra": extra}

    # 이름만 매칭
    m = _NAME_ONLY.search(base)
    if m:
        name = m.group("name")
        rest = base[m.end() :].strip(".·-_ ")
        extra = [p for p in re.split(r"[.\-_]", rest) if p.strip()]
        return {"name": name, "birth_year": None, "extra": extra}

    return {"name": None, "birth_year": None, "extra": []}


def group_by_person(files: list[dict]) -> list[dict]:
    """파일 목록을 이름+생년으로 그룹핑. 그룹당 최신 파일이 primary.

    Args:
        files: [{"file_name": str, "modified_time": str, ...}, ...]

    Returns:
        [{"key": (name, year), "primary": file_dict, "others": [file_dict, ...]}, ...]
    """
    groups: dict[tuple, list[dict]] = {}

    for f in files:
        parsed = parse_filename(f["file_name"])
        if parsed["name"] and parsed["birth_year"]:
            key = (parsed["name"], parsed["birth_year"])
        else:
            # 파싱 실패 → 개별 그룹 (파일명 자체를 키로)
            key = (f["file_name"],)

        groups.setdefault(key, []).append(f)

    result = []
    for key, file_list in groups.items():
        # modified_time 기준 내림차순 정렬
        sorted_files = sorted(
            file_list, key=lambda x: x.get("modified_time", ""), reverse=True
        )
        result.append({
            "key": key,
            "parsed": parse_filename(sorted_files[0]["file_name"]),
            "primary": sorted_files[0],
            "others": sorted_files[1:],
        })

    return result
```

- [ ] **2.4: 테스트 실행 — 통과 확인**

```bash
uv run pytest tests/test_filename_parser.py -v
```

Expected: All PASS.

- [ ] **2.5: Commit**

```bash
git add candidates/services/filename_parser.py tests/test_filename_parser.py
git commit -m "feat: filename parser for resume file grouping

Extract name + birth year from Korean resume filenames.
Group files by person, select most recent as primary."
```

---

## Task 3: 텍스트 추출 서비스

**Files:**
- Create: `candidates/services/text_extraction.py`
- Test: `tests/test_text_extraction.py`

- [ ] **3.1: 텍스트 추출 테스트 작성**

`tests/test_text_extraction.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from candidates.services.text_extraction import extract_text


class TestExtractText:
    def test_docx_extraction(self, tmp_path):
        """python-docx로 .docx 파일에서 텍스트 추출."""
        from docx import Document

        doc = Document()
        doc.add_paragraph("강솔찬")
        doc.add_paragraph("현대엠시트 회계팀장")
        filepath = tmp_path / "test.docx"
        doc.save(filepath)

        text = extract_text(str(filepath))
        assert "강솔찬" in text
        assert "현대엠시트" in text

    @patch("candidates.services.text_extraction._extract_doc_antiword")
    def test_doc_extraction_antiword_success(self, mock_antiword, tmp_path):
        """antiword로 .doc 추출 성공."""
        mock_antiword.return_value = "강솔찬\n현대엠시트 회계팀장"
        filepath = tmp_path / "test.doc"
        filepath.write_bytes(b"fake doc content")

        text = extract_text(str(filepath))
        assert "강솔찬" in text
        mock_antiword.assert_called_once()

    @patch("candidates.services.text_extraction._extract_doc_libreoffice")
    @patch("candidates.services.text_extraction._extract_doc_antiword")
    def test_doc_fallback_to_libreoffice(self, mock_antiword, mock_libre, tmp_path):
        """antiword 실패 시 LibreOffice fallback."""
        mock_antiword.side_effect = RuntimeError("antiword failed")
        mock_libre.return_value = "강솔찬 이력서"
        filepath = tmp_path / "test.doc"
        filepath.write_bytes(b"fake doc content")

        text = extract_text(str(filepath))
        assert "강솔찬" in text
        mock_libre.assert_called_once()

    def test_unsupported_extension(self, tmp_path):
        filepath = tmp_path / "test.hwp"
        filepath.write_bytes(b"fake")
        with pytest.raises(ValueError, match="지원하지 않는"):
            extract_text(str(filepath))

    def test_empty_extraction(self, tmp_path):
        """빈 docx 파일 → 빈 문자열."""
        from docx import Document

        doc = Document()
        filepath = tmp_path / "empty.docx"
        doc.save(filepath)

        text = extract_text(str(filepath))
        assert text == ""
```

- [ ] **3.2: 테스트 실행 — 실패 확인**

```bash
uv run pytest tests/test_text_extraction.py -v
```

- [ ] **3.3: 텍스트 추출 서비스 구현**

`candidates/services/text_extraction.py`:

```python
"""이력서 텍스트 추출. .docx → python-docx, .doc → antiword (fallback: LibreOffice)."""

import logging
import subprocess
import tempfile
from pathlib import Path

from docx import Document

logger = logging.getLogger(__name__)


def extract_text(file_path: str) -> str:
    """파일 경로에서 텍스트 추출.

    Args:
        file_path: .doc 또는 .docx 파일 경로

    Returns:
        추출된 텍스트 (빈 문서면 빈 문자열)

    Raises:
        ValueError: 지원하지 않는 확장자
        RuntimeError: 추출 실패
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".docx":
        return _extract_docx(file_path)
    elif ext == ".doc":
        return _extract_doc(file_path)
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {ext}")


def _extract_docx(file_path: str) -> str:
    """python-docx로 .docx 텍스트 추출."""
    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def _extract_doc(file_path: str) -> str:
    """antiword → LibreOffice fallback으로 .doc 텍스트 추출."""
    try:
        return _extract_doc_antiword(file_path)
    except Exception as e:
        logger.warning("antiword failed for %s: %s, trying LibreOffice", file_path, e)
        return _extract_doc_libreoffice(file_path)


def _extract_doc_antiword(file_path: str) -> str:
    """antiword로 .doc 텍스트 추출."""
    result = subprocess.run(
        ["antiword", file_path],
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"antiword error: {result.stderr.decode(errors='replace')}")

    # EUC-KR 인코딩 시도 → 실패 시 UTF-8 → latin-1 순서
    for encoding in ["utf-8", "euc-kr", "cp949", "latin-1"]:
        try:
            return result.stdout.decode(encoding).strip()
        except UnicodeDecodeError:
            continue

    return result.stdout.decode("utf-8", errors="replace").strip()


def _extract_doc_libreoffice(file_path: str) -> str:
    """LibreOffice headless로 .doc → .txt 변환 후 텍스트 추출."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to",
                "txt:Text",
                "--outdir",
                tmpdir,
                file_path,
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"LibreOffice error: {result.stderr.decode(errors='replace')}"
            )

        # 변환된 .txt 파일 찾기
        txt_files = list(Path(tmpdir).glob("*.txt"))
        if not txt_files:
            raise RuntimeError("LibreOffice produced no output")

        # 여러 인코딩 시도
        content = txt_files[0].read_bytes()
        for encoding in ["utf-8", "euc-kr", "cp949", "latin-1"]:
            try:
                return content.decode(encoding).strip()
            except UnicodeDecodeError:
                continue

        return content.decode("utf-8", errors="replace").strip()
```

- [ ] **3.4: 테스트 실행 — 통과 확인**

```bash
uv run pytest tests/test_text_extraction.py -v
```

- [ ] **3.5: Commit**

```bash
git add candidates/services/text_extraction.py tests/test_text_extraction.py
git commit -m "feat: text extraction service for .doc/.docx resumes

python-docx for .docx, antiword for .doc with LibreOffice fallback.
Handles EUC-KR/CP949 Korean encoding."
```

---

## Task 4: Google Drive Sync 서비스

**Files:**
- Create: `candidates/services/drive_sync.py`
- Test: `tests/test_drive_sync.py`

- [ ] **4.1: 드라이브 동기화 서비스 구현**

`candidates/services/drive_sync.py`:

```python
"""Google Drive 동기화: 카테고리 폴더 탐색 + 파일 다운로드.

OAuth 토큰은 assets/google_token.json, 클라이언트 시크릿은 assets/client_secret.json.
"""

import json
import logging
import tempfile
from pathlib import Path

from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN_PATH = Path(settings.BASE_DIR) / "assets" / "google_token.json"
CLIENT_SECRET_PATH = Path(settings.BASE_DIR) / "assets" / "client_secret.json"

# 20개 카테고리 폴더명 (Google Drive 폴더 구조)
CATEGORY_FOLDERS = [
    "Accounting", "EHS", "Engineer", "Finance", "HR",
    "Law", "Logistics", "Marketing", "MD", "MR",
    "Plant", "PR+AD", "Procurement", "Production", "Quality",
    "R&D", "Sales", "SCM", "SI+IT", "VMD",
]


def _get_credentials() -> Credentials:
    """OAuth 자격증명 로드 + 자동 갱신."""
    creds = None

    if TOKEN_PATH.exists():
        with open(TOKEN_PATH) as f:
            token_data = json.load(f)
        creds = Credentials(
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=_get_client_id(),
            client_secret=_get_client_secret(),
            scopes=SCOPES,
        )

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)

    if not creds or not creds.valid:
        raise RuntimeError(
            "Google Drive 인증 토큰이 만료되었습니다. "
            "assets/google_token.json을 갱신해주세요."
        )

    return creds


def _get_client_id() -> str:
    with open(CLIENT_SECRET_PATH) as f:
        data = json.load(f)
    return data.get("installed", data.get("web", {})).get("client_id", "")


def _get_client_secret() -> str:
    with open(CLIENT_SECRET_PATH) as f:
        data = json.load(f)
    return data.get("installed", data.get("web", {})).get("client_secret", "")


def _save_token(creds: Credentials):
    """갱신된 토큰 저장."""
    token_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "scope": " ".join(creds.scopes or SCOPES),
        "token_type": "Bearer",
    }
    with open(TOKEN_PATH, "w") as f:
        json.dump(token_data, f, indent=2)


def get_drive_service():
    """Google Drive API 서비스 객체."""
    creds = _get_credentials()
    return build("drive", "v3", credentials=creds)


def find_category_folder(service, parent_id: str, folder_name: str) -> str | None:
    """부모 폴더 아래에서 카테고리 폴더 ID 찾기."""
    query = (
        f"'{parent_id}' in parents "
        f"and name = '{folder_name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


def list_files_in_folder(
    service, folder_id: str, page_size: int = 1000
) -> list[dict]:
    """폴더 내 .doc/.docx 파일 목록 조회.

    Returns:
        [{"id": str, "name": str, "mimeType": str, "size": int, "modifiedTime": str}]
    """
    all_files = []
    page_token = None
    query = (
        f"'{folder_id}' in parents "
        f"and trashed = false "
        f"and (mimeType = 'application/msword' "
        f"or mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')"
    )

    while True:
        results = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                pageSize=page_size,
                pageToken=page_token,
            )
            .execute()
        )
        all_files.extend(results.get("files", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break

    return all_files


def download_file(service, file_id: str, dest_path: str) -> str:
    """Google Drive 파일을 로컬에 다운로드.

    Args:
        service: Drive API 서비스
        file_id: Google Drive 파일 ID
        dest_path: 저장할 로컬 경로

    Returns:
        저장된 파일 경로
    """
    import io

    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    with open(dest_path, "wb") as f:
        f.write(fh.getvalue())

    return dest_path


def list_root_folders(service) -> list[dict]:
    """Drive 루트의 폴더 목록 (카테고리 폴더 찾기용)."""
    query = (
        "'root' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    results = service.files().list(
        q=query, fields="files(id, name)", pageSize=100
    ).execute()
    return results.get("files", [])
```

- [ ] **4.2: 드라이브 동기화 테스트 작성 (mock)**

`tests/test_drive_sync.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from candidates.services.drive_sync import (
    list_files_in_folder,
    CATEGORY_FOLDERS,
)


class TestCategoryFolders:
    def test_has_20_categories(self):
        assert len(CATEGORY_FOLDERS) == 20

    def test_known_categories(self):
        assert "Accounting" in CATEGORY_FOLDERS
        assert "Sales" in CATEGORY_FOLDERS
        assert "SI+IT" in CATEGORY_FOLDERS


class TestListFiles:
    def test_list_files_returns_doc_files(self):
        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {
            "files": [
                {
                    "id": "file1",
                    "name": "강솔찬.85.현대.doc",
                    "mimeType": "application/msword",
                    "size": "12345",
                    "modifiedTime": "2024-01-01T00:00:00Z",
                },
            ],
            "nextPageToken": None,
        }

        files = list_files_in_folder(mock_service, "folder123")
        assert len(files) == 1
        assert files[0]["name"] == "강솔찬.85.현대.doc"
```

- [ ] **4.3: 테스트 실행**

```bash
uv run pytest tests/test_drive_sync.py -v
```

- [ ] **4.4: Commit**

```bash
git add candidates/services/drive_sync.py tests/test_drive_sync.py
git commit -m "feat: Google Drive sync service for resume download

OAuth token auto-refresh, category folder discovery,
file listing and download for .doc/.docx files."
```

---

## Task 5: LLM 구조화 추출

**Files:**
- Create: `candidates/services/llm_extraction.py`
- Test: `tests/test_llm_extraction.py`

- [ ] **5.1: LLM 추출 테스트 작성**

`tests/test_llm_extraction.py`:

```python
import pytest
from unittest.mock import patch
from candidates.services.llm_extraction import (
    extract_candidate_data,
    build_extraction_prompt,
    EXTRACTION_SYSTEM_PROMPT,
)


SAMPLE_RESUME_TEXT = """
이력서

성명: 강솔찬
생년월일: 1985년 3월 15일
연락처: 010-1234-5678
이메일: solchan@example.com

학력
- 인천대학교 경영학과 졸업 (2008)

경력
1. 현대엠시트 회계팀장 (2020.03 ~ 현재)
   - 재무제표 작성 및 결산 업무
   - 내부 회계 감사 대응

2. 나디아 선임회계사 (2015.01 ~ 2020.02)
   - 월결산, 분기결산 담당

3. EY한영 회계사 (2012.03 ~ 2014.12)

자격증
- CPA (2013년 취득)

어학
- TOEIC 900점 (2019)
"""


class TestBuildPrompt:
    def test_includes_resume_text(self):
        prompt = build_extraction_prompt(SAMPLE_RESUME_TEXT)
        assert "강솔찬" in prompt
        assert "현대엠시트" in prompt

    def test_includes_json_schema(self):
        prompt = build_extraction_prompt(SAMPLE_RESUME_TEXT)
        assert "birth_year" in prompt
        assert "careers" in prompt
        assert "confidence" in prompt

    def test_system_prompt_exists(self):
        assert len(EXTRACTION_SYSTEM_PROMPT) > 100


class TestExtractCandidateData:
    @patch("candidates.services.llm_extraction.call_llm_json")
    def test_successful_extraction(self, mock_llm):
        mock_llm.return_value = {
            "name": "강솔찬",
            "birth_year": 1985,
            "gender": "M",
            "email": "solchan@example.com",
            "phone": "010-1234-5678",
            "current_company": "현대엠시트",
            "current_position": "회계팀장",
            "total_experience_years": 12,
            "core_competencies": ["재무제표", "결산", "내부감사"],
            "summary": "12년차 회계 전문가",
            "educations": [
                {
                    "institution": "인천대학교",
                    "degree": "bachelor",
                    "major": "경영학",
                    "end_year": 2008,
                }
            ],
            "careers": [
                {
                    "company": "현대엠시트",
                    "position": "회계팀장",
                    "start_date": "2020.03",
                    "end_date": "",
                    "is_current": True,
                    "duties": "재무제표 작성 및 결산 업무, 내부 회계 감사 대응",
                    "order": 0,
                },
                {
                    "company": "나디아",
                    "position": "선임회계사",
                    "start_date": "2015.01",
                    "end_date": "2020.02",
                    "is_current": False,
                    "duties": "월결산, 분기결산 담당",
                    "order": 1,
                },
                {
                    "company": "EY한영",
                    "position": "회계사",
                    "start_date": "2012.03",
                    "end_date": "2014.12",
                    "is_current": False,
                    "duties": "",
                    "order": 2,
                },
            ],
            "certifications": [{"name": "CPA", "acquired_date": "2013"}],
            "language_skills": [
                {"language": "영어", "test_name": "TOEIC", "score": "900"}
            ],
            "field_confidences": {
                "name": 1.0,
                "birth_year": 0.95,
                "careers": 0.9,
                "educations": 0.85,
            },
        }

        result = extract_candidate_data(SAMPLE_RESUME_TEXT)

        assert result["name"] == "강솔찬"
        assert result["birth_year"] == 1985
        assert len(result["careers"]) == 3
        assert result["careers"][0]["is_current"] is True
        assert len(result["certifications"]) == 1
        assert "field_confidences" in result

    @patch("candidates.services.llm_extraction.call_llm_json")
    def test_retry_on_json_error(self, mock_llm):
        """JSON 파싱 실패 시 재시도."""
        mock_llm.side_effect = [
            Exception("JSON parse error"),
            {"name": "강솔찬", "birth_year": 1985, "careers": [], "educations": [],
             "certifications": [], "language_skills": [], "field_confidences": {}},
        ]

        result = extract_candidate_data(SAMPLE_RESUME_TEXT, max_retries=2)
        assert result["name"] == "강솔찬"
        assert mock_llm.call_count == 2

    @patch("candidates.services.llm_extraction.call_llm_json")
    def test_all_retries_fail(self, mock_llm):
        mock_llm.side_effect = Exception("LLM error")

        result = extract_candidate_data(SAMPLE_RESUME_TEXT, max_retries=3)
        assert result is None
```

- [ ] **5.2: 테스트 실행 — 실패 확인**

```bash
uv run pytest tests/test_llm_extraction.py -v
```

- [ ] **5.3: LLM 추출 서비스 구현**

`candidates/services/llm_extraction.py`:

```python
"""LLM 기반 이력서 구조화 추출.

common/llm.py의 call_llm_json()으로 이력서 텍스트 → 구조화 JSON.
"""

import logging

from common.llm import call_llm_json

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """당신은 한국어 이력서 파싱 전문가입니다.
주어진 이력서 텍스트에서 구조화된 정보를 추출하여 JSON으로 반환하세요.

규칙:
- 이력서에 명시되지 않은 정보는 빈 문자열 또는 null로 반환
- 생년은 4자리 연도로 변환 (85 → 1985)
- 경력은 최신순으로 정렬 (order: 0이 가장 최신)
- is_current: 현재 재직 중이면 true, end_date가 없으면 true
- 각 필드별 confidence score를 0.0-1.0으로 반환
- 확실하지 않은 정보는 낮은 confidence로 표시"""

EXTRACTION_JSON_SCHEMA = """{
  "name": "string (한글 이름)",
  "name_en": "string (영문 이름, 없으면 빈 문자열)",
  "birth_year": "number (4자리, 없으면 null)",
  "gender": "string (M/F, 없으면 빈 문자열)",
  "email": "string",
  "phone": "string",
  "address": "string",
  "current_company": "string (현재 회사)",
  "current_position": "string (현재 직위)",
  "total_experience_years": "number (총 경력 연수, 없으면 null)",
  "core_competencies": ["string (핵심역량)"],
  "summary": "string (2-3문장 요약)",
  "educations": [
    {
      "institution": "string (학교명)",
      "degree": "string (bachelor/master/phd/etc)",
      "major": "string (전공)",
      "gpa": "string (학점, 없으면 빈 문자열)",
      "start_year": "number (nullable)",
      "end_year": "number (nullable)",
      "is_abroad": "boolean"
    }
  ],
  "careers": [
    {
      "company": "string (회사명)",
      "company_en": "string (영문 회사명, 없으면 빈 문자열)",
      "position": "string (직급/직책)",
      "department": "string (부서, 없으면 빈 문자열)",
      "start_date": "string (입사일, 다양한 형식 그대로)",
      "end_date": "string (퇴사일, 재직중이면 빈 문자열)",
      "is_current": "boolean",
      "duties": "string (주요 업무, 여러 줄이면 합쳐서)",
      "achievements": "string (성과, 없으면 빈 문자열)",
      "order": "number (0이 최신)"
    }
  ],
  "certifications": [
    {
      "name": "string (자격증명)",
      "issuer": "string (발급기관, 없으면 빈 문자열)",
      "acquired_date": "string (취득일, 없으면 빈 문자열)"
    }
  ],
  "language_skills": [
    {
      "language": "string (영어, 일본어 등)",
      "test_name": "string (TOEIC 등, 없으면 빈 문자열)",
      "score": "string (점수/등급)",
      "level": "string (native/fluent/business/basic, 없으면 빈 문자열)"
    }
  ],
  "field_confidences": {
    "name": "number (0.0-1.0)",
    "birth_year": "number",
    "careers": "number",
    "educations": "number",
    "certifications": "number",
    "overall": "number"
  }
}"""


def build_extraction_prompt(resume_text: str) -> str:
    """이력서 텍스트로 추출 프롬프트 생성."""
    return f"""다음 이력서 텍스트에서 정보를 추출하여 JSON으로 반환하세요.

출력 JSON 스키마:
{EXTRACTION_JSON_SCHEMA}

이력서 텍스트:
---
{resume_text}
---

위 스키마에 맞는 JSON만 반환하세요. 설명이나 마크다운 없이 순수 JSON만."""


def extract_candidate_data(
    resume_text: str, max_retries: int = 3
) -> dict | None:
    """LLM으로 이력서 텍스트에서 구조화 데이터 추출.

    Args:
        resume_text: 이력서 전문 텍스트
        max_retries: 최대 재시도 횟수

    Returns:
        추출된 데이터 dict 또는 실패 시 None
    """
    prompt = build_extraction_prompt(resume_text)

    for attempt in range(max_retries):
        try:
            result = call_llm_json(
                prompt,
                system=EXTRACTION_SYSTEM_PROMPT,
                timeout=60,
                max_tokens=4000,
            )
            # 최소 필수 필드 확인
            if isinstance(result, dict) and "name" in result:
                return result
            logger.warning("LLM returned invalid structure (attempt %d)", attempt + 1)
        except Exception:
            logger.warning(
                "LLM extraction failed (attempt %d/%d)",
                attempt + 1,
                max_retries,
                exc_info=True,
            )

    logger.error("All %d extraction attempts failed", max_retries)
    return None
```

- [ ] **5.4: 테스트 실행 — 통과 확인**

```bash
uv run pytest tests/test_llm_extraction.py -v
```

- [ ] **5.5: Commit**

```bash
git add candidates/services/llm_extraction.py tests/test_llm_extraction.py
git commit -m "feat: LLM-based resume structured extraction

Prompt engineering for Korean resume parsing.
JSON schema with field-level confidence scores.
Retry logic (3 attempts) on parse failures."
```

---

## Task 6: 3단계 검증 시스템

**Files:**
- Create: `candidates/services/validation.py`
- Test: `tests/test_validation.py`

- [ ] **6.1: 검증 시스템 테스트 작성**

`tests/test_validation.py`:

```python
import pytest
from candidates.services.validation import (
    validate_extraction,
    validate_rules,
    validate_cross_check,
    compute_overall_confidence,
)


class TestRuleValidation:
    """Layer 2: 규칙 기반 검증."""

    def test_valid_birth_year(self):
        data = {"birth_year": 1985}
        issues = validate_rules(data)
        assert not any(i["field"] == "birth_year" for i in issues)

    def test_invalid_birth_year_too_old(self):
        data = {"birth_year": 1930}
        issues = validate_rules(data)
        assert any(i["field"] == "birth_year" for i in issues)

    def test_invalid_birth_year_future(self):
        data = {"birth_year": 2030}
        issues = validate_rules(data)
        assert any(i["field"] == "birth_year" for i in issues)

    def test_missing_name(self):
        data = {"name": "", "birth_year": 1985}
        issues = validate_rules(data)
        assert any(i["field"] == "name" for i in issues)

    def test_career_date_order(self):
        data = {
            "careers": [
                {"start_date": "2020.01", "end_date": "2015.01", "order": 0},
            ]
        }
        issues = validate_rules(data)
        assert any(i["field"] == "careers" for i in issues)

    def test_valid_careers(self):
        data = {
            "careers": [
                {"start_date": "2015.01", "end_date": "2020.01", "order": 0},
            ]
        }
        issues = validate_rules(data)
        assert not any(i["field"] == "careers" for i in issues)


class TestCrossCheck:
    """Layer 3: 파일명 vs LLM 추출 교차 검증."""

    def test_name_matches(self):
        parsed = {"name": "강솔찬", "birth_year": 1985}
        extracted = {"name": "강솔찬", "birth_year": 1985}
        issues = validate_cross_check(parsed, extracted)
        assert len(issues) == 0

    def test_name_mismatch(self):
        parsed = {"name": "강솔찬", "birth_year": 1985}
        extracted = {"name": "김영희", "birth_year": 1985}
        issues = validate_cross_check(parsed, extracted)
        assert any(i["field"] == "name" for i in issues)

    def test_birth_year_mismatch(self):
        parsed = {"name": "강솔찬", "birth_year": 1985}
        extracted = {"name": "강솔찬", "birth_year": 1990}
        issues = validate_cross_check(parsed, extracted)
        assert any(i["field"] == "birth_year" for i in issues)

    def test_skip_when_filename_unparsed(self):
        parsed = {"name": None, "birth_year": None}
        extracted = {"name": "강솔찬", "birth_year": 1985}
        issues = validate_cross_check(parsed, extracted)
        assert len(issues) == 0


class TestOverallConfidence:
    def test_high_confidence(self):
        field_confidences = {"name": 1.0, "birth_year": 0.95, "careers": 0.9, "overall": 0.92}
        issues = []
        score, status = compute_overall_confidence(field_confidences, issues)
        assert score >= 0.85
        assert status == "auto_confirmed"

    def test_medium_confidence(self):
        field_confidences = {"name": 0.8, "birth_year": 0.7, "careers": 0.6, "overall": 0.7}
        issues = []
        score, status = compute_overall_confidence(field_confidences, issues)
        assert 0.6 <= score < 0.85
        assert status == "needs_review"

    def test_low_confidence(self):
        field_confidences = {"name": 0.3, "overall": 0.4}
        issues = []
        score, status = compute_overall_confidence(field_confidences, issues)
        assert score < 0.6
        assert status == "failed"

    def test_issues_lower_confidence(self):
        field_confidences = {"name": 1.0, "birth_year": 0.95, "overall": 0.95}
        issues = [{"field": "name", "severity": "error", "message": "이름 불일치"}]
        score, status = compute_overall_confidence(field_confidences, issues)
        assert score < 0.95  # 이슈로 인해 낮아짐


class TestValidateExtraction:
    """통합 검증 (3단계 모두)."""

    def test_full_validation(self):
        extracted = {
            "name": "강솔찬",
            "birth_year": 1985,
            "careers": [
                {"start_date": "2015.01", "end_date": "2020.01", "order": 0},
            ],
            "field_confidences": {
                "name": 1.0, "birth_year": 0.95, "careers": 0.9, "overall": 0.92,
            },
        }
        filename_parsed = {"name": "강솔찬", "birth_year": 1985}

        result = validate_extraction(extracted, filename_parsed)
        assert "confidence_score" in result
        assert "validation_status" in result
        assert "issues" in result
```

- [ ] **6.2: 테스트 실행 — 실패 확인**

```bash
uv run pytest tests/test_validation.py -v
```

- [ ] **6.3: 검증 시스템 구현**

`candidates/services/validation.py`:

```python
"""3단계 검증 시스템.

Layer 1: LLM 자체 confidence (field_confidences)
Layer 2: 규칙 기반 검증 (birth_year 범위, career 날짜 순서 등)
Layer 3: 파일명 vs LLM 추출 교차 검증
"""

import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

CURRENT_YEAR = datetime.now().year


def validate_rules(data: dict) -> list[dict]:
    """Layer 2: 규칙 기반 검증.

    Returns:
        [{"field": str, "severity": "error"|"warning", "message": str}]
    """
    issues = []

    # 필수 필드: 이름
    name = data.get("name", "")
    if not name or not name.strip():
        issues.append({
            "field": "name",
            "severity": "error",
            "message": "이름이 비어있습니다",
        })

    # 생년 범위 (1940-2005)
    birth_year = data.get("birth_year")
    if birth_year is not None:
        if birth_year < 1940 or birth_year > 2005:
            issues.append({
                "field": "birth_year",
                "severity": "error",
                "message": f"생년 {birth_year}이(가) 유효 범위(1940-2005) 밖입니다",
            })

    # 경력 날짜 순서
    careers = data.get("careers", [])
    for i, career in enumerate(careers):
        start = career.get("start_date", "")
        end = career.get("end_date", "")
        if start and end:
            start_num = _date_to_number(start)
            end_num = _date_to_number(end)
            if start_num and end_num and start_num > end_num:
                issues.append({
                    "field": "careers",
                    "severity": "warning",
                    "message": f"경력 {i}: 시작일({start})이 종료일({end})보다 늦습니다",
                })

    return issues


def validate_cross_check(
    filename_parsed: dict, extracted: dict
) -> list[dict]:
    """Layer 3: 파일명 vs LLM 추출 교차 검증.

    Args:
        filename_parsed: parse_filename() 결과 {"name": str|None, "birth_year": int|None}
        extracted: LLM 추출 결과

    Returns:
        [{"field": str, "severity": str, "message": str}]
    """
    issues = []
    fn_name = filename_parsed.get("name")
    fn_year = filename_parsed.get("birth_year")

    if not fn_name:
        return issues  # 파일명 파싱 실패 → 교차 검증 불가

    ex_name = extracted.get("name", "")
    if fn_name and ex_name and fn_name != ex_name:
        issues.append({
            "field": "name",
            "severity": "warning",
            "message": f"파일명 이름({fn_name})과 추출 이름({ex_name})이 다릅니다",
        })

    ex_year = extracted.get("birth_year")
    if fn_year and ex_year and fn_year != ex_year:
        issues.append({
            "field": "birth_year",
            "severity": "warning",
            "message": f"파일명 생년({fn_year})과 추출 생년({ex_year})이 다릅니다",
        })

    return issues


def compute_overall_confidence(
    field_confidences: dict, issues: list[dict]
) -> tuple[float, str]:
    """종합 신뢰도 + 검증 상태 결정.

    Returns:
        (confidence_score, validation_status)
        status: "auto_confirmed" (>=0.85) / "needs_review" (0.6-0.85) / "failed" (<0.6)
    """
    # LLM 제공 overall 우선, 없으면 평균
    base_score = field_confidences.get("overall")
    if base_score is None:
        values = [v for v in field_confidences.values() if isinstance(v, (int, float))]
        base_score = sum(values) / len(values) if values else 0.5

    # 이슈에 따른 감점
    penalty = 0.0
    for issue in issues:
        if issue["severity"] == "error":
            penalty += 0.15
        elif issue["severity"] == "warning":
            penalty += 0.05

    score = max(0.0, base_score - penalty)

    if score >= 0.85:
        status = "auto_confirmed"
    elif score >= 0.6:
        status = "needs_review"
    else:
        status = "failed"

    return round(score, 3), status


def validate_extraction(
    extracted: dict, filename_parsed: dict
) -> dict:
    """3단계 통합 검증.

    Returns:
        {
            "confidence_score": float,
            "validation_status": str,
            "field_confidences": dict,
            "issues": list[dict],
        }
    """
    field_confidences = extracted.get("field_confidences", {})

    # Layer 2: 규칙 기반
    rule_issues = validate_rules(extracted)

    # Layer 3: 교차 검증
    cross_issues = validate_cross_check(filename_parsed, extracted)

    all_issues = rule_issues + cross_issues
    score, status = compute_overall_confidence(field_confidences, all_issues)

    return {
        "confidence_score": score,
        "validation_status": status,
        "field_confidences": field_confidences,
        "issues": all_issues,
    }


def _date_to_number(date_str: str) -> float | None:
    """날짜 문자열을 비교 가능한 숫자로 변환. '2020.03' → 2020.03"""
    match = re.search(r"(\d{4})[.\-/]?(\d{1,2})?", date_str)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else 0
    return year + month / 100
```

- [ ] **6.4: 테스트 실행 — 통과 확인**

```bash
uv run pytest tests/test_validation.py -v
```

- [ ] **6.5: Commit**

```bash
git add candidates/services/validation.py tests/test_validation.py
git commit -m "feat: 3-layer validation system for resume extraction

Layer 1: LLM field-level confidence scores
Layer 2: Rule-based validation (birth year, career dates)
Layer 3: Filename vs extraction cross-check
Auto-classification: auto_confirmed/needs_review/failed"
```

---

## Task 7: Management Command (import_resumes)

**Files:**
- Create: `candidates/management/__init__.py`, `candidates/management/commands/__init__.py`
- Create: `candidates/management/commands/import_resumes.py`
- Test: `tests/test_import_pipeline.py`

- [ ] **7.1: management 디렉토리 구조 생성**

```bash
mkdir -p candidates/management/commands
touch candidates/management/__init__.py
touch candidates/management/commands/__init__.py
```

- [ ] **7.2: import_resumes 커맨드 구현**

`candidates/management/commands/import_resumes.py`:

```python
"""이력서 임포트 파이프라인.

Usage:
    python manage.py import_resumes --folder=Accounting --limit=100
    python manage.py import_resumes --folder=Accounting --dry-run
    python manage.py import_resumes --all --limit=10
"""

import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand
from django.db import transaction

from candidates.models import (
    Candidate,
    Career,
    Category,
    Certification,
    Education,
    ExtractionLog,
    LanguageSkill,
    Resume,
)
from candidates.services.drive_sync import (
    CATEGORY_FOLDERS,
    download_file,
    find_category_folder,
    get_drive_service,
    list_files_in_folder,
    list_root_folders,
)
from candidates.services.filename_parser import group_by_person, parse_filename
from candidates.services.llm_extraction import extract_candidate_data
from candidates.services.text_extraction import extract_text
from candidates.services.validation import validate_extraction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Google Drive 이력서를 임포트하여 Candidate DB로 변환"

    def add_arguments(self, parser):
        parser.add_argument(
            "--folder",
            type=str,
            help="특정 카테고리 폴더만 처리 (예: Accounting)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="모든 카테고리 폴더 처리",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="폴더당 최대 처리 파일 수 (0=무제한)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="실제 처리 없이 파일 목록만 확인",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=5,
            help="LLM 병렬 호출 수 (default: 5)",
        )
        parser.add_argument(
            "--parent-folder-id",
            type=str,
            default="",
            help="카테고리 폴더들의 부모 폴더 ID (기본: Drive 루트)",
        )

    def handle(self, *args, **options):
        folder = options["folder"]
        process_all = options["all"]
        limit = options["limit"]
        dry_run = options["dry_run"]
        workers = options["workers"]
        parent_id = options["parent_folder_id"]

        if not folder and not process_all:
            self.stderr.write("--folder 또는 --all 중 하나를 지정하세요.")
            return

        folders = [folder] if folder else CATEGORY_FOLDERS

        service = get_drive_service()

        # 부모 폴더 찾기
        if not parent_id:
            root_folders = list_root_folders(service)
            self.stdout.write(f"Drive 루트 폴더: {[f['name'] for f in root_folders]}")

        stats = {
            "total_files": 0,
            "groups": 0,
            "downloaded": 0,
            "extracted": 0,
            "parsed": 0,
            "auto_confirmed": 0,
            "needs_review": 0,
            "failed": 0,
            "skipped": 0,
        }

        for folder_name in folders:
            self._process_folder(
                service, folder_name, parent_id, limit, dry_run, workers, stats
            )

        self._print_summary(stats, dry_run)

    def _process_folder(
        self, service, folder_name, parent_id, limit, dry_run, workers, stats
    ):
        """단일 카테고리 폴더 처리."""
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Processing folder: {folder_name}")

        # 카테고리 DB 조회/생성
        category, _ = Category.objects.get_or_create(
            name=folder_name,
            defaults={"name_ko": folder_name},
        )

        # Drive에서 폴더 찾기
        search_parent = parent_id or "root"
        folder_id = find_category_folder(service, search_parent, folder_name)
        if not folder_id:
            self.stderr.write(f"  폴더를 찾을 수 없습니다: {folder_name}")
            return

        # 파일 목록
        files = list_files_in_folder(service, folder_id)
        self.stdout.write(f"  파일 수: {len(files)}")
        stats["total_files"] += len(files)

        if dry_run:
            for f in files[:10]:
                self.stdout.write(f"    {f['name']}")
            if len(files) > 10:
                self.stdout.write(f"    ... and {len(files) - 10} more")
            return

        # 이미 처리된 파일 제외
        existing_ids = set(
            Resume.objects.filter(
                drive_file_id__in=[f["id"] for f in files]
            ).values_list("drive_file_id", flat=True)
        )
        new_files = [f for f in files if f["id"] not in existing_ids]
        stats["skipped"] += len(files) - len(new_files)

        if not new_files:
            self.stdout.write("  모든 파일이 이미 처리됨. 스킵.")
            return

        self.stdout.write(f"  새 파일: {len(new_files)}, 스킵: {len(existing_ids)}")

        # 파일명 그룹핑
        file_dicts = [
            {"file_name": f["name"], "modified_time": f.get("modifiedTime", ""),
             "id": f["id"], "mimeType": f.get("mimeType", ""), "size": f.get("size")}
            for f in new_files
        ]
        groups = group_by_person(file_dicts)
        stats["groups"] += len(groups)

        if limit:
            groups = groups[:limit]

        self.stdout.write(f"  그룹 수: {len(groups)} (limit={limit})")

        # 그룹별 처리 (LLM 병렬)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for group in groups:
                future = executor.submit(
                    self._process_group, service, group, category, stats
                )
                futures[future] = group

            for future in as_completed(futures):
                group = futures[future]
                try:
                    future.result()
                except Exception:
                    logger.exception(
                        "Failed to process group: %s",
                        group["primary"]["file_name"],
                    )
                    stats["failed"] += 1

        # 카테고리 카운트 업데이트
        category.candidate_count = category.candidates.count()
        category.save(update_fields=["candidate_count"])

    def _process_group(self, service, group, category, stats):
        """그룹(동일 인물 파일들) 처리: 다운로드 → 텍스트 추출 → LLM → 검증 → DB 저장."""
        primary_file = group["primary"]
        file_name = primary_file["file_name"]
        self.stdout.write(f"    Processing: {file_name}")

        # 1. 다운로드
        with tempfile.NamedTemporaryFile(
            suffix=f".{file_name.rsplit('.', 1)[-1]}", delete=True
        ) as tmp:
            download_file(service, primary_file["id"], tmp.name)
            stats["downloaded"] += 1

            # 2. 텍스트 추출
            try:
                raw_text = extract_text(tmp.name)
            except Exception as e:
                logger.error("Text extraction failed for %s: %s", file_name, e)
                self._create_failed_resume(primary_file, category, str(e))
                stats["failed"] += 1
                return

        if not raw_text.strip():
            logger.warning("Empty text extracted from %s", file_name)
            self._create_failed_resume(primary_file, category, "빈 텍스트")
            stats["failed"] += 1
            return

        stats["extracted"] += 1

        # 3. LLM 구조화 추출
        extracted = extract_candidate_data(raw_text)
        if not extracted:
            self._create_failed_resume(primary_file, category, "LLM 추출 실패")
            stats["failed"] += 1
            return

        # 4. 검증
        filename_parsed = group["parsed"]
        validation = validate_extraction(extracted, filename_parsed)

        # 5. DB 저장
        with transaction.atomic():
            candidate = self._save_candidate(
                extracted, raw_text, category, validation, primary_file
            )

            # Primary resume
            resume = Resume.objects.create(
                candidate=candidate,
                file_name=file_name,
                drive_file_id=primary_file["id"],
                drive_folder=category.name,
                mime_type=primary_file.get("mimeType", ""),
                file_size=int(primary_file.get("size") or 0),
                raw_text=raw_text,
                is_primary=True,
                processing_status=Resume.ProcessingStatus.PARSED,
            )

            # Other resumes (버전 관리, 텍스트 추출 안 함)
            for i, other in enumerate(group.get("others", []), start=2):
                Resume.objects.create(
                    candidate=candidate,
                    file_name=other["file_name"],
                    drive_file_id=other["id"],
                    drive_folder=category.name,
                    mime_type=other.get("mimeType", ""),
                    file_size=int(other.get("size") or 0),
                    is_primary=False,
                    version=i,
                    processing_status=Resume.ProcessingStatus.PENDING,
                )

            # Extraction log
            ExtractionLog.objects.create(
                candidate=candidate,
                resume=resume,
                action=ExtractionLog.Action.AUTO_EXTRACT,
                confidence=validation["confidence_score"],
                note=f"issues: {len(validation['issues'])}",
            )

        stats["parsed"] += 1
        stats[validation["validation_status"]] += 1
        self.stdout.write(
            f"      → {candidate.name} "
            f"(confidence: {validation['confidence_score']:.2f}, "
            f"status: {validation['validation_status']})"
        )

    def _save_candidate(self, extracted, raw_text, category, validation, file_info):
        """추출 데이터로 Candidate + 하위 모델 생성."""
        candidate = Candidate.objects.create(
            name=extracted.get("name", ""),
            name_en=extracted.get("name_en", ""),
            birth_year=extracted.get("birth_year"),
            gender=extracted.get("gender", ""),
            email=extracted.get("email", ""),
            phone=extracted.get("phone", ""),
            address=extracted.get("address", ""),
            primary_category=category,
            total_experience_years=extracted.get("total_experience_years"),
            current_company=extracted.get("current_company", ""),
            current_position=extracted.get("current_position", ""),
            current_salary=extracted.get("current_salary"),
            desired_salary=extracted.get("desired_salary"),
            core_competencies=extracted.get("core_competencies", []),
            summary=extracted.get("summary", ""),
            source=Candidate.Source.DRIVE_IMPORT,
            raw_text=raw_text,
            validation_status=validation["validation_status"],
            raw_extracted_json=extracted,
            confidence_score=validation["confidence_score"],
            field_confidences=validation.get("field_confidences"),
        )
        candidate.categories.add(category)

        # Education
        for edu in extracted.get("educations", []):
            Education.objects.create(
                candidate=candidate,
                institution=edu.get("institution", ""),
                degree=edu.get("degree", ""),
                major=edu.get("major", ""),
                gpa=edu.get("gpa", ""),
                start_year=edu.get("start_year"),
                end_year=edu.get("end_year"),
                is_abroad=edu.get("is_abroad", False),
            )

        # Career
        for career in extracted.get("careers", []):
            Career.objects.create(
                candidate=candidate,
                company=career.get("company", ""),
                company_en=career.get("company_en", ""),
                position=career.get("position", ""),
                department=career.get("department", ""),
                start_date=career.get("start_date", ""),
                end_date=career.get("end_date", ""),
                is_current=career.get("is_current", False),
                duties=career.get("duties", ""),
                achievements=career.get("achievements", ""),
                salary=career.get("salary"),
                order=career.get("order", 0),
            )

        # Certification
        for cert in extracted.get("certifications", []):
            Certification.objects.create(
                candidate=candidate,
                name=cert.get("name", ""),
                issuer=cert.get("issuer", ""),
                acquired_date=cert.get("acquired_date", ""),
            )

        # LanguageSkill
        for lang in extracted.get("language_skills", []):
            LanguageSkill.objects.create(
                candidate=candidate,
                language=lang.get("language", ""),
                test_name=lang.get("test_name", ""),
                score=lang.get("score", ""),
                level=lang.get("level", ""),
            )

        return candidate

    def _create_failed_resume(self, file_info, category, error_msg):
        """처리 실패 시 Resume 레코드만 생성 (재시도용)."""
        Resume.objects.create(
            file_name=file_info["file_name"],
            drive_file_id=file_info["id"],
            drive_folder=category.name,
            mime_type=file_info.get("mimeType", ""),
            processing_status=Resume.ProcessingStatus.FAILED,
            error_message=error_msg,
        )

    def _print_summary(self, stats, dry_run):
        """처리 결과 요약 출력."""
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write("IMPORT SUMMARY" + (" (DRY RUN)" if dry_run else ""))
        self.stdout.write(f"{'='*60}")
        self.stdout.write(f"  전체 파일:      {stats['total_files']}")
        self.stdout.write(f"  그룹 수:        {stats['groups']}")
        self.stdout.write(f"  다운로드:       {stats['downloaded']}")
        self.stdout.write(f"  텍스트 추출:    {stats['extracted']}")
        self.stdout.write(f"  파싱 완료:      {stats['parsed']}")
        self.stdout.write(f"  자동 확인:      {stats['auto_confirmed']}")
        self.stdout.write(f"  검토 필요:      {stats['needs_review']}")
        self.stdout.write(f"  실패:           {stats['failed']}")
        self.stdout.write(f"  스킵(기존):     {stats['skipped']}")
```

- [ ] **7.3: 파이프라인 테스트 작성**

`tests/test_import_pipeline.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from candidates.models import Candidate, Category, Resume


@pytest.fixture
def accounting_category(db):
    return Category.objects.create(name="Accounting", name_ko="회계")


class TestPipelineIdempotency:
    """이미 처리된 drive_file_id는 스킵."""

    def test_skip_existing_resume(self, db, accounting_category):
        Resume.objects.create(
            file_name="강솔찬.85.현대.doc",
            drive_file_id="existing_id",
            drive_folder="Accounting",
            processing_status=Resume.ProcessingStatus.PARSED,
        )
        assert Resume.objects.filter(drive_file_id="existing_id").exists()

    def test_failed_resume_not_reprocessed_by_default(self, db, accounting_category):
        """실패한 Resume은 drive_file_id로 이미 존재하므로 재처리 안 됨."""
        Resume.objects.create(
            file_name="test.doc",
            drive_file_id="failed_id",
            drive_folder="Accounting",
            processing_status=Resume.ProcessingStatus.FAILED,
        )
        existing = set(
            Resume.objects.filter(
                drive_file_id__in=["failed_id"]
            ).values_list("drive_file_id", flat=True)
        )
        assert "failed_id" in existing


class TestCandidateCreation:
    """추출 데이터로 Candidate + 하위 모델 생성."""

    def test_create_candidate_from_extracted(self, db, accounting_category):
        candidate = Candidate.objects.create(
            name="강솔찬",
            birth_year=1985,
            current_company="현대엠시트",
            primary_category=accounting_category,
            validation_status=Candidate.ValidationStatus.AUTO_CONFIRMED,
            confidence_score=0.92,
            raw_extracted_json={"name": "강솔찬"},
        )
        candidate.categories.add(accounting_category)

        assert candidate.name == "강솔찬"
        assert candidate.validation_status == "auto_confirmed"
        assert accounting_category in candidate.categories.all()
```

- [ ] **7.4: 테스트 실행**

```bash
uv run pytest tests/test_import_pipeline.py -v
```

- [ ] **7.5: Commit**

```bash
git add candidates/management/ tests/test_import_pipeline.py
git commit -m "feat: import_resumes management command

Pipeline: Drive sync → download → text extraction → LLM →
validation → DB save. ThreadPoolExecutor for parallel LLM calls.
Idempotent: skips already-processed drive_file_ids.
Supports --folder, --all, --limit, --dry-run, --workers."
```

---

## Task 8: 리뷰 UI

**Files:**
- Create: `candidates/urls.py`
- Create: `candidates/views.py`
- Create: `candidates/templates/candidates/review_list.html`
- Create: `candidates/templates/candidates/review_detail.html`
- Create: `candidates/templates/candidates/partials/review_list_content.html`
- Create: `candidates/templates/candidates/partials/review_detail_content.html`
- Modify: `main/urls.py` — candidates URL include

- [ ] **8.1: URL 라우팅**

`candidates/urls.py`:

```python
from django.urls import path

from . import views

app_name = "candidates"

urlpatterns = [
    path("review/", views.review_list, name="review_list"),
    path("review/<uuid:pk>/", views.review_detail, name="review_detail"),
    path("review/<uuid:pk>/confirm/", views.review_confirm, name="review_confirm"),
    path("review/<uuid:pk>/reject/", views.review_reject, name="review_reject"),
]
```

- [ ] **8.2: main/urls.py 수정**

`main/urls.py`에 추가:

```python
urlpatterns = [
    # ...existing...
    path("candidates/", include("candidates.urls")),
]
```

- [ ] **8.3: views.py 작성**

`candidates/views.py`:

```python
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from .models import Candidate, ExtractionLog

PAGE_SIZE = 20


@login_required
def review_list(request):
    """needs_review 후보자 리스트."""
    status_filter = request.GET.get("status", "needs_review")
    candidates = Candidate.objects.filter(validation_status=status_filter).select_related(
        "primary_category"
    )

    page = int(request.GET.get("page", 1))
    offset = (page - 1) * PAGE_SIZE
    page_candidates = candidates[offset : offset + PAGE_SIZE]
    has_more = candidates[offset + PAGE_SIZE : offset + PAGE_SIZE + 1].exists()
    total = candidates.count()

    template = (
        "candidates/partials/review_list_content.html"
        if request.htmx
        else "candidates/review_list.html"
    )
    return render(
        request,
        template,
        {
            "candidates": page_candidates,
            "page": page,
            "has_more": has_more,
            "total": total,
            "status_filter": status_filter,
        },
    )


@login_required
def review_detail(request, pk):
    """원본 텍스트 + 추출 결과 나란히 표시."""
    candidate = get_object_or_404(Candidate, pk=pk)
    primary_resume = candidate.resumes.filter(is_primary=True).first()
    careers = candidate.careers.all()
    educations = candidate.educations.all()
    certifications = candidate.certifications.all()
    language_skills = candidate.language_skills.all()
    logs = candidate.extraction_logs.all()[:10]

    template = (
        "candidates/partials/review_detail_content.html"
        if request.htmx
        else "candidates/review_detail.html"
    )
    return render(
        request,
        template,
        {
            "candidate": candidate,
            "primary_resume": primary_resume,
            "careers": careers,
            "educations": educations,
            "certifications": certifications,
            "language_skills": language_skills,
            "logs": logs,
        },
    )


@login_required
def review_confirm(request, pk):
    """검토 확인: needs_review → confirmed."""
    candidate = get_object_or_404(Candidate, pk=pk)
    if request.method == "POST":
        candidate.validation_status = Candidate.ValidationStatus.CONFIRMED
        candidate.save(update_fields=["validation_status", "updated_at"])

        ExtractionLog.objects.create(
            candidate=candidate,
            action=ExtractionLog.Action.HUMAN_CONFIRM,
        )

        if request.htmx:
            return HttpResponse(
                status=204,
                headers={"HX-Redirect": "/candidates/review/"},
            )
    return HttpResponse(status=405)


@login_required
def review_reject(request, pk):
    """검토 거부: needs_review → failed."""
    candidate = get_object_or_404(Candidate, pk=pk)
    if request.method == "POST":
        candidate.validation_status = Candidate.ValidationStatus.FAILED
        candidate.save(update_fields=["validation_status", "updated_at"])

        ExtractionLog.objects.create(
            candidate=candidate,
            action=ExtractionLog.Action.HUMAN_REJECT,
            note=request.POST.get("reason", ""),
        )

        if request.htmx:
            return HttpResponse(
                status=204,
                headers={"HX-Redirect": "/candidates/review/"},
            )
    return HttpResponse(status=405)
```

- [ ] **8.4: 템플릿 디렉토리 생성**

```bash
mkdir -p candidates/templates/candidates/partials
```

- [ ] **8.5: review_list.html (전체 페이지)**

`candidates/templates/candidates/review_list.html`:

```html
{% extends "common/base.html" %}

{% block content %}
{% include "candidates/partials/review_list_content.html" %}
{% endblock %}
```

- [ ] **8.6: review_list_content.html (HTMX partial)**

`candidates/templates/candidates/partials/review_list_content.html`:

```html
<div id="review-list" class="px-4 py-6 max-w-4xl mx-auto">
  <div class="flex items-center justify-between mb-6">
    <h1 class="text-xl font-semibold text-gray-900">추출 결과 검토</h1>
    <span class="text-sm text-gray-500">{{ total }}건</span>
  </div>

  <!-- 상태 필터 탭 -->
  <div class="flex gap-2 mb-4 overflow-x-auto">
    {% for value, label in status_choices %}
    <a
      hx-get="/candidates/review/?status={{ value }}"
      hx-target="#review-list"
      hx-push-url="true"
      class="px-3 py-1.5 rounded-full text-sm whitespace-nowrap cursor-pointer
        {% if status_filter == value %}
          bg-indigo-600 text-white
        {% else %}
          bg-gray-100 text-gray-600 hover:bg-gray-200
        {% endif %}"
    >{{ label }}</a>
    {% endfor %}
  </div>

  <!-- 후보자 리스트 -->
  <div class="space-y-3">
    {% for c in candidates %}
    <a
      hx-get="/candidates/review/{{ c.pk }}/"
      hx-target="main"
      hx-push-url="true"
      class="block bg-white rounded-xl border border-gray-200 p-4 hover:border-indigo-300 transition-colors"
    >
      <div class="flex items-center justify-between">
        <div>
          <span class="font-semibold text-gray-900">{{ c.name }}</span>
          {% if c.birth_year %}
          <span class="text-xs text-gray-400 ml-1">{{ c.birth_year }}년생</span>
          {% endif %}
        </div>
        <div class="flex items-center gap-2">
          {% if c.confidence_score %}
          <span class="text-xs px-2 py-0.5 rounded-full
            {% if c.confidence_score >= 0.85 %}bg-green-100 text-green-700
            {% elif c.confidence_score >= 0.6 %}bg-yellow-100 text-yellow-700
            {% else %}bg-red-100 text-red-700{% endif %}">
            {{ c.confidence_score|floatformat:0 }}%
          </span>
          {% endif %}
        </div>
      </div>
      <div class="mt-1 text-sm text-gray-500">
        {% if c.current_company %}{{ c.current_company }}{% endif %}
        {% if c.current_position %} · {{ c.current_position }}{% endif %}
        {% if c.total_experience_years %} · {{ c.total_experience_years }}년차{% endif %}
      </div>
      {% if c.primary_category %}
      <span class="inline-block mt-2 text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">
        {{ c.primary_category.name }}
      </span>
      {% endif %}
    </a>
    {% empty %}
    <div class="text-center py-12 text-gray-400">
      검토할 후보자가 없습니다.
    </div>
    {% endfor %}
  </div>

  <!-- 더보기 -->
  {% if has_more %}
  <div class="mt-4 text-center">
    <button
      hx-get="/candidates/review/?status={{ status_filter }}&page={{ page|add:1 }}"
      hx-target="#review-list"
      hx-swap="innerHTML"
      class="text-sm text-indigo-600 hover:text-indigo-800"
    >
      더보기
    </button>
  </div>
  {% endif %}
</div>
```

- [ ] **8.7: review_detail.html (전체 페이지)**

`candidates/templates/candidates/review_detail.html`:

```html
{% extends "common/base.html" %}

{% block content %}
{% include "candidates/partials/review_detail_content.html" %}
{% endblock %}
```

- [ ] **8.8: review_detail_content.html (HTMX partial)**

`candidates/templates/candidates/partials/review_detail_content.html`:

```html
<div class="px-4 py-6 max-w-4xl mx-auto">
  <!-- 헤더 -->
  <div class="flex items-center gap-3 mb-6">
    <a hx-get="/candidates/review/" hx-target="main" hx-push-url="true"
       class="text-gray-400 hover:text-gray-600">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
      </svg>
    </a>
    <h1 class="text-xl font-semibold text-gray-900">{{ candidate.name }}</h1>
    {% if candidate.confidence_score %}
    <span class="text-xs px-2 py-0.5 rounded-full
      {% if candidate.confidence_score >= 0.85 %}bg-green-100 text-green-700
      {% elif candidate.confidence_score >= 0.6 %}bg-yellow-100 text-yellow-700
      {% else %}bg-red-100 text-red-700{% endif %}">
      신뢰도 {{ candidate.confidence_score|floatformat:0 }}%
    </span>
    {% endif %}
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <!-- 좌측: 추출 결과 -->
    <div class="space-y-4">
      <h2 class="text-sm font-medium text-gray-500 uppercase tracking-wide">추출 결과</h2>

      <!-- 기본 정보 -->
      <div class="bg-white rounded-xl border border-gray-200 p-4">
        <h3 class="text-sm font-semibold text-gray-700 mb-3">기본 정보</h3>
        <dl class="space-y-2 text-sm">
          <div class="flex justify-between">
            <dt class="text-gray-500">이름</dt>
            <dd class="text-gray-900">{{ candidate.name }}</dd>
          </div>
          {% if candidate.birth_year %}
          <div class="flex justify-between">
            <dt class="text-gray-500">생년</dt>
            <dd class="text-gray-900">{{ candidate.birth_year }}</dd>
          </div>
          {% endif %}
          {% if candidate.email %}
          <div class="flex justify-between">
            <dt class="text-gray-500">이메일</dt>
            <dd class="text-gray-900">{{ candidate.email }}</dd>
          </div>
          {% endif %}
          {% if candidate.phone %}
          <div class="flex justify-between">
            <dt class="text-gray-500">전화</dt>
            <dd class="text-gray-900">{{ candidate.phone }}</dd>
          </div>
          {% endif %}
          {% if candidate.current_company %}
          <div class="flex justify-between">
            <dt class="text-gray-500">현 직장</dt>
            <dd class="text-gray-900">{{ candidate.current_company }} {{ candidate.current_position }}</dd>
          </div>
          {% endif %}
          {% if candidate.total_experience_years %}
          <div class="flex justify-between">
            <dt class="text-gray-500">총 경력</dt>
            <dd class="text-gray-900">{{ candidate.total_experience_years }}년</dd>
          </div>
          {% endif %}
        </dl>
      </div>

      <!-- 경력 -->
      {% if careers %}
      <div class="bg-white rounded-xl border border-gray-200 p-4">
        <h3 class="text-sm font-semibold text-gray-700 mb-3">경력</h3>
        <div class="space-y-3">
          {% for c in careers %}
          <div class="border-l-2 border-indigo-200 pl-3">
            <div class="text-sm font-medium text-gray-900">{{ c.company }} — {{ c.position }}</div>
            <div class="text-xs text-gray-500">
              {{ c.start_date }}{% if c.end_date %} ~ {{ c.end_date }}{% else %} ~ 현재{% endif %}
            </div>
            {% if c.duties %}
            <div class="text-xs text-gray-600 mt-1">{{ c.duties }}</div>
            {% endif %}
          </div>
          {% endfor %}
        </div>
      </div>
      {% endif %}

      <!-- 학력 -->
      {% if educations %}
      <div class="bg-white rounded-xl border border-gray-200 p-4">
        <h3 class="text-sm font-semibold text-gray-700 mb-3">학력</h3>
        {% for e in educations %}
        <div class="text-sm">
          <span class="text-gray-900">{{ e.institution }}</span>
          {% if e.major %}<span class="text-gray-500"> {{ e.major }}</span>{% endif %}
          {% if e.degree %}<span class="text-gray-400"> ({{ e.degree }})</span>{% endif %}
          {% if e.end_year %}<span class="text-gray-400"> {{ e.end_year }}</span>{% endif %}
        </div>
        {% endfor %}
      </div>
      {% endif %}

      <!-- 자격증 + 어학 -->
      {% if certifications or language_skills %}
      <div class="bg-white rounded-xl border border-gray-200 p-4">
        <h3 class="text-sm font-semibold text-gray-700 mb-3">자격증 · 어학</h3>
        {% for cert in certifications %}
        <span class="inline-block text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-700 mr-1 mb-1">
          {{ cert.name }}{% if cert.acquired_date %} ({{ cert.acquired_date }}){% endif %}
        </span>
        {% endfor %}
        {% for lang in language_skills %}
        <span class="inline-block text-xs px-2 py-1 rounded-full bg-blue-50 text-blue-700 mr-1 mb-1">
          {{ lang.language }}{% if lang.test_name %} {{ lang.test_name }}{% endif %}{% if lang.score %} {{ lang.score }}{% endif %}
        </span>
        {% endfor %}
      </div>
      {% endif %}
    </div>

    <!-- 우측: 원본 텍스트 -->
    <div>
      <h2 class="text-sm font-medium text-gray-500 uppercase tracking-wide mb-4">원본 텍스트</h2>
      <div class="bg-gray-50 rounded-xl border border-gray-200 p-4 max-h-[600px] overflow-y-auto">
        <pre class="text-xs text-gray-700 whitespace-pre-wrap font-[Pretendard]">{% if primary_resume %}{{ primary_resume.raw_text }}{% else %}원본 텍스트 없음{% endif %}</pre>
      </div>
    </div>
  </div>

  <!-- 액션 버튼 -->
  {% if candidate.validation_status == "needs_review" %}
  <div class="flex gap-3 mt-6 sticky bottom-0 bg-white py-4 border-t border-gray-100">
    <button
      hx-post="/candidates/review/{{ candidate.pk }}/confirm/"
      hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'
      class="flex-1 py-3 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700"
    >
      확인
    </button>
    <button
      hx-post="/candidates/review/{{ candidate.pk }}/reject/"
      hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'
      class="flex-1 py-3 bg-white text-red-600 border border-red-200 rounded-xl text-sm font-medium hover:bg-red-50"
    >
      거부
    </button>
  </div>
  {% endif %}
</div>
```

- [ ] **8.9: views.py에 status_choices 컨텍스트 추가**

`candidates/views.py`의 `review_list` 함수에서 context에 추가:

```python
# render() 호출의 context dict에 추가:
"status_choices": [
    ("needs_review", "검토 필요"),
    ("auto_confirmed", "자동 확인"),
    ("confirmed", "확인 완료"),
    ("failed", "실패"),
],
```

- [ ] **8.10: Commit**

```bash
git add candidates/urls.py candidates/views.py candidates/templates/ main/urls.py
git commit -m "feat: review UI for extraction validation

HTMX-based review pages: list (filterable by status) +
detail (extracted data vs raw text side by side).
Confirm/reject actions with ExtractionLog tracking."
```

---

## Task 9: 린트 + 통합 테스트 + 체크리스트

**Files:**
- Modify: various (lint fixes)
- Run: full test suite

- [ ] **9.1: 린트 실행 및 수정**

```bash
uv run ruff check candidates/ tests/test_candidates_models.py tests/test_filename_parser.py tests/test_text_extraction.py tests/test_llm_extraction.py tests/test_validation.py tests/test_import_pipeline.py tests/test_drive_sync.py
uv run ruff format candidates/ tests/
```

- [ ] **9.2: 마이그레이션 체크**

```bash
uv run python manage.py makemigrations --check --dry-run
```

Expected: "No changes detected"

- [ ] **9.3: 전체 테스트 실행**

```bash
uv run pytest -v
```

Expected: All tests PASS (기존 테스트 + 새 테스트 모두).

- [ ] **9.4: Django check**

```bash
uv run python manage.py check
```

Expected: "System check identified no issues."

- [ ] **9.5: CHECK_LIST.md 점검**

1. **의존성:** python-docx는 이미 pyproject.toml에 있음. google-api-python-client, google-auth-oauthlib도 이미 있음. 새 패키지 추가 없음.
2. **UX 피드백:** 리뷰 리스트에 빈 상태 메시지 있음. 확인/거부 후 리다이렉트.
3. **DB 마이그레이션:** makemigrations + migrate 완료.
4. **Dockerfile:** antiword + LibreOffice 이미 설치됨. 새 의존성 없음.

- [ ] **9.6: 최종 Commit**

```bash
uv run ruff format .
git add -A
git commit -m "chore: lint fixes and integration test verification"
```

---

## Post-Implementation: 실제 데이터 테스트

계획 구현 완료 후, 실제 Google Drive 데이터로 파이프라인을 테스트해야 합니다:

```bash
# 1. Dry run으로 파일 목록 확인
uv run python manage.py import_resumes --folder=Accounting --dry-run

# 2. 소량 테스트 (5건)
uv run python manage.py import_resumes --folder=Accounting --limit=5

# 3. 결과 확인
uv run python manage.py shell -c "
from candidates.models import Candidate, Resume
print(f'Candidates: {Candidate.objects.count()}')
print(f'Resumes: {Resume.objects.count()}')
for c in Candidate.objects.all()[:5]:
    print(f'  {c.name} - {c.validation_status} ({c.confidence_score})')
"

# 4. 리뷰 UI 확인
# http://localhost:8000/candidates/review/
```
