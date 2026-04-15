# Self-Evolving Parsing Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 파싱 결과를 Codex CLI로 교차 검증하고, 실패 시 원인 분류 → 자동 재시도 → 패턴 축적하는 자체 진화 루프 구축

**Architecture:** Claude가 추출한 JSON을 Codex CLI가 원본 텍스트와 비교하여 교차 검증. 실패 원인을 text_extraction/llm_parsing/ambiguous_source로 분류하고, 텍스트 재추출 또는 프롬프트 보강 후 최대 3회 재시도. 검증을 통과한 교정 사례는 규칙 엔진(JSON) 또는 few-shot 예시 DB(ParseExample 모델)에 축적되어 다음 파싱에 자동 반영.

**Tech Stack:** Django ORM, Codex CLI (codex-cli 0.117.0), Claude CLI, python-docx, LibreOffice

---

## File Structure

| File | Responsibility |
|------|----------------|
| `candidates/services/codex_validation.py` | **신규**. Codex CLI 호출, 교차 검증 로직, 진단 결과 파싱 |
| `candidates/services/retry_pipeline.py` | **신규**. 재시도 오케스트레이터: 원인별 분기, 재추출/재파싱 |
| `candidates/services/fewshot_store.py` | **신규**. ParseExample DB 조회, 프롬프트에 few-shot 삽입 |
| `candidates/services/extraction_rules.json` | **신규**. 규칙 엔진 저장소 (JSON) |
| `candidates/services/llm_extraction.py` | **수정**. few-shot 예시 삽입 지원 |
| `candidates/services/text_extraction.py` | **수정**. LibreOffice 재추출 함수 분리 (retry에서 호출용) |
| `candidates/services/validation.py` | **수정**. codex_validation 결과 통합 |
| `candidates/models.py` | **수정**. ParseExample, ValidationDiagnosis 모델 추가 |
| `candidates/management/commands/import_resumes.py` | **수정**. 새 파이프라인 호출 |
| `tests/test_codex_validation.py` | **신규**. 교차 검증 테스트 |
| `tests/test_retry_pipeline.py` | **신규**. 재시도 로직 테스트 |
| `tests/test_fewshot_store.py` | **신규**. few-shot 조회/삽입 테스트 |

---

## Task 1: ParseExample & ValidationDiagnosis 모델 추가

**Files:**
- Modify: `candidates/models.py`
- Create: `candidates/migrations/` (자동 생성)
- Test: `tests/test_validation.py`

- [ ] **Step 1: Write the failing test for ParseExample model**

```python
# tests/test_validation.py — 기존 파일에 추가
import pytest
from candidates.models import ParseExample

@pytest.mark.django_db
def test_parse_example_create():
    ex = ParseExample.objects.create(
        category="Plant",
        resume_pattern="영문+국문 혼합, 텍스트박스 헤더",
        input_excerpt="Daehan Solution LLC / President...",
        correct_output={"company": "대한솔루션", "start_date": "Dec. 2016"},
    )
    assert ex.category == "Plant"
    assert ex.is_active is True
    assert ex.correct_output["company"] == "대한솔루션"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_validation.py::test_parse_example_create -v`
Expected: FAIL with "cannot import name 'ParseExample'"

- [ ] **Step 3: Add ParseExample model to candidates/models.py**

```python
class ParseExample(BaseModel):
    """Few-shot 예시 저장소. 교정된 사례를 축적하여 다음 파싱 프롬프트에 삽입."""

    category = models.CharField(max_length=50, db_index=True)
    resume_pattern = models.CharField(max_length=200)
    input_excerpt = models.TextField(help_text="원본 텍스트 발췌 (500자 이내)")
    correct_output = models.JSONField(help_text="교정된 추출 JSON 발췌")
    source_candidate = models.ForeignKey(
        "Candidate", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="parse_examples",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "parse_examples"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.category}] {self.resume_pattern[:50]}"
```

- [ ] **Step 4: Add ValidationDiagnosis model to candidates/models.py**

