# DB 저장 정책 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `Candidate=사람`, `Resume=버전` 정책을 코드로 확정하고, 동일인 식별(email/phone) → 기존 Candidate 업데이트 → provenance 저장 경로를 완성한다.

**Architecture:** 동일인 식별 서비스(`candidate_identity.py`)를 신규 생성하여 email/phone 매칭을 담당. `save_pipeline_result()`에 update path를 추가하여 `matched_candidate`가 있으면 기존 Candidate 아래에 새 Resume를 추가하고 대표 프로필을 갱신. `Candidate.current_resume` FK로 현재 기준 Resume를 추적하고, `DiscrepancyReport.compared_resume`에 비교 대상을 기록.

**Tech Stack:** Django 5.2, PostgreSQL, pytest

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `candidates/services/candidate_identity.py` | 동일인 식별 서비스 (email/phone 매칭) |
| Modify | `candidates/models.py:163` | `Candidate.current_resume` FK 추가 |
| Modify | `candidates/services/integrity/save.py:35` | update path 추가, `compared_resume` 저장, version 계산 |
| Modify | `candidates/management/commands/import_resumes.py:302-346` | `identify_candidate()` 호출로 교체 |
| Create | `tests/test_candidate_identity.py` | 동일인 식별 테스트 |
| Create | `tests/test_save_update_path.py` | 저장 경로 update 테스트 |

---

### Task 1: `Candidate.current_resume` FK 추가

**Files:**
- Modify: `candidates/models.py:192-193` (Candidate 모델, email 필드 근처)
- Create: migration via `makemigrations`

- [ ] **Step 1: Add `current_resume` FK to Candidate model**

`candidates/models.py` — `phone` 필드 아래 (line ~193 이후)에 추가:

```python
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=300, blank=True)

    # Current representative resume
    current_resume = models.ForeignKey(
        "candidates.Resume",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="current_for_candidate",
    )
```

- [ ] **Step 2: Generate and apply migration**

```bash
uv run python manage.py makemigrations candidates -n add_candidate_current_resume
uv run python manage.py migrate
```

Expected: migration created and applied successfully.

- [ ] **Step 3: Verify migration**

```bash
uv run python manage.py makemigrations --check --dry-run
```

Expected: "No changes detected"

- [ ] **Step 4: Run existing tests to verify no regression**

```bash
uv run pytest tests/test_import_pipeline.py tests/test_integrity_pipeline.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add candidates/models.py candidates/migrations/
git commit -m "feat: add Candidate.current_resume FK for representative resume tracking"
```

---

### Task 2: 동일인 식별 서비스 생성

**Files:**
- Create: `candidates/services/candidate_identity.py`
- Create: `tests/test_candidate_identity.py`

- [ ] **Step 1: Write failing tests for `identify_candidate()`**

`tests/test_candidate_identity.py`:

