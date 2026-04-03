# 이력서 위조 탐지 파이프라인 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이력서 추출 파이프라인을 재설계하여 원문의 정보 소실 없이 데이터를 추출하고, 추출 과정에서 위조 의심 흔적을 자동 탐지한다.

**Architecture:** 4단계 파이프라인 — Step 1(충실한 추출) → Step 1.5(시멘틱 그룹핑) → Step 2(그룹별 정규화+위조탐지, 병렬) → Step 3(교차분석, 코드). 각 단계에 품질 검증 + 자동 재시도 루프 내장. 기존 retry_pipeline.py 패턴을 확장.

**Tech Stack:** Python 3.13, Django 5.2, Gemini 3.1 Flash (google-genai), 기존 candidates 앱

**Spec:** `docs/superpowers/specs/2026-04-03-integrity-check-pipeline-design.md`

---

## 파일 구조

### 신규 파일
- `candidates/services/integrity/step1_extract.py` — Step 1 충실한 추출
- `candidates/services/integrity/step1_5_grouping.py` — Step 1.5 시멘틱 그룹핑
- `candidates/services/integrity/step2_normalize.py` — Step 2 그룹별 정규화+위조탐지
- `candidates/services/integrity/step3_overlap.py` — Step 3 교차분석 (코드)
- `candidates/services/integrity/validators.py` — 단계별 품질 검증
- `candidates/services/integrity/pipeline.py` — 전체 오케스트레이션
- `candidates/services/integrity/__init__.py`
- `tests/test_integrity_step1.py`
- `tests/test_integrity_step1_5.py`
- `tests/test_integrity_step2.py`
- `tests/test_integrity_step3.py`
- `tests/test_integrity_validators.py`
- `tests/test_integrity_pipeline.py`

### 수정 파일
- `candidates/services/retry_pipeline.py` — 새 파이프라인 호출로 전환
- `candidates/management/commands/import_resumes.py` — 새 파이프라인 연결
- `candidates/models.py` — integrity_flags 통합

---

## Task 1: Step 3 — 교차분석 (PERIOD_OVERLAP)

Step 3부터 시작하는 이유: 기존 discrepancy.py의 overlap 로직을 추출하여 독립 모듈로 만드는 것이므로 가장 단순하고, 다른 Step과 의존성이 없다.

**Files:**
- Create: `candidates/services/integrity/__init__.py`
- Create: `candidates/services/integrity/step3_overlap.py`
- Test: `tests/test_integrity_step3.py`

- [ ] **Step 1: __init__.py 생성**

```bash
mkdir -p candidates/services/integrity
touch candidates/services/integrity/__init__.py
```

- [ ] **Step 2: PERIOD_OVERLAP 계산 테스트 작성**

```python
# tests/test_integrity_step3.py
import pytest
from datetime import date

from candidates.services.integrity.step3_overlap import check_period_overlaps


class TestPeriodOverlaps:
    def test_no_overlap_sequential_careers(self):
        careers = [
            {"company": "A사", "start_date": "2020-01", "end_date": "2022-06", "is_current": False},
            {"company": "B사", "start_date": "2022-07", "end_date": "2024-01", "is_current": False},
        ]
        result = check_period_overlaps(careers)
        assert result == []

    def test_short_overlap_normal(self):
        """이직 인수인계 수준의 짧은 중복은 flag 없음"""
        careers = [
            {"company": "A사", "start_date": "2020-01", "end_date": "2022-06", "is_current": False},
            {"company": "B사", "start_date": "2022-05", "end_date": "2024-01", "is_current": False},
        ]
        result = check_period_overlaps(careers)
        assert result == []

    def test_long_overlap_flagged(self):
        """장기 중복은 flag"""
        careers = [
            {"company": "A사", "start_date": "2020-01", "end_date": "2022-06", "is_current": False},
            {"company": "B사", "start_date": "2021-01", "end_date": "2024-01", "is_current": False},
        ]
        result = check_period_overlaps(careers)
        assert len(result) == 1
        assert result[0]["type"] == "PERIOD_OVERLAP"
        assert result[0]["overlap_months"] > 12

    def test_current_career_uses_today(self):
        """is_current=True인 경력은 오늘 날짜를 종료일로 사용"""
        careers = [
            {"company": "A사", "start_date": "2020-01", "end_date": None, "is_current": True},
            {"company": "B사", "start_date": "2023-01", "end_date": "2024-01", "is_current": False},
        ]
        result = check_period_overlaps(careers)
        assert len(result) >= 1

    def test_affiliated_group_excluded(self):
        """계열사 관계 그룹은 중복에서 제외"""
        careers = [
            {"company": "삼성카드", "start_date": "2002-08", "end_date": "2006-05", "is_current": False},
            {"company": "삼성그룹 e-HR T/F", "start_date": "2004-03", "end_date": "2005-03", "is_current": False},
        ]
        affiliated_groups = [{"canonical_name": "삼성", "entry_indices": [0, 1], "relationship": "affiliated_group"}]
        result = check_period_overlaps(careers, affiliated_groups=affiliated_groups)
        assert result == []

    def test_severity_multiple_overlaps_escalates(self):
        """여러 건의 장기 중복이 반복되면 severity 상승"""
        careers = [
            {"company": "A사", "start_date": "1994-02", "end_date": "1995-11", "is_current": False},
            {"company": "B사", "start_date": "1995-01", "end_date": "1997-10", "is_current": False},
            {"company": "C사", "start_date": "1996-10", "end_date": "2000-03", "is_current": False},
        ]
        result = check_period_overlaps(careers)
        severities = [f["severity"] for f in result]
        assert "RED" in severities  # 반복 패턴이므로 RED
```

- [ ] **Step 3: 테스트 실행 — 실패 확인**

```bash
uv run pytest tests/test_integrity_step3.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'candidates.services.integrity.step3_overlap'`

- [ ] **Step 4: step3_overlap.py 구현**