```python
class ValidationDiagnosis(BaseModel):
    """Codex 교차 검증 진단 결과. 재시도 이력 추적."""

    candidate = models.ForeignKey(
        "Candidate", on_delete=models.CASCADE, related_name="diagnoses",
    )
    resume = models.ForeignKey(
        "Resume", on_delete=models.CASCADE, related_name="diagnoses",
    )
    attempt_number = models.PositiveIntegerField(default=1)
    verdict = models.CharField(max_length=10)  # pass / fail
    overall_score = models.FloatField()
    issues = models.JSONField(default=list)
    field_scores = models.JSONField(default=dict)
    retry_action = models.CharField(max_length=30, blank=True)  # re_extract / re_parse / human_review / none

    class Meta:
        db_table = "validation_diagnoses"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Attempt {self.attempt_number}: {self.verdict} ({self.overall_score})"
```

- [ ] **Step 5: Generate and run migration**

Run: `uv run python manage.py makemigrations candidates && uv run python manage.py migrate`
Expected: Migration created and applied

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_validation.py::test_parse_example_create -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add candidates/models.py candidates/migrations/ tests/test_validation.py
git commit -m "feat: add ParseExample and ValidationDiagnosis models"
```

---

## Task 2: Codex CLI 교차 검증 서비스

**Files:**
- Create: `candidates/services/codex_validation.py`
- Create: `tests/test_codex_validation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_codex_validation.py
import json
import pytest
from unittest.mock import patch

from candidates.services.codex_validation import validate_with_codex


MOCK_CODEX_RESPONSE = json.dumps({
    "verdict": "fail",
    "issues": [
        {
            "field": "careers[0].start_date",
            "type": "missing",
            "evidence": "원본에 'Dec. 2016 – May 2025' 존재하나 추출 결과에 없음",
            "root_cause": "text_extraction",
            "severity": "critical",
            "suggested_value": "2016-12",
        }
    ],
    "field_scores": {"name": 1.0, "careers": 0.3, "educations": 0.9},
    "overall_score": 0.55,
})


@patch("candidates.services.codex_validation._call_codex_cli")
def test_validate_with_codex_fail(mock_call):
    mock_call.return_value = MOCK_CODEX_RESPONSE

    raw_text = "김홍안 이력서 원본 텍스트..."
    extracted = {"name": "김홍안", "careers": [{"company": "북미공장", "start_date": ""}]}
    filename_meta = {"name": "김홍안", "companies": ["대한솔루션", "LG엔솔"]}

    result = validate_with_codex(raw_text, extracted, filename_meta)

    assert result["verdict"] == "fail"
    assert len(result["issues"]) == 1
    assert result["issues"][0]["root_cause"] == "text_extraction"
    assert result["overall_score"] == 0.55


@patch("candidates.services.codex_validation._call_codex_cli")
def test_validate_with_codex_pass(mock_call):
    mock_call.return_value = json.dumps({
        "verdict": "pass",
        "issues": [],
        "field_scores": {"name": 1.0, "careers": 0.95, "educations": 0.9},
        "overall_score": 0.95,
    })

    result = validate_with_codex("text", {"name": "홍길동"}, {})
    assert result["verdict"] == "pass"
    assert result["overall_score"] == 0.95


@patch("candidates.services.codex_validation._call_codex_cli")
def test_validate_with_codex_cli_failure_returns_fallback(mock_call):
    mock_call.side_effect = RuntimeError("codex timeout")

    result = validate_with_codex("text", {"name": "홍길동"}, {})
    assert result["verdict"] == "error"
    assert result["overall_score"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_codex_validation.py -v`
Expected: FAIL with "cannot import name 'validate_with_codex'"

- [ ] **Step 3: Implement codex_validation.py**

```python
"""Codex CLI cross-validation for resume extraction results."""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)