```python
import pytest

from candidates.models import Candidate, Category, Resume


@pytest.fixture
def category(db):
    return Category.objects.create(name="HR", name_ko="인사")


@pytest.fixture
def existing_candidate(db, category):
    c = Candidate.objects.create(
        name="김철수",
        email="kim@example.com",
        phone="010-1234-5678",
        primary_category=category,
    )
    Resume.objects.create(
        candidate=c,
        file_name="김철수_v1.pdf",
        drive_file_id="drive_v1",
        drive_folder="HR",
        is_primary=True,
        version=1,
        processing_status=Resume.ProcessingStatus.PARSED,
    )
    return c


class TestIdentifyByEmail:
    def test_match_by_email(self, existing_candidate):
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"email": "kim@example.com", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is not None
        assert result.candidate == existing_candidate
        assert result.match_reason == "email"

    def test_no_match_different_email(self, existing_candidate):
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"email": "park@example.com", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is None

    def test_no_match_empty_email(self, existing_candidate):
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"email": "", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is None


class TestIdentifyByPhone:
    def test_match_by_phone_exact(self, existing_candidate):
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"phone": "010-1234-5678", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is not None
        assert result.candidate == existing_candidate
        assert result.match_reason == "phone"

    def test_match_by_phone_normalized(self, existing_candidate):
        """Different formatting but same number."""
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"phone": "01012345678", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is not None
        assert result.candidate == existing_candidate

    def test_no_match_different_phone(self, existing_candidate):
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"phone": "010-9999-8888", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is None


class TestIdentifyNoAutoMergeByName:
    def test_same_name_different_person_no_merge(self, existing_candidate):
        """Same name but no email/phone match → must NOT auto-merge."""
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"name": "김철수", "email": "", "phone": ""}
        result = identify_candidate(extracted)
        assert result is None

    def test_same_name_no_contact_info(self, existing_candidate):
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"name": "김철수"}
        result = identify_candidate(extracted)
        assert result is None


class TestIdentifyPreviousResume:
    def test_compared_resume_returned(self, existing_candidate):
        """Should return the latest parsed resume for cross-version comparison."""
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"email": "kim@example.com", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is not None
        assert result.compared_resume is not None
        assert result.compared_resume.drive_file_id == "drive_v1"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_candidate_identity.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'candidates.services.candidate_identity'`

- [ ] **Step 3: Implement `identify_candidate()`**

`candidates/services/candidate_identity.py`:

```python
"""Identify whether an incoming resume belongs to an existing candidate.

Policy: auto-merge ONLY on email or phone match.
Name-only matches are NOT used for auto-merge to prevent false merges.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from candidates.models import Candidate, Resume


@dataclass
class IdentityMatch:
    """Result of candidate identity matching."""

    candidate: Candidate
    compared_resume: Resume | None
    match_reason: str  # "email" or "phone"


def _normalize_phone(phone: str) -> str:
    """Strip all non-digit characters for comparison."""
    return re.sub(r"\D", "", phone)


def identify_candidate(extracted: dict) -> IdentityMatch | None:
    """Find an existing candidate matching the extracted resume data.

    Matching order (first match wins):
      1. email exact match (case-insensitive)
      2. phone normalized match

    Returns None if no confident match is found.
    """
    # 1. Email match
    email = (extracted.get("email") or "").strip().lower()
    if email:
        candidate = (
            Candidate.objects.filter(email__iexact=email)
            .order_by("-created_at")
            .first()
        )
        if candidate:
            return IdentityMatch(
                candidate=candidate,
                compared_resume=_latest_parsed_resume(candidate),
                match_reason="email",
            )

    # 2. Phone match (normalized)
    phone = extracted.get("phone") or ""
    normalized = _normalize_phone(phone)
    if len(normalized) >= 10:
        for c in Candidate.objects.exclude(phone="").order_by("-created_at"):
            if _normalize_phone(c.phone) == normalized:
                return IdentityMatch(
                    candidate=c,
                    compared_resume=_latest_parsed_resume(c),
                    match_reason="phone",
                )

    return None


def _latest_parsed_resume(candidate: Candidate) -> Resume | None:
    """Return the most recent parsed resume for cross-version comparison."""
    return (
        candidate.resumes.filter(
            processing_status=Resume.ProcessingStatus.PARSED,
        )
        .order_by("-version")
        .first()
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_candidate_identity.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add candidates/services/candidate_identity.py tests/test_candidate_identity.py
git commit -m "feat: add candidate identity service — email/phone matching only"
```

---

### Task 3: `save_pipeline_result()` update path 추가

**Files:**
- Modify: `candidates/services/integrity/save.py:35-192`
- Create: `tests/test_save_update_path.py`

- [ ] **Step 1: Write failing tests for update path**

`tests/test_save_update_path.py`:

```python
import pytest

from candidates.models import (
    Candidate,
    Career,
    Category,
    DiscrepancyReport,
    Education,
    Resume,
    ValidationDiagnosis,
)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Finance", name_ko="재무")


def _make_pipeline_result(*, name="테스트", email="test@test.com", phone="010-0000-0000"):
    """Create a minimal valid pipeline result for save tests."""
    return {
        "extracted": {
            "name": name,
            "email": email,
            "phone": phone,
            "birth_year": 1990,
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020.01",
                    "end_date": "2022.06",
                    "is_current": False,
                    "position": "개발자",
                    "order": 0,
                },
            ],
            "educations": [
                {
                    "institution": "서울대",
                    "degree": "학사",
                    "major": "컴퓨터",
                    "start_year": 2010,
                    "end_year": 2014,
                },
            ],
            "certifications": [],
            "language_skills": [],
        },
        "diagnosis": {
            "verdict": "pass",
            "overall_score": 0.9,
            "issues": [],
            "field_scores": {},
        },
        "attempts": 1,
        "retry_action": "none",
        "raw_text_used": "이력서 텍스트",
        "integrity_flags": [],
    }


def _make_primary_file(file_id="drive_001"):
    return {
        "file_name": "test_resume.pdf",
        "file_id": file_id,
        "mime_type": "application/pdf",
        "file_size": 1000,
    }


class TestSaveNewCandidate:
    def test_creates_new_candidate_when_no_match(self, category):
        from candidates.services.integrity.save import save_pipeline_result

        result = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="이력서 텍스트",
            category=category,
            primary_file=_make_primary_file(),
        )
        assert result is not None
        assert Candidate.objects.count() == 1
        assert Resume.objects.filter(candidate=result).count() == 1
        assert result.current_resume is not None
        assert result.current_resume.version == 1


class TestSaveUpdateExisting:
    def test_reuses_candidate_on_match(self, category):
        from candidates.services.integrity.save import save_pipeline_result

        # First import
        c1 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        assert c1 is not None

        # Second import — same email, different file
        c2 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        assert c2 is not None
        assert c2.id == c1.id  # Same candidate reused
        assert Candidate.objects.count() == 1
        assert Resume.objects.filter(candidate=c2).count() == 2

    def test_version_increments(self, category):
        from candidates.services.integrity.save import save_pipeline_result

        save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        c2 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        latest_resume = c2.current_resume
        assert latest_resume.version == 2

    def test_current_resume_updated(self, category):
        from candidates.services.integrity.save import save_pipeline_result

        c1 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        old_resume = c1.current_resume

        c2 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        assert c2.current_resume != old_resume
        assert c2.current_resume.version == 2

    def test_careers_rebuilt_on_update(self, category):
        from candidates.services.integrity.save import save_pipeline_result

        c1 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        assert Career.objects.filter(candidate=c1).count() == 1

        # Second import with 2 careers
        result2 = _make_pipeline_result()
        result2["extracted"]["careers"].append(
            {
                "company": "B사",
                "start_date": "2022.07",
                "end_date": "2024.01",
                "is_current": False,
                "position": "시니어",
                "order": 1,
            }
        )
        c2 = save_pipeline_result(
            pipeline_result=result2,
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        assert Career.objects.filter(candidate=c2).count() == 2

    def test_validation_diagnosis_per_resume(self, category):
        from candidates.services.integrity.save import save_pipeline_result

        save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        assert ValidationDiagnosis.objects.count() == 2


class TestComparedResumeSaved:
    def test_compared_resume_set_on_update(self, category):
        from candidates.services.integrity.save import save_pipeline_result

        save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        report = DiscrepancyReport.objects.order_by("-created_at").first()
        assert report.compared_resume is not None
        assert report.compared_resume.drive_file_id == "drive_001"

    def test_compared_resume_none_on_first_import(self, category):
        from candidates.services.integrity.save import save_pipeline_result

        save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        report = DiscrepancyReport.objects.first()
        assert report.compared_resume is None


class TestNoMergeByNameOnly:
    def test_different_email_creates_new_candidate(self, category):
        from candidates.services.integrity.save import save_pipeline_result

        save_pipeline_result(
            pipeline_result=_make_pipeline_result(name="김철수", email="kim1@test.com", phone="010-1111-1111"),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(name="김철수", email="kim2@test.com", phone="010-2222-2222"),
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        assert Candidate.objects.count() == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_save_update_path.py -v
```