```python
# candidates/services/integrity/step3_overlap.py
"""Step 3: Rule-based PERIOD_OVERLAP detection on normalized career data."""

from __future__ import annotations

from datetime import date


def _month_index(year: int, month: int) -> int:
    return year * 12 + month


def _parse_ym(date_str: str) -> tuple[int, int] | None:
    """Parse YYYY-MM string to (year, month)."""
    if not date_str:
        return None
    try:
        parts = date_str.split("-")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None


def _is_affiliated(idx_a: int, idx_b: int, affiliated_groups: list[dict]) -> bool:
    """Check if two career indices belong to the same affiliated group."""
    for group in affiliated_groups:
        if group.get("relationship") != "affiliated_group":
            continue
        indices = group.get("entry_indices", [])
        if idx_a in indices and idx_b in indices:
            return True
    return False


SHORT_OVERLAP_THRESHOLD = 3  # months — transition period


def check_period_overlaps(
    careers: list[dict],
    *,
    affiliated_groups: list[dict] | None = None,
) -> list[dict]:
    """Detect PERIOD_OVERLAP between normalized careers.

    Args:
        careers: Normalized career records with start_date, end_date, is_current.
        affiliated_groups: Group info from Step 1.5 to exclude affiliated overlaps.

    Returns:
        List of integrity_flag dicts.
    """
    today = date.today()
    today_idx = _month_index(today.year, today.month)
    affiliated_groups = affiliated_groups or []

    intervals = []
    for i, c in enumerate(careers):
        start = _parse_ym(c.get("start_date", ""))
        if start is None:
            continue

        end_str = c.get("end_date", "")
        if end_str:
            end = _parse_ym(end_str)
            if end is None:
                continue
            end_idx = _month_index(*end)
        elif c.get("is_current"):
            end_idx = today_idx
        else:
            continue

        intervals.append({
            "index": i,
            "company": c.get("company", ""),
            "start": _month_index(*start),
            "end": end_idx,
            "period": f"{c.get('start_date', '')}~{end_str or '현재'}",
        })

    intervals.sort(key=lambda x: x["start"])

    raw_overlaps = []
    for i, a in enumerate(intervals):
        for b in intervals[i + 1:]:
            if b["start"] > a["end"]:
                break
            overlap = min(a["end"], b["end"]) - b["start"]
            if overlap <= 0:
                continue
            if _is_affiliated(a["index"], b["index"], affiliated_groups):
                continue
            if overlap <= SHORT_OVERLAP_THRESHOLD:
                continue
            raw_overlaps.append({
                "company_a": a["company"],
                "period_a": a["period"],
                "company_b": b["company"],
                "period_b": b["period"],
                "overlap_months": overlap,
            })

    if not raw_overlaps:
        return []

    # Severity: single long overlap → YELLOW, repeated pattern → RED
    has_repeated = len(raw_overlaps) >= 2
    flags = []
    for o in raw_overlaps:
        severity = "RED" if has_repeated else "YELLOW"
        flags.append({
            "type": "PERIOD_OVERLAP",
            "severity": severity,
            "field": "careers",
            "detail": (
                f"{o['company_a']}({o['period_a']})와 "
                f"{o['company_b']}({o['period_b']}) "
                f"재직 기간이 {o['overlap_months']}개월 중복됨"
            ),
            "chosen": None,
            "alternative": None,
            "reasoning": (
                "반복적인 장기 중복 패턴" if has_repeated
                else "이직 인수인계를 넘어서는 장기 중복"
            ),
        })

    return flags
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

```bash
uv run pytest tests/test_integrity_step3.py -v
```
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add candidates/services/integrity/ tests/test_integrity_step3.py
git commit -m "feat: add Step 3 PERIOD_OVERLAP detection module"
```

---

## Task 2: 단계별 품질 검증 모듈

**Files:**
- Create: `candidates/services/integrity/validators.py`
- Test: `tests/test_integrity_validators.py`

- [ ] **Step 1: Step 1 검증 테스트 작성**

```python
# tests/test_integrity_validators.py
import pytest

from candidates.services.integrity.validators import (
    validate_step1,
    validate_step1_5,
    validate_step2,
)


class TestStep1Validation:
    def test_pass_with_complete_extraction(self):
        raw_data = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "source_section": "경력란"},
                {"company": "A사", "start_date": "2020-01", "source_section": "경력기술서"},
            ],
            "educations": [
                {"institution": "서울대", "source_section": "학력란"},
            ],
        }
        resume_text = "경력란에 A사 2020년 입사. 경력기술서에서 상세."
        issues = validate_step1(raw_data, resume_text)
        assert not any(i["severity"] == "error" for i in issues)

    def test_fail_single_source_section(self):
        """모든 항목이 같은 source_section이면 다른 섹션 누락 의심"""
        raw_data = {
            "careers": [
                {"company": "A사", "source_section": "경력란"},
                {"company": "B사", "source_section": "경력란"},
            ],
            "educations": [],
        }
        resume_text = "경력란 A사. 경력기술서 A사 상세 업무."  # 두 섹션인데 하나만 추출
        issues = validate_step1(raw_data, resume_text)
        assert any("섹션" in i.get("message", "") or "source" in i.get("message", "") for i in issues)

    def test_fail_japanese_text_but_no_japanese_section(self):
        """일문 텍스트가 있는데 일문 source_section이 없으면 누락"""
        raw_data = {
            "careers": [
                {"company": "A사", "source_section": "국문 경력란"},
            ],
            "educations": [],
        }
        resume_text = "국문 경력란 A사. 経歴紹介書 A株式会社 営業部"
        issues = validate_step1(raw_data, resume_text)
        assert any(i["severity"] == "warning" for i in issues)

    def test_fail_missing_duration_text(self):
        """원문에 괄호 기간이 있는데 duration_text가 비었으면 누락"""
        raw_data = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "duration_text": None, "source_section": "경력란"},
            ],
            "educations": [],
        }
        resume_text = "A사 2020.01~2022.06 (2년 6개월)"
        issues = validate_step1(raw_data, resume_text)
        assert any("duration" in i.get("message", "").lower() for i in issues)


class TestStep15Validation:
    def test_pass_low_ungrouped(self):
        grouping = {
            "career_groups": [{"group_id": "g1", "entry_indices": [0, 1]}],
            "ungrouped_career_indices": [],
        }
        total_careers = 2
        issues = validate_step1_5(grouping, total_careers, total_educations=0)
        assert not any(i["severity"] == "error" for i in issues)

    def test_fail_high_ungrouped(self):
        """ungrouped 비율이 높으면 경고"""
        grouping = {
            "career_groups": [{"group_id": "g1", "entry_indices": [0]}],
            "ungrouped_career_indices": [1, 2, 3, 4],
        }
        total_careers = 5
        issues = validate_step1_5(grouping, total_careers, total_educations=0)
        assert any(i["severity"] == "warning" for i in issues)


class TestStep2Validation:
    def test_pass_complete_normalization(self):
        normalized = {
            "career": {"company": "A사", "start_date": "2020-01", "end_date": "2022-06"},
            "flags": [],
        }
        issues = validate_step2(normalized)
        assert issues == []

    def test_fail_missing_start_date(self):
        normalized = {
            "career": {"company": "A사", "start_date": None, "end_date": "2022-06"},
            "flags": [],
        }
        issues = validate_step2(normalized)
        assert any("start_date" in i.get("message", "") for i in issues)

    def test_fail_invalid_date_format(self):
        normalized = {
            "career": {"company": "A사", "start_date": "2020.01", "end_date": "2022-06"},
            "flags": [],
        }
        issues = validate_step2(normalized)
        assert any("형식" in i.get("message", "") or "format" in i.get("message", "") for i in issues)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
uv run pytest tests/test_integrity_validators.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: validators.py 구현**

```python
# candidates/services/integrity/validators.py
"""Per-step quality validators for the integrity pipeline."""

from __future__ import annotations

import re


def _has_cjk_japanese(text: str) -> bool:
    """Detect Japanese-specific characters (katakana, hiragana)."""
    return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF]', text))


def _has_significant_english(text: str) -> bool:
    """Detect significant English content (not just short words)."""
    return bool(re.search(r'[A-Za-z]{15,}', text))


def _has_parenthetical_duration(text: str) -> bool:
    """Detect duration expressions in parentheses like (11개월), (2Y 6M)."""
    return bool(re.search(r'\(\d+[년Y년개월M\s]+\)', text, re.IGNORECASE))