CODEX_VALIDATION_PROMPT = """당신은 이력서 추출 결과 검증 전문가입니다.

## 작업
원본 이력서 텍스트와 AI가 추출한 구조화 JSON을 비교하여 누락, 오류, 환각(hallucination)을 찾아내세요.

## 검증 규칙
1. 원본에 있는 정보가 추출 결과에 누락되었는지 확인 (특히 경력 날짜, 회사명, 직책)
2. 추출된 값이 원본과 다른지 확인
3. 원본에 없는 정보가 추출 결과에 추가되었는지 확인 (환각)
4. 파일명 메타데이터와 추출 결과가 일치하는지 확인

## 원인 분류 (root_cause)
- "text_extraction": 원본 텍스트에 해당 정보가 아예 없음 → 텍스트 추출기가 놓침
- "llm_parsing": 원본 텍스트에 정보가 있는데 AI가 놓치거나 틀림
- "ambiguous_source": 원본 자체가 모호하거나 정보 부족

## 출력 JSON 스키마
```json
{
  "verdict": "pass 또는 fail",
  "issues": [
    {
      "field": "필드 경로 (예: careers[0].start_date)",
      "type": "missing | incorrect | hallucinated",
      "evidence": "근거 설명",
      "root_cause": "text_extraction | llm_parsing | ambiguous_source",
      "severity": "critical | warning",
      "suggested_value": "올바른 값 (알 수 있는 경우)"
    }
  ],
  "field_scores": {"name": 0.0-1.0, "careers": 0.0-1.0, ...},
  "overall_score": 0.0-1.0
}
```

verdict 판정:
- critical issue가 0개이고 overall_score >= 0.85 → "pass"
- 그 외 → "fail"

JSON만 출력하세요."""


def _build_codex_prompt(raw_text: str, extracted: dict, filename_meta: dict) -> str:
    return (
        f"## 원본 이력서 텍스트\n```\n{raw_text[:6000]}\n```\n\n"
        f"## AI 추출 결과 JSON\n```json\n{json.dumps(extracted, ensure_ascii=False, indent=2)}\n```\n\n"
        f"## 파일명 메타데이터\n```json\n{json.dumps(filename_meta, ensure_ascii=False)}\n```\n\n"
        "위 정보를 비교하여 검증 결과 JSON을 출력하세요."
    )