Expected: multiple failures — `current_resume` not set, update path not implemented, etc.

- [ ] **Step 3: Modify `save_pipeline_result()` to support update path**

Rewrite `candidates/services/integrity/save.py`. The key changes:

1. Import and call `identify_candidate()` at the start
2. If matched, reuse existing `Candidate` instead of creating new
3. On update: delete old sub-records (Career, Education, etc.) and recreate from new extraction
4. Set `Candidate.current_resume` after creating the primary Resume
5. Pass `compared_resume` to `DiscrepancyReport.objects.create()`
6. Calculate version from existing resume count

Replace the function `save_pipeline_result()` (lines 35-192) with:

```python
def save_pipeline_result(
    pipeline_result: dict,
    raw_text: str,
    category: Category,
    primary_file: dict,
    other_files: list[dict] | None = None,
    existing_ids: set | None = None,
) -> Candidate | None:
    """Save integrity pipeline result to DB.

    Storage policy:
    - Candidate = person (reused if email/phone matches)
    - Resume = version (always created new)
    - On update: sub-records (Career, Education, etc.) are rebuilt from latest extraction
    - current_resume tracks which Resume the current profile is based on
    """
    from candidates.services.candidate_identity import identify_candidate

    extracted = pipeline_result.get("extracted")
    if not extracted:
        _save_failed_resume(primary_file, category.name, "Extraction failed")
        return None

    diagnosis = pipeline_result["diagnosis"]
    field_confidences = extracted.get("field_confidences", {})
    overall_score = diagnosis.get("overall_score", 0.0)
    validation = {
        "confidence_score": overall_score,
        "validation_status": (
            "auto_confirmed"
            if diagnosis["verdict"] == "pass" and overall_score >= 0.85
            else "needs_review"
            if overall_score >= 0.6
            else "failed"
        ),
        "field_confidences": {
            **field_confidences,
            **diagnosis.get("field_scores", {}),
        },
        "issues": diagnosis.get("issues", []),
    }

    other_files = other_files or []
    existing_ids = existing_ids or set()

    # Identify existing candidate
    identity = identify_candidate(extracted)
    matched_candidate = identity.candidate if identity else None
    compared_resume = identity.compared_resume if identity else None

    with transaction.atomic():
        if matched_candidate:
            candidate = _update_candidate(matched_candidate, extracted, raw_text, validation, category, primary_file)
        else:
            candidate = _create_candidate(extracted, raw_text, validation, category, primary_file)

        _rebuild_sub_records(candidate, extracted)

        # Calculate next version
        max_version = candidate.resumes.aggregate(
            max_v=models.Max("version")
        )["max_v"] or 0
        next_version = max_version + 1

        primary_resume = Resume.objects.create(
            candidate=candidate,
            file_name=primary_file["file_name"],
            drive_file_id=primary_file["file_id"],
            drive_folder=category.name,
            mime_type=primary_file.get("mime_type", ""),
            file_size=primary_file.get("file_size"),
            raw_text=raw_text,
            is_primary=True,
            version=next_version,
            processing_status=Resume.ProcessingStatus.PARSED,
        )

        # Set current_resume
        candidate.current_resume = primary_resume
        candidate.save(update_fields=["current_resume", "updated_at"])

        for idx, other in enumerate(other_files):
            if other["file_id"] not in existing_ids:
                Resume.objects.create(
                    candidate=candidate,
                    file_name=other["file_name"],
                    drive_file_id=other["file_id"],
                    drive_folder=category.name,
                    mime_type=other.get("mime_type", ""),
                    file_size=other.get("file_size"),
                    is_primary=False,
                    version=next_version + idx + 1,
                    processing_status=Resume.ProcessingStatus.PENDING,
                )

        ExtractionLog.objects.create(
            candidate=candidate,
            resume=primary_resume,
            action=ExtractionLog.Action.AUTO_EXTRACT,
            field_name="full_extraction",
            new_value=str(extracted),
            confidence=validation["confidence_score"],
            note=f"Imported from Drive folder: {category.name}",
        )

        ValidationDiagnosis.objects.create(
            candidate=candidate,
            resume=primary_resume,
            attempt_number=pipeline_result["attempts"],
            verdict=diagnosis["verdict"],
            overall_score=diagnosis.get("overall_score", 0.0),
            issues=diagnosis.get("issues", []),
            field_scores=diagnosis.get("field_scores", {}),
            retry_action=pipeline_result["retry_action"],
        )

        candidate.categories.add(category)

        # Combined discrepancy report
        integrity_flags = pipeline_result.get("integrity_flags", [])
        integrity_alerts = _convert_flags_to_alerts(integrity_flags)

        rule_report = scan_candidate_discrepancies(
            candidate, source_resume=primary_resume, save=False,
        )
        rule_alerts = rule_report.get("alerts", []) if isinstance(rule_report, dict) else []

        type_aliases = {
            "PERIOD_OVERLAP": "OVERLAP",
            "DATE_CONFLICT": "DATE_ORDER",
        }

        def _dedup_key(alert: dict) -> tuple:
            atype = alert.get("type", "")
            normalized_type = type_aliases.get(atype, atype)
            return (normalized_type, alert.get("field", ""))

        seen_keys = set()
        combined_alerts = []
        for alert in integrity_alerts:
            key = _dedup_key(alert)
            seen_keys.add(key)
            combined_alerts.append(alert)
        for alert in rule_alerts:
            key = _dedup_key(alert)
            if key not in seen_keys:
                combined_alerts.append(alert)

        combined_alerts.sort(
            key=lambda a: {"RED": 0, "YELLOW": 1, "BLUE": 2}.get(a.get("severity", ""), 3)
        )

        DiscrepancyReport.objects.create(
            candidate=candidate,
            source_resume=primary_resume,
            compared_resume=compared_resume,
            report_type=DiscrepancyReport.ReportType.SELF_CONSISTENCY,
            integrity_score=compute_integrity_score(combined_alerts),
            summary=_build_summary(combined_alerts),
            alerts=combined_alerts,
            scan_version="v4",
        )

    return candidate
```