def validate_step1(raw_data: dict, resume_text: str) -> list[dict]:
    """Validate Step 1 extraction completeness.

    Checks:
    - source_section diversity (multiple sections extracted?)
    - Language coverage (Japanese/English text → matching sections?)
    - duration_text capture (parenthetical durations in text → captured?)
    """
    issues = []
    careers = raw_data.get("careers", [])
    educations = raw_data.get("educations", [])

    # source_section diversity
    career_sections = set(c.get("source_section", "") for c in careers)
    if len(careers) >= 2 and len(career_sections) <= 1:
        issues.append({
            "severity": "warning",
            "message": "모든 경력 항목의 source_section이 동일합니다. 다른 섹션 누락 가능성.",
        })

    # Japanese coverage
    if _has_cjk_japanese(resume_text):
        all_sections = career_sections | set(e.get("source_section", "") for e in educations)
        has_jp_section = any(
            "일문" in s or "日" in s or "経" in s or "JP" in s.upper()
            for s in all_sections
        )
        if not has_jp_section:
            issues.append({
                "severity": "warning",
                "message": "이력서에 일문 텍스트가 감지되었으나 일문 source_section이 없습니다.",
            })

    # English coverage
    if _has_significant_english(resume_text):
        has_en_section = any(
            "영문" in s or "EN" in s.upper() or "WORK" in s.upper() or "EXPERIENCE" in s.upper()
            for s in career_sections
        )
        if not has_en_section and len(careers) >= 2:
            issues.append({
                "severity": "info",
                "message": "이력서에 영문 텍스트가 감지되었으나 영문 source_section이 없습니다.",
            })

    # duration_text capture
    if _has_parenthetical_duration(resume_text):
        has_duration = any(c.get("duration_text") for c in careers)
        if not has_duration:
            issues.append({
                "severity": "warning",
                "message": "이력서에 괄호 기간 표기가 있으나 duration_text가 추출되지 않았습니다.",
            })

    return issues


def validate_step1_5(
    grouping: dict,
    total_careers: int,
    total_educations: int,
) -> list[dict]:
    """Validate Step 1.5 grouping quality.

    Checks:
    - Ungrouped ratio
    """
    issues = []

    ungrouped_careers = len(grouping.get("ungrouped_career_indices", []))
    if total_careers > 0 and ungrouped_careers / total_careers > 0.5:
        issues.append({
            "severity": "warning",
            "message": (
                f"경력 항목의 {ungrouped_careers}/{total_careers}건이 미분류입니다. "
                "Step 1 추출 또는 그룹핑 품질을 확인하세요."
            ),
        })

    return issues


def validate_step2(normalized: dict) -> list[dict]:
    """Validate Step 2 normalization quality.

    Checks:
    - Required fields present
    - Date format (YYYY-MM)
    """
    issues = []
    career = normalized.get("career", {})

    if not career.get("company"):
        issues.append({"severity": "error", "message": "company 필드가 비어 있습니다."})

    start = career.get("start_date")
    if not start:
        issues.append({"severity": "error", "message": "start_date 필드가 비어 있습니다."})
    elif not re.match(r"^\d{4}-\d{2}$", start):
        issues.append({"severity": "error", "message": f"start_date 형식 오류: {start} (YYYY-MM 필요)"})

    end = career.get("end_date")
    if end and not re.match(r"^\d{4}-\d{2}$", end):
        issues.append({"severity": "error", "message": f"end_date 형식 오류: {end} (YYYY-MM 필요)"})

    # Flag consistency
    for flag in normalized.get("flags", []):
        if flag.get("severity") and not flag.get("reasoning"):
            issues.append({
                "severity": "warning",
                "message": f"integrity flag에 reasoning이 없습니다: {flag.get('type')}",
            })

    return issues
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
uv run pytest tests/test_integrity_validators.py -v
```
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add candidates/services/integrity/validators.py tests/test_integrity_validators.py
git commit -m "feat: add per-step quality validators for integrity pipeline"
```

---

## Task 3: Step 1 — 충실한 추출

**Files:**
- Create: `candidates/services/integrity/step1_extract.py`
- Test: `tests/test_integrity_step1.py`

- [ ] **Step 1: Step 1 프롬프트 및 호출 테스트 작성**

```python
# tests/test_integrity_step1.py
import pytest
from unittest.mock import patch, MagicMock

from candidates.services.integrity.step1_extract import (
    STEP1_SYSTEM_PROMPT,
    build_step1_prompt,
    extract_raw_data,
)


class TestStep1Prompt:
    def test_system_prompt_has_key_principles(self):
        """프롬프트에 핵심 원칙이 포함되어 있는지"""
        assert "정규화 시스템" in STEP1_SYSTEM_PROMPT  # 출력 용도
        assert "source_section" in STEP1_SYSTEM_PROMPT  # 섹션별 독립 추출
        assert "duration_text" in STEP1_SYSTEM_PROMPT  # 부가 정보 보존
        assert "누락" in STEP1_SYSTEM_PROMPT  # 실패 비용

    def test_build_prompt_includes_text(self):
        prompt = build_step1_prompt("이력서 텍스트 내용")
        assert "이력서 텍스트 내용" in prompt

    def test_build_prompt_includes_schema(self):
        prompt = build_step1_prompt("테스트")
        assert "source_section" in prompt
        assert "duration_text" in prompt


class TestStep1Extract:
    @patch("candidates.services.integrity.step1_extract._call_gemini")
    def test_returns_raw_data_on_success(self, mock_call):
        mock_call.return_value = {
            "name": "테스트",
            "careers": [{"company": "A사", "source_section": "경력란"}],
            "educations": [],
        }
        result = extract_raw_data("이력서 텍스트")
        assert result["name"] == "테스트"
        assert len(result["careers"]) == 1

    @patch("candidates.services.integrity.step1_extract._call_gemini")
    def test_returns_none_on_failure(self, mock_call):
        mock_call.return_value = None
        result = extract_raw_data("이력서 텍스트")
        assert result is None

    @patch("candidates.services.integrity.step1_extract._call_gemini")
    def test_retries_with_feedback(self, mock_call):
        """첫 번째 실패 시 피드백과 함께 재시도"""
        mock_call.side_effect = [
            {"name": "테스트", "careers": [{"company": "A사", "source_section": "경력란"}], "educations": []},
        ]
        result = extract_raw_data(
            "이력서 텍스트",
            feedback="일문 섹션이 누락되었습니다.",
        )
        # feedback가 프롬프트에 포함되는지 확인
        call_args = mock_call.call_args
        assert "일문 섹션" in call_args[0][1]  # prompt에 피드백 포함
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
uv run pytest tests/test_integrity_step1.py -v
```
Expected: FAIL

- [ ] **Step 3: step1_extract.py 구현**