def _call_codex_cli(prompt: str, timeout: int = 120) -> str:
    """Call Codex CLI and return raw response text."""
    result = subprocess.run(
        ["codex", "--full-auto", "-q", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Codex CLI error: {result.stderr[:500]}")
    return result.stdout.strip()


def _parse_codex_response(response_text: str) -> dict:
    """Extract JSON from Codex response."""
    text = response_text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def validate_with_codex(
    raw_text: str,
    extracted: dict,
    filename_meta: dict,
    timeout: int = 120,
) -> dict:
    """Cross-validate extraction results using Codex CLI.

    Returns dict with: verdict, issues, field_scores, overall_score.
    On Codex failure, returns a fallback error result.
    """
    try:
        prompt = _build_codex_prompt(raw_text, extracted, filename_meta)
        response = _call_codex_cli(prompt, timeout=timeout)
        result = _parse_codex_response(response)

        # Ensure required keys
        result.setdefault("verdict", "fail")
        result.setdefault("issues", [])
        result.setdefault("field_scores", {})
        result.setdefault("overall_score", 0.0)

        return result

    except Exception:
        logger.exception("Codex validation failed")
        return {
            "verdict": "error",
            "issues": [],
            "field_scores": {},
            "overall_score": 0.0,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_codex_validation.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add candidates/services/codex_validation.py tests/test_codex_validation.py
git commit -m "feat: add Codex CLI cross-validation service"
```

---

## Task 3: Few-shot 예시 저장소 서비스

**Files:**
- Create: `candidates/services/fewshot_store.py`
- Create: `tests/test_fewshot_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fewshot_store.py
import pytest
from candidates.models import ParseExample
from candidates.services.fewshot_store import get_fewshot_examples, format_fewshot_prompt


@pytest.mark.django_db
def test_get_fewshot_examples_empty():
    result = get_fewshot_examples("Plant")
    assert result == []


@pytest.mark.django_db
def test_get_fewshot_examples_returns_matching_category():
    ParseExample.objects.create(
        category="Plant",
        resume_pattern="영문+국문 혼합",
        input_excerpt="Daehan Solution LLC / President",
        correct_output={"company": "대한솔루션"},
    )
    ParseExample.objects.create(
        category="HR",
        resume_pattern="국문 전용",
        input_excerpt="삼성전자 인사팀",
        correct_output={"company": "삼성전자"},
    )

    result = get_fewshot_examples("Plant")
    assert len(result) == 1
    assert result[0].category == "Plant"


@pytest.mark.django_db
def test_get_fewshot_examples_max_3():
    for i in range(5):
        ParseExample.objects.create(
            category="Plant",
            resume_pattern=f"패턴{i}",
            input_excerpt=f"텍스트{i}",
            correct_output={"idx": i},
        )
    result = get_fewshot_examples("Plant", max_count=3)
    assert len(result) == 3


@pytest.mark.django_db
def test_format_fewshot_prompt_empty():
    result = format_fewshot_prompt([])
    assert result == ""


@pytest.mark.django_db
def test_format_fewshot_prompt_with_examples():
    ex = ParseExample.objects.create(
        category="Plant",
        resume_pattern="영문+국문 혼합",
        input_excerpt="Daehan Solution LLC",
        correct_output={"company": "대한솔루션"},
    )
    result = format_fewshot_prompt([ex])
    assert "대한솔루션" in result
    assert "Daehan Solution LLC" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fewshot_store.py -v`
Expected: FAIL with "cannot import name 'get_fewshot_examples'"

- [ ] **Step 3: Implement fewshot_store.py**

```python
"""Few-shot example store: query and format examples for LLM prompt injection."""

from __future__ import annotations

import json

from candidates.models import ParseExample


def get_fewshot_examples(
    category: str, max_count: int = 3
) -> list[ParseExample]:
    """Get active few-shot examples for a category, newest first."""
    return list(
        ParseExample.objects.filter(
            category=category,
            is_active=True,
        ).order_by("-created_at")[:max_count]
    )


def format_fewshot_prompt(examples: list[ParseExample]) -> str:
    """Format few-shot examples as a prompt section.

    Returns empty string if no examples.
    """
    if not examples:
        return ""

    lines = ["\n\n## 참고: 유사 이력서 추출 예시\n"]
    for i, ex in enumerate(examples, 1):
        lines.append(f"### 예시 {i} ({ex.resume_pattern})")
        lines.append(f"입력:\n```\n{ex.input_excerpt}\n```")
        lines.append(
            f"올바른 추출:\n```json\n"
            f"{json.dumps(ex.correct_output, ensure_ascii=False, indent=2)}\n```\n"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_fewshot_store.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add candidates/services/fewshot_store.py tests/test_fewshot_store.py
git commit -m "feat: add few-shot example store service"
```

---

## Task 4: LLM 추출에 few-shot 삽입 지원

**Files:**
- Modify: `candidates/services/llm_extraction.py`
- Modify: `tests/test_llm_extraction.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_extraction.py — 기존 파일에 추가
from candidates.services.llm_extraction import build_extraction_prompt


def test_build_extraction_prompt_with_fewshot():
    prompt = build_extraction_prompt("이력서 텍스트", fewshot_section="## 예시\n삼성전자")
    assert "예시" in prompt
    assert "삼성전자" in prompt
    assert "이력서 텍스트" in prompt


def test_build_extraction_prompt_without_fewshot():
    prompt = build_extraction_prompt("이력서 텍스트")
    assert "예시" not in prompt
    assert "이력서 텍스트" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_llm_extraction.py::test_build_extraction_prompt_with_fewshot -v`
Expected: FAIL (build_extraction_prompt doesn't accept fewshot_section parameter)

- [ ] **Step 3: Modify build_extraction_prompt to accept fewshot_section**

In `candidates/services/llm_extraction.py`, change the function signature and body:

```python
def build_extraction_prompt(resume_text: str, fewshot_section: str = "") -> str:
    """Build prompt containing the JSON schema, optional few-shot examples, and the resume text."""
    parts = [
        "아래 이력서 텍스트를 분석하여 다음 JSON 스키마에 맞게 구조화하세요.\n\n",
        f"## 출력 JSON 스키마\n```\n{EXTRACTION_JSON_SCHEMA}\n```\n",
    ]
    if fewshot_section:
        parts.append(fewshot_section)
    parts.append(
        f"\n## 이력서 텍스트\n```\n{resume_text}\n```\n\n"
        "위 스키마에 맞는 JSON만 출력하세요. 다른 텍스트는 포함하지 마세요."
    )
    return "".join(parts)
```

- [ ] **Step 4: Modify extract_candidate_data to accept fewshot_section**

```python
def extract_candidate_data(
    resume_text: str, max_retries: int = 3, fewshot_section: str = ""
) -> dict | None:
    """Extract structured candidate data from resume text using LLM."""
    prompt = build_extraction_prompt(resume_text, fewshot_section=fewshot_section)
    # ... rest unchanged
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_llm_extraction.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add candidates/services/llm_extraction.py tests/test_llm_extraction.py
git commit -m "feat: add few-shot injection support to LLM extraction"
```

---

## Task 5: 텍스트 재추출 함수 분리

**Files:**
- Modify: `candidates/services/text_extraction.py`
- Modify: `tests/test_text_extraction.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_text_extraction.py — 기존 파일에 추가
import os
import tempfile
from candidates.services.text_extraction import extract_text_libreoffice


def test_extract_text_libreoffice_with_docx(tmp_path):
    """Test that LibreOffice extraction can be called directly."""
    # Create a minimal valid docx for testing
    from docx import Document
    doc = Document()
    doc.add_paragraph("테스트 이력서 본문입니다")
    path = str(tmp_path / "test.docx")
    doc.save(path)

    result = extract_text_libreoffice(path)
    assert "테스트" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_text_extraction.py::test_extract_text_libreoffice_with_docx -v`
Expected: FAIL with "cannot import name 'extract_text_libreoffice'"

- [ ] **Step 3: Add public extract_text_libreoffice function**

In `candidates/services/text_extraction.py`, add at the bottom:

```python
def extract_text_libreoffice(file_path: str) -> str:
    """Public wrapper for LibreOffice-based text extraction.

    Used by retry pipeline when python-docx extraction misses content.
    """
    return _extract_doc_libreoffice(file_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_text_extraction.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add candidates/services/text_extraction.py tests/test_text_extraction.py
git commit -m "feat: expose LibreOffice extraction for retry pipeline"
```

---

## Task 6: 재시도 오케스트레이터

**Files:**
- Create: `candidates/services/retry_pipeline.py`
- Create: `tests/test_retry_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retry_pipeline.py
import json
import pytest
from unittest.mock import patch, MagicMock

from candidates.services.retry_pipeline import run_extraction_with_retry


@patch("candidates.services.retry_pipeline.validate_with_codex")
@patch("candidates.services.retry_pipeline.extract_candidate_data")
def test_pass_on_first_attempt(mock_extract, mock_codex):
    """First extraction passes validation — no retry needed."""
    mock_extract.return_value = {"name": "홍길동", "careers": []}
    mock_codex.return_value = {
        "verdict": "pass",
        "issues": [],
        "field_scores": {"name": 1.0},
        "overall_score": 0.95,
    }

    result = run_extraction_with_retry(
        raw_text="홍길동 이력서",
        file_path="/tmp/test.docx",
        category="HR",
        filename_meta={"name": "홍길동"},
    )

    assert result["extracted"]["name"] == "홍길동"
    assert result["diagnosis"]["verdict"] == "pass"
    assert result["attempts"] == 1
    assert mock_extract.call_count == 1


@patch("candidates.services.retry_pipeline.validate_with_codex")
@patch("candidates.services.retry_pipeline.extract_candidate_data")
@patch("candidates.services.retry_pipeline.extract_text_libreoffice")
def test_retry_on_text_extraction_failure(mock_libre, mock_extract, mock_codex):
    """text_extraction failure triggers LibreOffice re-extraction + re-parse."""
    mock_extract.side_effect = [
        {"name": "홍길동", "careers": [{"company": "A", "start_date": ""}]},
        {"name": "홍길동", "careers": [{"company": "A", "start_date": "2020-01"}]},
    ]
    mock_codex.side_effect = [
        {
            "verdict": "fail",
            "issues": [{"field": "careers[0].start_date", "root_cause": "text_extraction", "severity": "critical", "type": "missing", "evidence": "...", "suggested_value": "2020-01"}],
            "field_scores": {},
            "overall_score": 0.5,
        },
        {
            "verdict": "pass",
            "issues": [],
            "field_scores": {},
            "overall_score": 0.92,
        },
    ]
    mock_libre.return_value = "홍길동 재추출 텍스트 2020-01"

    result = run_extraction_with_retry(
        raw_text="홍길동 원본",
        file_path="/tmp/test.docx",
        category="HR",
        filename_meta={},
    )

    assert result["diagnosis"]["verdict"] == "pass"
    assert result["attempts"] == 2
    assert mock_libre.call_count == 1


@patch("candidates.services.retry_pipeline.validate_with_codex")
@patch("candidates.services.retry_pipeline.extract_candidate_data")
def test_retry_on_llm_parsing_failure(mock_extract, mock_codex):
    """llm_parsing failure triggers prompt-boosted re-parse."""
    mock_extract.side_effect = [
        {"name": "홍길동", "careers": [{"company": "", "start_date": ""}]},
        {"name": "홍길동", "careers": [{"company": "삼성전자", "start_date": "2020-01"}]},
    ]
    mock_codex.side_effect = [
        {
            "verdict": "fail",
            "issues": [{"field": "careers[0].company", "root_cause": "llm_parsing", "severity": "critical", "type": "missing", "evidence": "원본에 삼성전자 있음", "suggested_value": "삼성전자"}],
            "field_scores": {},
            "overall_score": 0.4,
        },
        {
            "verdict": "pass",
            "issues": [],
            "field_scores": {},
            "overall_score": 0.90,
        },
    ]

    result = run_extraction_with_retry(
        raw_text="삼성전자 홍길동",
        file_path="/tmp/test.docx",
        category="HR",
        filename_meta={},
    )

    assert result["diagnosis"]["verdict"] == "pass"
    assert result["attempts"] == 2


@patch("candidates.services.retry_pipeline.validate_with_codex")
@patch("candidates.services.retry_pipeline.extract_candidate_data")
def test_max_retries_exhausted(mock_extract, mock_codex):
    """After max retries, returns last result with human_review action."""
    mock_extract.return_value = {"name": "홍길동", "careers": []}
    mock_codex.return_value = {
        "verdict": "fail",
        "issues": [{"field": "careers", "root_cause": "ambiguous_source", "severity": "critical", "type": "missing", "evidence": "...", "suggested_value": ""}],
        "field_scores": {},
        "overall_score": 0.3,
    }

    result = run_extraction_with_retry(
        raw_text="홍길동",
        file_path="/tmp/test.docx",
        category="HR",
        filename_meta={},
    )

    assert result["diagnosis"]["verdict"] == "fail"
    assert result["retry_action"] == "human_review"
    assert result["attempts"] <= 4  # 1 initial + max 3 retries
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_retry_pipeline.py -v`
Expected: FAIL with "cannot import name 'run_extraction_with_retry'"

- [ ] **Step 3: Implement retry_pipeline.py**

```python
"""Retry orchestrator: extract → validate → retry with root-cause-specific strategy."""

from __future__ import annotations

import logging

from candidates.services.codex_validation import validate_with_codex
from candidates.services.fewshot_store import format_fewshot_prompt, get_fewshot_examples
from candidates.services.llm_extraction import extract_candidate_data
from candidates.services.text_extraction import extract_text_libreoffice

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _dominant_root_cause(issues: list[dict]) -> str:
    """Determine the dominant root cause from critical issues."""
    critical = [i for i in issues if i.get("severity") == "critical"]
    if not critical:
        return "none"

    causes = [i.get("root_cause", "ambiguous_source") for i in critical]
    # Priority: text_extraction > llm_parsing > ambiguous_source
    if "text_extraction" in causes:
        return "text_extraction"
    if "llm_parsing" in causes:
        return "llm_parsing"
    return "ambiguous_source"


def _build_diagnosis_hints(diagnosis: dict) -> str:
    """Build prompt hints from Codex diagnosis for retry."""
    issues = diagnosis.get("issues", [])
    if not issues:
        return ""

    lines = ["\n\n## 이전 추출에서 발견된 문제 (반드시 교정하세요)\n"]
    for issue in issues:
        field = issue.get("field", "")
        evidence = issue.get("evidence", "")
        suggested = issue.get("suggested_value", "")
        lines.append(f"- **{field}**: {evidence}")
        if suggested:
            lines.append(f"  → 올바른 값: `{suggested}`")
    return "\n".join(lines)


def run_extraction_with_retry(
    raw_text: str,
    file_path: str,
    category: str,
    filename_meta: dict,
) -> dict:
    """Run extraction with Codex cross-validation and automatic retry.

    Returns:
        {
            "extracted": dict,         # Final extraction result
            "diagnosis": dict,         # Final Codex diagnosis
            "attempts": int,           # Total attempts made
            "retry_action": str,       # "none" | "re_extract" | "re_parse" | "human_review"
            "raw_text_used": str,      # Final raw text (may differ from input if re-extracted)
        }
    """
    current_text = raw_text
    fewshot_section = ""
    diagnosis_hints = ""
    re_extracted = False

    # Load few-shot examples for this category
    examples = get_fewshot_examples(category)
    if examples:
        fewshot_section = format_fewshot_prompt(examples)

    for attempt in range(1, MAX_RETRIES + 2):  # 1 initial + MAX_RETRIES
        # Extract
        extracted = extract_candidate_data(
            current_text,
            fewshot_section=fewshot_section + diagnosis_hints,
        )
        if not extracted:
            logger.warning("LLM extraction returned None on attempt %d", attempt)
            if attempt > MAX_RETRIES:
                return {
                    "extracted": None,
                    "diagnosis": {"verdict": "fail", "issues": [], "field_scores": {}, "overall_score": 0.0},
                    "attempts": attempt,
                    "retry_action": "human_review",
                    "raw_text_used": current_text,
                }
            continue

        # Validate with Codex
        diagnosis = validate_with_codex(current_text, extracted, filename_meta)

        if diagnosis["verdict"] == "pass":
            return {
                "extracted": extracted,
                "diagnosis": diagnosis,
                "attempts": attempt,
                "retry_action": "none",
                "raw_text_used": current_text,
            }

        # Max retries exhausted
        if attempt > MAX_RETRIES:
            return {
                "extracted": extracted,
                "diagnosis": diagnosis,
                "attempts": attempt,
                "retry_action": "human_review",
                "raw_text_used": current_text,
            }

        # Determine retry strategy
        root_cause = _dominant_root_cause(diagnosis.get("issues", []))

        if root_cause == "text_extraction" and not re_extracted:
            logger.info("Attempt %d: re-extracting text via LibreOffice", attempt)
            try:
                current_text = extract_text_libreoffice(file_path)
                re_extracted = True
            except Exception:
                logger.exception("LibreOffice re-extraction failed")

        elif root_cause == "llm_parsing":
            logger.info("Attempt %d: retrying with diagnosis hints", attempt)
            diagnosis_hints = _build_diagnosis_hints(diagnosis)

        elif root_cause == "ambiguous_source":
            # No automatic fix possible
            return {
                "extracted": extracted,
                "diagnosis": diagnosis,
                "attempts": attempt,
                "retry_action": "human_review",
                "raw_text_used": current_text,
            }

    # Should not reach here, but safety fallback
    return {
        "extracted": extracted,
        "diagnosis": diagnosis,
        "attempts": MAX_RETRIES + 1,
        "retry_action": "human_review",
        "raw_text_used": current_text,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_retry_pipeline.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add candidates/services/retry_pipeline.py tests/test_retry_pipeline.py
git commit -m "feat: add retry orchestrator with root-cause-based strategy"
```

---

## Task 7: 규칙 엔진 초기 파일

**Files:**
- Create: `candidates/services/extraction_rules.json`

- [ ] **Step 1: Create the initial rules file**

```json
[
  {
    "id": "vml_textbox_priority",
    "trigger": "docx 파일에 VML 텍스트박스 존재",
    "action": "텍스트박스 내용을 본문과 병합하여 추출 (이미 text_extraction.py에 구현됨)",
    "stage": "text_extraction",
    "source_case": "김홍안 2026-03-31",
    "confidence": 1.0
  },
  {
    "id": "libreoffice_fallback_on_missing_dates",
    "trigger": "Codex 검증에서 경력 날짜 다수 누락 + root_cause=text_extraction",
    "action": "LibreOffice로 재추출 후 재파싱",
    "stage": "retry",
    "source_case": "김홍안 2026-03-31",
    "confidence": 1.0
  }
]
```

- [ ] **Step 2: Commit**

```bash
git add candidates/services/extraction_rules.json
git commit -m "feat: add initial extraction rules engine"
```

---

## Task 8: import_resumes 파이프라인 통합

**Files:**
- Modify: `candidates/management/commands/import_resumes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retry_pipeline.py — 추가
from unittest.mock import patch


@patch("candidates.services.retry_pipeline.validate_with_codex")
@patch("candidates.services.retry_pipeline.extract_candidate_data")
def test_run_extraction_with_retry_returns_raw_text_used(mock_extract, mock_codex):
    """Verify raw_text_used is returned for DB storage."""
    mock_extract.return_value = {"name": "테스트"}
    mock_codex.return_value = {"verdict": "pass", "issues": [], "field_scores": {}, "overall_score": 0.95}

    result = run_extraction_with_retry("원본텍스트", "/tmp/t.docx", "HR", {})
    assert result["raw_text_used"] == "원본텍스트"
```

- [ ] **Step 2: Run test — should pass (already implemented)**

Run: `uv run pytest tests/test_retry_pipeline.py::test_run_extraction_with_retry_returns_raw_text_used -v`
Expected: PASS

- [ ] **Step 3: Modify import_resumes.py _process_group method**

Replace the extraction + validation section (lines ~298-317) in `_process_group`:

```python
# Step 3: Extract + Validate + Retry (new pipeline)
from candidates.services.retry_pipeline import run_extraction_with_retry

pipeline_result = run_extraction_with_retry(
    raw_text=raw_text,
    file_path=dest_path,
    category=folder_name,
    filename_meta=parsed,
)

extracted = pipeline_result["extracted"]
if not extracted:
    self._save_failed_resume(
        primary, folder_name, "Extraction failed after retries"
    )
    return False

# Use potentially re-extracted text
raw_text = pipeline_result["raw_text_used"]

# Step 3.5: Fallback name from filename if LLM returned null
if not extracted.get("name"):
    extracted["name"] = parsed.get("name") or primary["file_name"]

# Step 4: Build validation result from Codex diagnosis
diagnosis = pipeline_result["diagnosis"]
field_confidences = extracted.get("field_confidences", {})
validation = {
    "confidence_score": diagnosis.get("overall_score", 0.0),
    "validation_status": (
        "auto_confirmed" if diagnosis["verdict"] == "pass"
        else "needs_review" if diagnosis.get("overall_score", 0) >= 0.6
        else "failed"
    ),
    "field_confidences": {**field_confidences, **diagnosis.get("field_scores", {})},
    "issues": diagnosis.get("issues", []),
}
```

- [ ] **Step 4: Add ValidationDiagnosis creation in the transaction block**

After the ExtractionLog creation, add:

```python
# Save Codex validation diagnosis
from candidates.models import ValidationDiagnosis

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
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add candidates/management/commands/import_resumes.py
git commit -m "feat: integrate retry pipeline into import_resumes command"
```

---

## Task 9: Lint, format, final verification

**Files:** All modified files

- [ ] **Step 1: Run ruff check and format**

Run: `uv run ruff check . && uv run ruff format .`
Expected: No errors

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 3: Run Django system check**

Run: `uv run python manage.py check`
Expected: "System check identified no issues"

- [ ] **Step 4: Verify migration is complete**

Run: `uv run python manage.py showmigrations candidates | grep '\[ \]'`
Expected: No unapplied migrations

- [ ] **Step 5: Final commit if any formatting changes**

```bash
git add -A
git commit -m "chore: lint + format self-evolving parsing pipeline"
```