Add these new helper functions (after `save_pipeline_result`, before `_convert_flags_to_alerts`):

```python
def _update_candidate(
    candidate: Candidate,
    extracted: dict,
    raw_text: str,
    validation: dict,
    category: Category,
    primary_file: dict | None = None,
) -> Candidate:
    """Update existing candidate's profile fields from new extraction."""
    from candidates.services.detail_normalizers import (
        normalize_awards,
        normalize_family,
        normalize_military,
        normalize_overseas,
        normalize_patents,
        normalize_projects,
        normalize_self_intro,
        normalize_trainings,
    )
    from candidates.services.salary_parser import normalize_salary

    salary_result = normalize_salary(extracted)
    military = extracted.get("military_service") or extracted.get("military") or {}

    resume_reference_date = extracted.get("resume_reference_date") or ""
    resume_reference_source = extracted.get("resume_reference_date_source") or ""
    resume_reference_evidence = extracted.get("resume_reference_date_evidence") or ""

    if not resume_reference_date and primary_file and primary_file.get("modified_time"):
        resume_reference_date = primary_file["modified_time"]
        resume_reference_source = "file_modified_time"
        resume_reference_evidence = "Drive modifiedTime fallback"

    candidate.name = extracted.get("name") or candidate.name
    candidate.name_en = extracted.get("name_en") or candidate.name_en
    candidate.birth_year = extracted.get("birth_year") or candidate.birth_year
    candidate.gender = extracted.get("gender") or candidate.gender
    candidate.email = extracted.get("email") or candidate.email
    candidate.phone = extracted.get("phone") or candidate.phone
    candidate.address = extracted.get("address") or candidate.address
    candidate.current_company = extracted.get("current_company") or candidate.current_company
    candidate.current_position = extracted.get("current_position") or candidate.current_position
    candidate.total_experience_years = extracted.get("total_experience_years") or candidate.total_experience_years
    candidate.resume_reference_date = resume_reference_date or candidate.resume_reference_date
    candidate.resume_reference_date_source = resume_reference_source or candidate.resume_reference_date_source
    candidate.resume_reference_date_evidence = resume_reference_evidence or candidate.resume_reference_date_evidence
    candidate.core_competencies = extracted.get("core_competencies") or candidate.core_competencies
    candidate.summary = extracted.get("summary") or candidate.summary
    candidate.raw_text = raw_text
    candidate.validation_status = validation["validation_status"]
    candidate.raw_extracted_json = extracted
    candidate.confidence_score = validation["confidence_score"]
    candidate.field_confidences = validation.get("field_confidences", {})
    candidate.primary_category = category
    candidate.current_salary = salary_result["current_salary_int"]
    candidate.desired_salary = salary_result["desired_salary_int"]
    candidate.salary_detail = salary_result["salary_detail"]
    candidate.military_service = normalize_military(military) if military else {}
    candidate.awards = normalize_awards(
        extracted.get("awards") or extracted.get("honors") or []
    )
    candidate.self_introduction = normalize_self_intro(
        extracted.get("self_introduction")
        or extracted.get("personal_statement")
        or extracted.get("cover_letter")
        or extracted.get("objective")
        or ""
    )
    candidate.family_info = normalize_family(
        extracted.get("family_info")
        or extracted.get("family_background")
        or extracted.get("marital_status")
        or {}
    )
    candidate.overseas_experience = normalize_overseas(
        extracted.get("overseas_experience")
        or extracted.get("international_experience")
        or extracted.get("residence_abroad")
        or []
    )
    candidate.trainings = normalize_trainings(
        extracted.get("trainings")
        or extracted.get("training_courses")
        or extracted.get("training_programs")
        or extracted.get("education_history")
        or []
    )
    candidate.patents = normalize_patents(
        extracted.get("patents_registered")
        or extracted.get("patents_applications")
        or extracted.get("patents")
        or []
    )
    candidate.projects = normalize_projects(extracted.get("projects") or [])
    candidate.save()
    return candidate


def _rebuild_sub_records(candidate: Candidate, extracted: dict):
    """Delete and recreate normalized sub-records from latest extraction."""
    candidate.educations.all().delete()
    candidate.careers.all().delete()
    candidate.certifications.all().delete()
    candidate.language_skills.all().delete()

    _create_educations(candidate, extracted.get("educations", []))
    _create_careers(candidate, extracted.get("careers", []))
    _create_certifications(candidate, extracted.get("certifications", []))
    _create_language_skills(candidate, extracted.get("language_skills", []))
```