```python
# candidates/services/integrity/step1_extract.py
"""Step 1: Faithful extraction — all sections, all languages, no dedup."""

from __future__ import annotations

import json
import logging

from django.conf import settings
from google import genai

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

STEP1_SYSTEM_PROMPT = """\
당신은 이력서에서 모든 데이터를 충실하게 추출하는 전문가입니다.

당신의 출력은 정규화 시스템의 입력이 됩니다. 정규화 시스템은 여러 섹션의
데이터를 비교하여 정보 간 불일치를 탐지합니다. 따라서 원문의 데이터가 하나라도
누락되면 불일치 탐지가 불가능해집니다.

## 원칙

### 모든 섹션, 모든 언어에서 추출

이력서는 구조화된 테이블, 서술형 문단, 다국어 버전 등 여러 형태의 섹션으로
구성될 수 있습니다. 어떤 형태든, 어떤 언어든, 본인의 경력이나 학력에 대한
구체적 기관명이 포함된 언급이 있으면 추출하세요.

### 섹션별 독립 추출

같은 회사가 세 개의 섹션에 나오면 세 개의 항목을 만드세요.
각 항목에 source_section을 표시하여 출처를 구분하세요.

이렇게 하는 이유: 정규화 시스템이 섹션 간 날짜를 비교해야 하기 때문입니다.
한 섹션에서 1999년이고 다른 섹션에서 1992년이면, 둘 다 있어야 비교가 가능합니다.
하나만 가져오면 불일치를 발견할 수 없습니다.

### 원문 보존

날짜, 기간 표기, 기관명을 원문 그대로 가져오세요. 정규화는 다음 단계의 역할입니다.
유일한 예외: 2자리 연도는 4자리로 변환합니다 ('85 → 1985).
"현재", "Present" 등은 문자열 그대로 유지하세요.

### 부가 정보 보존

경력 항목에 괄호로 기간이 표기되어 있으면 duration_text에 가져오세요.
이 정보는 정규화 시스템이 날짜와 기간의 정합성을 검증하는 데 사용됩니다.
시작~종료일과 기재된 기간이 모순되면 위조 의심 신호이기 때문입니다.

## 추출 규칙
1. 이력서에 나오는 순서대로 가져오세요.
2. 이름은 한국어를 우선하되, 영문명도 별도로 가져오세요.
3. JSON만 출력하세요.
"""

STEP1_SCHEMA = """{
  "name": "string",
  "name_en": "string | null",
  "birth_year": "integer | null",
  "gender": "string | null",
  "email": "string | null",
  "phone": "string | null",
  "address": "string | null",
  "total_experience_years": "integer | null",
  "total_experience_text": "string | null (원문 그대로)",
  "resume_reference_date": "string | null",
  "careers": [
    {
      "company": "string (원문 그대로)",
      "position": "string | null",
      "department": "string | null",
      "start_date": "string | null (원문 그대로)",
      "end_date": "string | null (원문 그대로)",
      "duration_text": "string | null (괄호 안 기간 표기 원문 그대로)",
      "is_current": "boolean",
      "duties": "string | null",
      "source_section": "string (출처 섹션)"
    }
  ],
  "educations": [
    {
      "institution": "string (원문 그대로)",
      "degree": "string | null",
      "major": "string | null",
      "start_year": "integer | null",
      "end_year": "integer | null",
      "is_abroad": "boolean",
      "status": "string | null (졸업/중퇴/수료 등 원문 그대로)",
      "source_section": "string (출처 섹션)"
    }
  ],
  "certifications": [
    {"name": "string", "issuer": "string | null", "acquired_date": "string | null"}
  ],
  "language_skills": [
    {"language": "string", "test_name": "string | null", "score": "string | null"}
  ]
}"""


def _get_client() -> genai.Client:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


def _call_gemini(system: str, prompt: str, max_tokens: int = 6000) -> dict | None:
    """Call Gemini and parse JSON response."""
    client = _get_client()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                temperature=0.2,
            ),
        )
        raw = response.text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        result = json.loads(raw)
        if not isinstance(result, dict):
            return None
        return result
    except Exception:
        logger.warning("Gemini call failed", exc_info=True)
        return None


def build_step1_prompt(resume_text: str, feedback: str | None = None) -> str:
    """Build Step 1 extraction prompt."""
    feedback_block = ""
    if feedback:
        feedback_block = (
            f"\n## 이전 추출에 대한 피드백\n{feedback}\n"
            "위 피드백을 반영하여 다시 추출하세요.\n"
        )
    return (
        f"이력서의 모든 데이터를 추출하세요.{feedback_block}\n\n"
        f"## 스키마\n```\n{STEP1_SCHEMA}\n```\n\n"
        f"## 이력서\n```\n{resume_text}\n```\n\n"
        "JSON만 출력하세요."
    )


def extract_raw_data(
    resume_text: str,
    *,
    feedback: str | None = None,
    max_retries: int = 2,
) -> dict | None:
    """Step 1: Extract all data faithfully from resume text.

    Args:
        resume_text: Preprocessed resume text.
        feedback: Optional feedback from previous extraction attempt.
        max_retries: Maximum retry attempts.

    Returns:
        Raw extracted data dict, or None if extraction fails.
    """
    prompt = build_step1_prompt(resume_text, feedback=feedback)

    for attempt in range(max_retries):
        result = _call_gemini(STEP1_SYSTEM_PROMPT, prompt)
        if result and "name" in result:
            return result
        logger.warning("Step 1 extraction attempt %d/%d failed", attempt + 1, max_retries)

    return None
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
uv run pytest tests/test_integrity_step1.py -v
```
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add candidates/services/integrity/step1_extract.py tests/test_integrity_step1.py
git commit -m "feat: add Step 1 faithful extraction module"
```

---

## Task 4: Step 1.5 — 시멘틱 그룹핑

**Files:**
- Create: `candidates/services/integrity/step1_5_grouping.py`
- Test: `tests/test_integrity_step1_5.py`

- [ ] **Step 1: 그룹핑 테스트 작성**

```python
# tests/test_integrity_step1_5.py
import pytest
from unittest.mock import patch

from candidates.services.integrity.step1_5_grouping import (
    GROUPING_SYSTEM_PROMPT,
    group_raw_data,
)


class TestGroupingPrompt:
    def test_system_prompt_has_key_principles(self):
        assert "병합" in GROUPING_SYSTEM_PROMPT  # 병합 금지 원칙
        assert "미분류" in GROUPING_SYSTEM_PROMPT or "ungrouped" in GROUPING_SYSTEM_PROMPT


class TestGroupRawData:
    @patch("candidates.services.integrity.step1_5_grouping._call_gemini")
    def test_groups_same_company_different_sections(self, mock_call):
        mock_call.return_value = {
            "career_groups": [
                {"group_id": "g1", "canonical_name": "A사", "relationship": "same_company", "entry_indices": [0, 1]},
            ],
            "education_groups": [],
            "ungrouped_career_indices": [],
            "ungrouped_education_indices": [],
        }
        raw_data = {
            "careers": [
                {"company": "A사", "source_section": "국문"},
                {"company": "A社", "source_section": "일문"},
            ],
            "educations": [],
        }
        result = group_raw_data(raw_data)
        assert len(result["career_groups"]) == 1
        assert result["career_groups"][0]["entry_indices"] == [0, 1]

    @patch("candidates.services.integrity.step1_5_grouping._call_gemini")
    def test_ungrouped_items_preserved(self, mock_call):
        mock_call.return_value = {
            "career_groups": [],
            "education_groups": [],
            "ungrouped_career_indices": [0],
            "ungrouped_education_indices": [],
        }
        raw_data = {
            "careers": [{"company": "Unknown Corp", "source_section": "영문"}],
            "educations": [],
        }
        result = group_raw_data(raw_data)
        assert result["ungrouped_career_indices"] == [0]
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
uv run pytest tests/test_integrity_step1_5.py -v
```

- [ ] **Step 3: step1_5_grouping.py 구현**

```python
# candidates/services/integrity/step1_5_grouping.py
"""Step 1.5: Semantic grouping of raw extracted data."""

from __future__ import annotations

import json
import logging

from candidates.services.integrity.step1_extract import _call_gemini

logger = logging.getLogger(__name__)

GROUPING_SYSTEM_PROMPT = """\
당신은 이력서 데이터의 시멘틱 그룹핑 전문가입니다.

Step 1에서 이력서의 모든 섹션, 모든 언어의 데이터가 독립 추출되었습니다.
같은 회사/학교가 여러 항목으로 나올 수 있습니다.

당신의 역할은 같은 회사/학교를 가리키는 항목들을 그룹으로 묶는 것입니다.
병합은 하지 마세요. 누가 누구와 같은 항목인지만 판별하세요.

이렇게 하는 이유: 다음 단계에서 각 그룹을 독립적으로 정규화합니다.
그룹핑이 정확해야 정규화와 위조 탐지가 올바르게 작동합니다.

## 그룹핑 원칙

- 다른 언어로 표기된 같은 기관은 같은 그룹입니다.
- 한 회사의 전체 재직 기간과 세부 직무 기간은 같은 그룹입니다.
- 계열사/그룹사 관계는 affiliated_group으로 표시합니다.
- 확실하지 않으면 그룹에 넣지 마세요. 잘못 묶는 것보다 안 묶는 것이 안전합니다.
  잘못 묶으면 다음 단계에서 잘못된 통합이 발생하지만,
  안 묶으면 개별 처리되어 최종 결과에 영향이 작습니다.

## 출력
JSON만 출력하세요.
"""

GROUPING_SCHEMA = """{
  "career_groups": [
    {
      "group_id": "string",
      "canonical_name": "string (대표 회사명, 한국어 우선)",
      "relationship": "string (same_company | parent_with_sub_periods | affiliated_group)",
      "entry_indices": [0, 1, 2]
    }
  ],
  "education_groups": [
    {
      "group_id": "string",
      "canonical_name": "string",
      "entry_indices": [0, 1]
    }
  ],
  "ungrouped_career_indices": [],
  "ungrouped_education_indices": []
}"""


def group_raw_data(
    raw_data: dict,
    *,
    feedback: str | None = None,
) -> dict | None:
    """Step 1.5: Group raw items by semantic similarity.

    Args:
        raw_data: Step 1 output.
        feedback: Optional feedback from previous grouping attempt.

    Returns:
        Grouping result dict, or None on failure.
    """
    careers_summary = []
    for i, c in enumerate(raw_data.get("careers", [])):
        careers_summary.append(
            f"[{i}] {c.get('company', '?')} | "
            f"{c.get('start_date', '?')}~{c.get('end_date', '?')} | "
            f"source: {c.get('source_section', '?')}"
        )

    edus_summary = []
    for i, e in enumerate(raw_data.get("educations", [])):
        edus_summary.append(
            f"[{i}] {e.get('institution', '?')} | "
            f"{e.get('degree', '')} | "
            f"{e.get('start_year', '?')}~{e.get('end_year', '?')} | "
            f"source: {e.get('source_section', '?')}"
        )

    feedback_block = ""
    if feedback:
        feedback_block = f"\n## 이전 그룹핑에 대한 피드백\n{feedback}\n"

    prompt = (
        f"아래 항목들을 동일 회사/학교 단위로 그룹핑하세요.{feedback_block}\n\n"
        f"## 스키마\n```\n{GROUPING_SCHEMA}\n```\n\n"
        f"## 경력 항목\n{chr(10).join(careers_summary)}\n\n"
        f"## 학력 항목\n{chr(10).join(edus_summary)}\n\n"
        "JSON만 출력하세요."
    )

    result = _call_gemini(GROUPING_SYSTEM_PROMPT, prompt, max_tokens=2000)
    if not result or "career_groups" not in result:
        logger.warning("Step 1.5 grouping failed")
        return None

    return result
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
uv run pytest tests/test_integrity_step1_5.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add candidates/services/integrity/step1_5_grouping.py tests/test_integrity_step1_5.py
git commit -m "feat: add Step 1.5 semantic grouping module"
```

---

## Task 5: Step 2 — 그룹별 정규화 + 위조 탐지

**Files:**
- Create: `candidates/services/integrity/step2_normalize.py`
- Test: `tests/test_integrity_step2.py`

- [ ] **Step 1: Step 2 테스트 작성**

```python
# tests/test_integrity_step2.py
import pytest
from unittest.mock import patch

from candidates.services.integrity.step2_normalize import (
    STEP2_SYSTEM_PROMPT,
    normalize_career_group,
    normalize_education_group,
)


class TestStep2Prompt:
    def test_system_prompt_has_key_principles(self):
        assert "정규화의 부산물" in STEP2_SYSTEM_PROMPT or "부산물" in STEP2_SYSTEM_PROMPT
        assert "거짓 경보" in STEP2_SYSTEM_PROMPT
        assert "채용 담당자" in STEP2_SYSTEM_PROMPT


class TestNormalizeCareerGroup:
    @patch("candidates.services.integrity.step2_normalize._call_gemini")
    def test_single_entry_passthrough(self, mock_call):
        """항목이 1개뿐인 그룹은 정규화만 하고 flag 없음"""
        mock_call.return_value = {
            "career": {
                "company": "A사",
                "start_date": "2020-01",
                "end_date": "2022-06",
                "is_current": False,
            },
            "flags": [],
        }
        entries = [{"company": "A사", "start_date": "2020.01", "end_date": "2022.06", "source_section": "경력란"}]
        result = normalize_career_group(entries, "A사")
        assert result["career"]["start_date"] == "2020-01"
        assert result["flags"] == []

    @patch("candidates.services.integrity.step2_normalize._call_gemini")
    def test_date_conflict_detected(self, mock_call):
        """날짜 충돌이 있는 그룹에서 DATE_CONFLICT flag 생성"""
        mock_call.return_value = {
            "career": {
                "company": "카모스테크",
                "start_date": "1999-02",
                "end_date": "2003-07",
                "is_current": False,
            },
            "flags": [{
                "type": "DATE_CONFLICT",
                "severity": "RED",
                "field": "careers.start_date",
                "detail": "시작일 7년 차이",
                "chosen": "1999-02",
                "alternative": "1992-02",
                "reasoning": "다수의 섹션이 1999년, 1개 섹션만 1992년",
            }],
        }
        entries = [
            {"company": "카모스테크", "start_date": "1999.2", "source_section": "국문"},
            {"company": "カモステック", "start_date": "1992.2", "source_section": "일문"},
        ]
        result = normalize_career_group(entries, "카모스테크")
        assert len(result["flags"]) == 1
        assert result["flags"][0]["type"] == "DATE_CONFLICT"