Also add `from django.db import models` to the imports at the top of `save.py` (for `models.Max`):

```python
from django.db import models, transaction
```

(Replace the existing `from django.db import transaction`)

- [ ] **Step 4: Run new tests to verify they pass**

```bash
uv run pytest tests/test_save_update_path.py -v
```

Expected: all 10 tests pass.

- [ ] **Step 5: Run all existing tests to verify no regression**

```bash
uv run pytest -v
```

Expected: all 263+ tests pass.

- [ ] **Step 6: Commit**

```bash
git add candidates/services/integrity/save.py tests/test_save_update_path.py
git commit -m "feat: add update path to save_pipeline_result — reuse Candidate on email/phone match"
```

---

### Task 4: `import_resumes.py`에서 `_find_previous_data()` 교체

**Files:**
- Modify: `candidates/management/commands/import_resumes.py:302-389`

- [ ] **Step 1: Update `import_resumes.py` to use `identify_candidate()` for `previous_data`**

The `_find_previous_data()` method is now only used for cross-version comparison data (feeding `previous_data` to the pipeline). The actual identity matching is handled inside `save_pipeline_result()`. So we replace `_find_previous_data()` with a simpler version that uses `identify_candidate()`.

In `import_resumes.py`, replace lines 302-305 (the `previous_data` lookup block):

```python
            # Look up previous version for cross-version comparison
            previous_data = None
            if getattr(self, "use_integrity", False) and parsed.get("name"):
                previous_data = self._find_previous_data(parsed)
```

with:

```python
            # Look up previous version for cross-version comparison
            previous_data = None
            if getattr(self, "use_integrity", False):
                previous_data = self._find_previous_data(extracted)
```

Note: now passes `extracted` (full LLM result with email/phone) instead of `parsed` (filename metadata).

Replace the `_find_previous_data` method (lines 349-389) with:

```python
    def _find_previous_data(self, extracted: dict) -> dict | None:
        """Find existing candidate's data for cross-version comparison."""
        from candidates.services.candidate_identity import identify_candidate

        identity = identify_candidate(extracted)
        if not identity or not identity.compared_resume:
            return None

        candidate = identity.candidate
        careers = [
            {
                "company": c.company,
                "start_date": c.start_date,
                "end_date": c.end_date,
                "position": c.position,
            }
            for c in candidate.careers.all()
        ]
        educations = [
            {
                "institution": e.institution,
                "degree": e.degree,
                "start_year": e.start_year,
                "end_year": e.end_year,
            }
            for e in candidate.educations.all()
        ]

        return {"careers": careers, "educations": educations}
```

Also move the `previous_data` lookup to AFTER extraction (line ~326, after `extracted` is available), since we now need email/phone from extracted data:

The full block around lines 300-340 should become:

```python
            # Step 2: Extract text + preprocess
            from candidates.services.text_extraction import preprocess_resume_text

            raw_text = extract_text(dest_path)
            if not raw_text or not raw_text.strip():
                self._save_failed_resume(primary, folder_name, "Empty text extraction")
                return False
            raw_text = preprocess_resume_text(raw_text)

            # Step 3: Extract + Validate + Retry
            # First pass without previous_data to get extracted fields
            pipeline_result = run_extraction_with_retry(
                raw_text=raw_text,
                file_path=dest_path,
                category=folder_name,
                filename_meta=parsed,
                file_reference_date=primary.get("modified_time"),
                use_integrity_pipeline=getattr(self, "use_integrity", False),
                previous_data=None,
            )

            extracted = pipeline_result["extracted"]
            if not extracted:
                self._save_failed_resume(
                    primary, folder_name, "Extraction failed after retries"
                )
                return False

            # Look up previous version for cross-version comparison (needs extracted email/phone)
            if getattr(self, "use_integrity", False):
                previous_data = self._find_previous_data(extracted)
                if previous_data:
                    # Re-run with previous_data for cross-version flags
                    pipeline_result = run_extraction_with_retry(
                        raw_text=raw_text,
                        file_path=dest_path,
                        category=folder_name,
                        filename_meta=parsed,
                        file_reference_date=primary.get("modified_time"),
                        use_integrity_pipeline=True,
                        previous_data=previous_data,
                    )
                    extracted = pipeline_result["extracted"]
                    if not extracted:
                        self._save_failed_resume(
                            primary, folder_name, "Extraction failed after retries"
                        )
                        return False

            # Use potentially re-extracted text
            raw_text = pipeline_result["raw_text_used"]
```

Wait — re-running the full pipeline is expensive. A better approach: feed `previous_data` on the first call if we can find it from filename metadata, and let `save_pipeline_result()` handle identity matching independently. The current flow already works this way. So the simpler fix is:

Keep the original flow structure but replace only `_find_previous_data()` to use `identify_candidate()` with the filename-parsed data, falling back to the old name-based lookup when email/phone aren't available from filename:

```python
    def _find_previous_data(self, parsed: dict) -> dict | None:
        """Find existing candidate's data for cross-version comparison.

        Uses identify_candidate() if email/phone available, otherwise
        falls back to name-based lookup for comparison-only purposes.
        Note: this is ONLY for cross-version comparison, NOT for identity
        matching. Identity matching happens in save_pipeline_result().
        """
        from candidates.models import Candidate, Career, Education
        from candidates.services.candidate_identity import identify_candidate

        # Try identity service first (email/phone)
        identity = identify_candidate(parsed)
        if identity:
            candidate = identity.candidate
        else:
            # Fallback: name-based lookup for comparison only
            name = parsed.get("name", "")
            if not name:
                return None
            qs = Candidate.objects.filter(name=name)
            birth_year = parsed.get("birth_year")
            if birth_year:
                try:
                    qs = qs.filter(birth_year=int(birth_year))
                except (ValueError, TypeError):
                    pass
            candidate = qs.order_by("-created_at").first()

        if not candidate:
            return None

        careers = [
            {
                "company": c.company,
                "start_date": c.start_date,
                "end_date": c.end_date,
                "position": c.position,
            }
            for c in candidate.careers.all()
        ]
        educations = [
            {
                "institution": e.institution,
                "degree": e.degree,
                "start_year": e.start_year,
                "end_year": e.end_year,
            }
            for e in candidate.educations.all()
        ]

        return {"careers": careers, "educations": educations}
```

This keeps the existing call site unchanged (`self._find_previous_data(parsed)` at line 305) — no flow restructuring needed.

- [ ] **Step 2: Run all tests**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add candidates/management/commands/import_resumes.py
git commit -m "refactor: use identify_candidate() in import_resumes for cross-version lookup"
```

---

### Task 5: 전체 통합 테스트 및 정리

**Files:**
- Modify: `tests/test_import_pipeline.py` (idempotency 테스트에 update 시나리오 추가)

- [ ] **Step 1: Add integration test for idempotency with update**

Append to `tests/test_import_pipeline.py`:

```python
class TestCandidateUpdateOnReimport:
    """Verify that re-importing with same email reuses the Candidate."""

    def test_same_email_reuses_candidate(self, db, accounting_category):
        from candidates.services.integrity.save import save_pipeline_result

        pipeline_result = {
            "extracted": {
                "name": "강솔찬",
                "email": "kang@example.com",
                "phone": "010-1234-5678",
                "birth_year": 1985,
                "current_company": "현대",
                "careers": [],
                "educations": [],
                "certifications": [],
                "language_skills": [],
            },
            "diagnosis": {"verdict": "pass", "overall_score": 0.9, "issues": [], "field_scores": {}},
            "attempts": 1,
            "retry_action": "none",
            "raw_text_used": "텍스트",
            "integrity_flags": [],
        }
        file1 = {"file_name": "강솔찬_v1.pdf", "file_id": "id_v1", "mime_type": "application/pdf"}
        file2 = {"file_name": "강솔찬_v2.pdf", "file_id": "id_v2", "mime_type": "application/pdf"}

        c1 = save_pipeline_result(
            pipeline_result=pipeline_result,
            raw_text="v1",
            category=accounting_category,
            primary_file=file1,
        )
        c2 = save_pipeline_result(
            pipeline_result=pipeline_result,
            raw_text="v2",
            category=accounting_category,
            primary_file=file2,
        )
        assert c1.id == c2.id
        assert Candidate.objects.count() == 1
        assert Resume.objects.filter(candidate=c1).count() == 2
```

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass (263+ existing + new tests).

- [ ] **Step 3: Commit**

```bash
git add tests/test_import_pipeline.py
git commit -m "test: add integration test for candidate reuse on re-import"
```

- [ ] **Step 4: Verify migration is clean**

```bash
uv run python manage.py makemigrations --check --dry-run
```

Expected: "No changes detected"

---

Plan complete and saved to `docs/superpowers/plans/2026-04-03-db-save-policy.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