class TestNormalizeEducationGroup:
    @patch("candidates.services.integrity.step2_normalize._call_gemini")
    def test_short_degree_detected(self, mock_call):
        mock_call.return_value = {
            "educations": [{"institution": "X대", "degree": "학사", "start_year": 2020, "end_year": 2022}],
            "flags": [{
                "type": "SHORT_DEGREE",
                "severity": "YELLOW",
                "field": "educations",
                "detail": "4년제 2년 재학",
                "chosen": None,
                "alternative": None,
                "reasoning": "편입 가능성 확인 필요",
            }],
        }
        entries = [{"institution": "X대", "degree": "학사", "start_year": 2020, "end_year": 2022, "source_section": "학력란"}]
        result = normalize_education_group(entries)
        assert len(result["flags"]) == 1
        assert result["flags"][0]["type"] == "SHORT_DEGREE"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
uv run pytest tests/test_integrity_step2.py -v
```

- [ ] **Step 3: step2_normalize.py 구현**

```python
# candidates/services/integrity/step2_normalize.py
"""Step 2: Per-group normalization + fraud detection."""

from __future__ import annotations

import json
import logging

from candidates.services.integrity.step1_extract import _call_gemini

logger = logging.getLogger(__name__)

STEP2_SYSTEM_PROMPT = """\
당신은 이력서 데이터를 정규화하는 전문가입니다.

같은 회사/학교의 여러 항목이 입력됩니다.
이것들을 하나의 정규화된 레코드로 통합하세요.

당신의 출력은 두 곳에서 사용됩니다:
- 정규화된 데이터 → 후보자 DB에 저장되어 검색·열람에 사용
- integrity_flags → 채용 담당자에게 검수 알림으로 표시

## 정규화

이력서의 서로 다른 섹션은 서로 다른 시점에 작성되었을 수 있습니다.
따라서 날짜가 충돌하면 가장 확정적인 정보를 선택하세요.
- 확정된 날짜가 "현재"보다 신뢰도가 높습니다.
- 전체 기간과 세부 기간이 있으면 전체 기간이 최종 정보일 가능성이 높습니다.

start_date, end_date는 YYYY-MM 형식으로 통일하세요.
현재 재직 중이면 end_date는 null, is_current는 true.

## 위조 탐지

위조 탐지는 정규화의 부산물입니다.
통합이 매끄러우면 integrity_flags는 빈 배열입니다.
통합 과정에서 해소할 수 없는 모순이 발견되면 기록하세요.

거짓 경보는 채용 담당자의 시스템 신뢰를 떨어뜨립니다.
담당자가 RED를 보면 해당 후보자를 즉시 재검토하고,
YELLOW를 보면 면접 시 확인 사항으로 기록합니다.

타이핑 실수나 월 계산 방식 차이로 설명 가능한 작은 차이는
정규화만 하고 보고하지 마세요.

duration_text와 날짜 계산의 모순은 같은 항목 내 자기모순이므로
정규화로 해소할 수 없습니다 — 보고 대상입니다.

## 출력
JSON만 출력하세요.
"""

CAREER_OUTPUT_SCHEMA = """{
  "career": {
    "company": "string",
    "company_en": "string | null",
    "position": "string | null",
    "department": "string | null",
    "start_date": "string (YYYY-MM)",
    "end_date": "string | null (YYYY-MM)",
    "is_current": "boolean",
    "duties": "string | null",
    "achievements": "string | null"
  },
  "flags": [
    {
      "type": "string (DATE_CONFLICT)",
      "severity": "string (RED | YELLOW)",
      "field": "string",
      "detail": "string",
      "chosen": "string | null",
      "alternative": "string | null",
      "reasoning": "string"
    }
  ]
}"""

EDUCATION_OUTPUT_SCHEMA = """{
  "educations": [
    {
      "institution": "string",
      "degree": "string | null",
      "major": "string | null",
      "start_year": "integer | null",
      "end_year": "integer | null",
      "is_abroad": "boolean"
    }
  ],
  "flags": [
    {
      "type": "string (SHORT_DEGREE)",
      "severity": "string (RED | YELLOW)",
      "field": "string",
      "detail": "string",
      "chosen": "string | null",
      "alternative": "string | null",
      "reasoning": "string"
    }
  ]
}"""

EDUCATION_EXTRA_PROMPT = """\

## 학력 위조 탐지 원칙

본인이 솔직하게 밝힌 학력 사항은 위조가 아닙니다.
같은 분야의 다른 학교가 있으면 편입 가능성이 있습니다.
위 어디에도 해당하지 않으면서 정규 학위를 수업연한보다
현저히 짧은 기간에 취득한 것은 보고 대상입니다.
"""


def normalize_career_group(
    entries: list[dict],
    canonical_name: str,
    *,
    feedback: str | None = None,
) -> dict | None:
    """Normalize a career group into one record + flags.

    Args:
        entries: Raw career entries from Step 1 (same company group).
        canonical_name: Group canonical name from Step 1.5.
        feedback: Optional feedback from previous normalization attempt.
    """
    entries_json = json.dumps(entries, ensure_ascii=False, indent=2)

    feedback_block = ""
    if feedback:
        feedback_block = f"\n## 피드백\n{feedback}\n"

    prompt = (
        f"아래 '{canonical_name}'의 {len(entries)}개 항목을 하나로 통합하세요.{feedback_block}\n\n"
        f"## 출력 스키마\n```\n{CAREER_OUTPUT_SCHEMA}\n```\n\n"
        f"## 입력 항목\n```json\n{entries_json}\n```\n\n"
        "JSON만 출력하세요."
    )

    result = _call_gemini(STEP2_SYSTEM_PROMPT, prompt, max_tokens=2000)
    if not result or "career" not in result:
        logger.warning("Step 2 career normalization failed for %s", canonical_name)
        return None

    return result


def normalize_education_group(
    entries: list[dict],
    *,
    feedback: str | None = None,
) -> dict | None:
    """Normalize education entries + detect SHORT_DEGREE.

    Args:
        entries: All raw education entries from Step 1.
        feedback: Optional feedback from previous attempt.
    """
    entries_json = json.dumps(entries, ensure_ascii=False, indent=2)

    feedback_block = ""
    if feedback:
        feedback_block = f"\n## 피드백\n{feedback}\n"

    prompt = (
        f"아래 학력 항목들을 정규화하고 위조 의심을 탐지하세요.{feedback_block}\n\n"
        f"## 출력 스키마\n```\n{EDUCATION_OUTPUT_SCHEMA}\n```\n\n"
        f"{EDUCATION_EXTRA_PROMPT}\n"
        f"## 입력 항목\n```json\n{entries_json}\n```\n\n"
        "JSON만 출력하세요."
    )

    result = _call_gemini(
        STEP2_SYSTEM_PROMPT + EDUCATION_EXTRA_PROMPT,
        prompt,
        max_tokens=2000,
    )
    if not result or "educations" not in result:
        logger.warning("Step 2 education normalization failed")
        return None

    return result
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
uv run pytest tests/test_integrity_step2.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add candidates/services/integrity/step2_normalize.py tests/test_integrity_step2.py
git commit -m "feat: add Step 2 per-group normalization with fraud detection"
```

---

## Task 6: 파이프라인 오케스트레이션

**Files:**
- Create: `candidates/services/integrity/pipeline.py`
- Test: `tests/test_integrity_pipeline.py`

- [ ] **Step 1: 오케스트레이션 테스트 작성**

```python
# tests/test_integrity_pipeline.py
import pytest
from unittest.mock import patch, MagicMock

from candidates.services.integrity.pipeline import run_integrity_pipeline


class TestPipeline:
    @patch("candidates.services.integrity.pipeline.check_period_overlaps")
    @patch("candidates.services.integrity.pipeline.normalize_education_group")
    @patch("candidates.services.integrity.pipeline.normalize_career_group")
    @patch("candidates.services.integrity.pipeline.group_raw_data")
    @patch("candidates.services.integrity.pipeline.extract_raw_data")
    def test_full_pipeline_success(
        self, mock_step1, mock_step15, mock_step2_career, mock_step2_edu, mock_step3
    ):
        mock_step1.return_value = {
            "name": "테스트",
            "name_en": None,
            "birth_year": 1990,
            "careers": [{"company": "A사", "start_date": "2020.01", "end_date": "2022.06", "source_section": "경력란"}],
            "educations": [{"institution": "서울대", "degree": "학사", "start_year": 2010, "end_year": 2014, "source_section": "학력란"}],
        }
        mock_step15.return_value = {
            "career_groups": [{"group_id": "g1", "canonical_name": "A사", "relationship": "same_company", "entry_indices": [0]}],
            "education_groups": [],
            "ungrouped_career_indices": [],
            "ungrouped_education_indices": [],
        }
        mock_step2_career.return_value = {
            "career": {"company": "A사", "start_date": "2020-01", "end_date": "2022-06", "is_current": False},
            "flags": [],
        }
        mock_step2_edu.return_value = {
            "educations": [{"institution": "서울대", "degree": "학사", "start_year": 2010, "end_year": 2014, "is_abroad": False}],
            "flags": [],
        }
        mock_step3.return_value = []

        result = run_integrity_pipeline("이력서 텍스트")

        assert result is not None
        assert result["name"] == "테스트"
        assert len(result["careers"]) == 1
        assert len(result["educations"]) == 1
        assert result["integrity_flags"] == []

    @patch("candidates.services.integrity.pipeline.extract_raw_data")
    def test_step1_failure_returns_none(self, mock_step1):
        mock_step1.return_value = None
        result = run_integrity_pipeline("이력서 텍스트")
        assert result is None
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
uv run pytest tests/test_integrity_pipeline.py -v
```

- [ ] **Step 3: pipeline.py 구현**

```python
# candidates/services/integrity/pipeline.py
"""Integrity pipeline orchestration: Step 1 → 1.5 → 2 (parallel) → 3."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from candidates.services.integrity.step1_extract import extract_raw_data
from candidates.services.integrity.step1_5_grouping import group_raw_data
from candidates.services.integrity.step2_normalize import (
    normalize_career_group,
    normalize_education_group,
)
from candidates.services.integrity.step3_overlap import check_period_overlaps
from candidates.services.integrity.validators import (
    validate_step1,
    validate_step1_5,
    validate_step2,
)

logger = logging.getLogger(__name__)


def run_integrity_pipeline(
    resume_text: str,
    *,
    file_reference_date: str | None = None,
) -> dict | None:
    """Run the full integrity pipeline.

    Returns:
        {
            "name": str,
            "name_en": str | None,
            "birth_year": int | None,
            ...
            "careers": [...],
            "educations": [...],
            "integrity_flags": [...],
            "field_confidences": {...},
            "pipeline_meta": {
                "step1_items": int,
                "groups": int,
                "retries": int,
            },
        }
        or None on failure.
    """
    retries = 0

    # ── Step 1: Faithful extraction ──
    raw_data = extract_raw_data(resume_text)
    if raw_data is None:
        logger.error("Step 1 extraction failed")
        return None

    # Step 1 validation
    step1_issues = validate_step1(raw_data, resume_text)
    has_warnings = any(i["severity"] == "warning" for i in step1_issues)
    if has_warnings:
        feedback = ". ".join(i["message"] for i in step1_issues if i["severity"] == "warning")
        logger.info("Step 1 validation issues, retrying: %s", feedback)
        raw_data_retry = extract_raw_data(resume_text, feedback=feedback)
        if raw_data_retry and "name" in raw_data_retry:
            raw_data = raw_data_retry
            retries += 1

    careers_raw = raw_data.get("careers", [])
    educations_raw = raw_data.get("educations", [])

    # ── Step 1.5: Semantic grouping ──
    grouping = group_raw_data(raw_data)
    if grouping is None:
        logger.error("Step 1.5 grouping failed")
        return None

    # Step 1.5 validation
    step15_issues = validate_step1_5(grouping, len(careers_raw), len(educations_raw))
    if any(i["severity"] == "warning" for i in step15_issues):
        feedback = ". ".join(i["message"] for i in step15_issues if i["severity"] == "warning")
        grouping_retry = group_raw_data(raw_data, feedback=feedback)
        if grouping_retry:
            grouping = grouping_retry
            retries += 1

    # ── Step 2: Parallel normalization + fraud detection ──
    career_groups = grouping.get("career_groups", [])
    ungrouped_careers = grouping.get("ungrouped_career_indices", [])

    all_flags = []
    normalized_careers = []

    def process_career_group(group):
        entries = [careers_raw[i] for i in group["entry_indices"] if i < len(careers_raw)]
        result = normalize_career_group(entries, group["canonical_name"])
        if result is None:
            return None
        # Validate
        issues = validate_step2(result)
        if any(i["severity"] == "error" for i in issues):
            feedback = ". ".join(i["message"] for i in issues)
            result = normalize_career_group(entries, group["canonical_name"], feedback=feedback)
        return result

    # Parallel execution for career groups
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(process_career_group, group): group
            for group in career_groups
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                career = result["career"]
                career["order"] = len(normalized_careers)
                normalized_careers.append(career)
                all_flags.extend(result.get("flags", []))

    # Handle ungrouped careers (single-entry groups)
    for idx in ungrouped_careers:
        if idx < len(careers_raw):
            entry = careers_raw[idx]
            result = normalize_career_group([entry], entry.get("company", ""))
            if result:
                career = result["career"]
                career["order"] = len(normalized_careers)
                normalized_careers.append(career)
                all_flags.extend(result.get("flags", []))

    # Sort by order (most recent first)
    normalized_careers.sort(key=lambda c: c.get("start_date", ""), reverse=True)
    for i, c in enumerate(normalized_careers):
        c["order"] = i

    # Education normalization
    edu_result = normalize_education_group(educations_raw)
    normalized_educations = []
    if edu_result:
        normalized_educations = edu_result.get("educations", [])
        all_flags.extend(edu_result.get("flags", []))

    # ── Step 3: Cross-group overlap analysis ──
    affiliated_groups = [g for g in career_groups if g.get("relationship") == "affiliated_group"]
    overlap_flags = check_period_overlaps(normalized_careers, affiliated_groups=affiliated_groups)
    all_flags.extend(overlap_flags)

    # ── Assemble final result ──
    return {
        "name": raw_data.get("name"),
        "name_en": raw_data.get("name_en"),
        "birth_year": raw_data.get("birth_year"),
        "gender": raw_data.get("gender"),
        "email": raw_data.get("email"),
        "phone": raw_data.get("phone"),
        "address": raw_data.get("address"),
        "total_experience_years": raw_data.get("total_experience_years"),
        "resume_reference_date": raw_data.get("resume_reference_date"),
        "careers": normalized_careers,
        "educations": normalized_educations,
        "certifications": raw_data.get("certifications", []),
        "language_skills": raw_data.get("language_skills", []),
        "integrity_flags": all_flags,
        "field_confidences": {},
        "pipeline_meta": {
            "step1_items": len(careers_raw) + len(educations_raw),
            "groups": len(career_groups),
            "retries": retries,
        },
    }
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
uv run pytest tests/test_integrity_pipeline.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add candidates/services/integrity/pipeline.py tests/test_integrity_pipeline.py
git commit -m "feat: add integrity pipeline orchestration with parallel execution"
```

---

## Task 7: 기존 파이프라인 연결

**Files:**
- Modify: `candidates/services/retry_pipeline.py`
- Modify: `candidates/management/commands/import_resumes.py`
- Modify: `candidates/models.py`

- [ ] **Step 1: retry_pipeline.py에 새 파이프라인 옵션 추가 테스트**

```python
# tests/test_retry_pipeline.py 에 추가
from unittest.mock import patch

@patch("candidates.services.retry_pipeline.run_integrity_pipeline")
def test_integrity_pipeline_integration(mock_pipeline):
    mock_pipeline.return_value = {
        "name": "테스트",
        "careers": [],
        "educations": [],
        "integrity_flags": [],
        "pipeline_meta": {"step1_items": 0, "groups": 0, "retries": 0},
    }
    from candidates.services.retry_pipeline import run_extraction_with_retry
    result = run_extraction_with_retry(
        raw_text="테스트",
        file_path="test.doc",
        category="테스트",
        filename_meta={},
        use_integrity_pipeline=True,
    )
    assert result["extracted"]["name"] == "테스트"
```

- [ ] **Step 2: retry_pipeline.py 수정**

```python
# candidates/services/retry_pipeline.py 에 추가
# 기존 함수 시그니처에 use_integrity_pipeline 파라미터 추가

def run_extraction_with_retry(
    raw_text: str,
    file_path: str,
    category: str,
    filename_meta: dict,
    file_reference_date: str | None = None,
    *,
    use_integrity_pipeline: bool = False,
) -> dict:
    if use_integrity_pipeline:
        from candidates.services.integrity.pipeline import run_integrity_pipeline
        result = run_integrity_pipeline(raw_text, file_reference_date=file_reference_date)
        if result is None:
            return {
                "extracted": None,
                "diagnosis": {"verdict": "fail", "issues": [], "field_scores": {}, "overall_score": 0.0},
                "attempts": 1,
                "retry_action": "human_review",
                "raw_text_used": raw_text,
            }
        return {
            "extracted": result,
            "diagnosis": {
                "verdict": "pass",
                "issues": [],
                "field_scores": result.get("field_confidences", {}),
                "overall_score": 0.9,
            },
            "attempts": 1 + result.get("pipeline_meta", {}).get("retries", 0),
            "retry_action": "none",
            "raw_text_used": raw_text,
            "integrity_flags": result.get("integrity_flags", []),
        }

    # 기존 로직 유지
    extracted = extract_candidate_data(raw_text, file_reference_date=file_reference_date)
    # ... (기존 코드)
```

- [ ] **Step 3: DiscrepancyReport에 integrity_flags 저장 로직 추가**

`candidates/models.py`의 `DiscrepancyReport.notice_items` 프로퍼티에서
integrity_flags의 `summary` 필드를 추가:

```python
# DiscrepancyReport.notice_items에서 integrity_flags도 처리
@property
def notice_items(self) -> list[dict]:
    items = []
    for alert in self.alerts:
        if not isinstance(alert, dict) or not alert.get("detail"):
            continue
        severity = alert.get("severity", "BLUE")
        detail = alert["detail"]
        summary = alert.get("summary") or (detail[:30] + "…" if len(detail) > 30 else detail)
        items.append({
            "severity": severity,
            "label": _severity_label(severity),
            "detail": detail,
            "summary": summary,
            "type": alert.get("type", ""),
        })
    return items
```

- [ ] **Step 4: 전체 테스트 실행**

```bash
uv run pytest tests/ -v
```

- [ ] **Step 5: 커밋**

```bash
git add candidates/services/retry_pipeline.py candidates/models.py
git commit -m "feat: integrate integrity pipeline with existing extraction flow"
```

---

## Task 8: E2E 통합 테스트

**Files:**
- Create: `tests/test_integrity_e2e.py`

- [ ] **Step 1: E2E 테스트 작성 (DB 이용)**

```python
# tests/test_integrity_e2e.py
import pytest
from candidates.services.integrity.pipeline import run_integrity_pipeline
from candidates.models import Resume


@pytest.mark.django_db
class TestIntegrityE2E:
    """E2E tests using actual resume texts from DB.

    These tests call the real Gemini API — mark as slow/integration.
    """

    @pytest.fixture
    def resume_text(self):
        """Get a resume text for testing. Uses first available."""
        resume = Resume.objects.exclude(raw_text="").exclude(raw_text__isnull=True).first()
        if resume is None:
            pytest.skip("No resume with text available")
        return resume.raw_text

    @pytest.mark.slow
    def test_pipeline_produces_valid_output(self, resume_text):
        result = run_integrity_pipeline(resume_text)
        assert result is not None
        assert "name" in result
        assert "careers" in result
        assert "educations" in result
        assert "integrity_flags" in result
        assert isinstance(result["integrity_flags"], list)

    @pytest.mark.slow
    def test_pipeline_careers_have_required_fields(self, resume_text):
        result = run_integrity_pipeline(resume_text)
        assert result is not None
        for career in result["careers"]:
            assert "company" in career
            assert "start_date" in career
            assert "order" in career

    @pytest.mark.slow
    def test_pipeline_flags_have_required_fields(self, resume_text):
        result = run_integrity_pipeline(resume_text)
        assert result is not None
        for flag in result["integrity_flags"]:
            assert "type" in flag
            assert "severity" in flag
            assert flag["severity"] in ("RED", "YELLOW")
            assert "detail" in flag
            assert "reasoning" in flag
```

- [ ] **Step 2: 빠른 테스트 실행 (mock 기반)**

```bash
uv run pytest tests/test_integrity_pipeline.py tests/test_integrity_step1.py tests/test_integrity_step1_5.py tests/test_integrity_step2.py tests/test_integrity_step3.py tests/test_integrity_validators.py -v
```
Expected: ALL PASS

- [ ] **Step 3: E2E 테스트 실행 (실제 API, 선택적)**

```bash
uv run pytest tests/test_integrity_e2e.py -v -m slow
```

- [ ] **Step 4: 커밋**

```bash
git add tests/test_integrity_e2e.py
git commit -m "test: add E2E integration tests for integrity pipeline"
```
