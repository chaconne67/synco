# P03a: JD 분석 파이프라인 — 확정 구현계획서

> **Phase:** 3a (P03과 P05 사이)
> **선행조건:** P03 (project CRUD), P01 (models)
> **산출물:** JD 입력 → AI 분석 → requirements 자동 추출 → 서칭 세션 생성

---

## 범위 정의

### IN (P03a)
- JD 입력: 파일 업로드(.doc/.docx/PDF), Google Drive, 텍스트 입력
- 텍스트 추출: 기존 text.py 활용 + PDF 추출 추가
- AI 분석: Gemini structured output → requirements JSON 추출
- 분석 결과 UI: 프로젝트 상세에서 추출된 요구조건 확인/수정/재분석
- 서칭 세션 생성: requirements → SearchSession → redirect
- 후보자 매칭 서비스 레이어: match_candidates(), generate_gap_report()
- 프로젝트 상세 내 매칭 결과 목록 표시

### OUT (P05 이후)
- 서칭 탭 내부 UI 수정
- 후보자 상세 내 Gap 리포트 화면
- HWP 파일 지원
- 공지 초안 자동 생성

---

## Step 1: 모델 변경 + Migration

### Project 모델 추가 필드

```python
# projects/models.py — Project 클래스에 추가

class JDSource(models.TextChoices):
    UPLOAD = "upload", "파일 업로드"
    DRIVE = "drive", "Google Drive"
    TEXT = "text", "텍스트 입력"

# Project 클래스 내부:
jd_source = models.CharField(
    max_length=20, choices=JDSource.choices, blank=True
)
jd_drive_file_id = models.CharField(max_length=255, blank=True)
jd_raw_text = models.TextField(blank=True)  # 파일/Drive에서 추출한 원문
jd_analysis = models.JSONField(default=dict, blank=True)  # AI 전체 분석 결과
# requirements는 기존 필드 (JSONField) — 그대로 활용
# jd_text는 기존 필드 (TextField) — 사용자 직접 입력용으로 유지
# jd_file은 기존 필드 (FileField) — 업로드 파일 저장용으로 유지
```

**필드 역할 정의:**
- `jd_text`: 사용자가 직접 입력한 JD 텍스트 (기존 필드, 변경 없음)
- `jd_raw_text`: 파일 업로드 또는 Drive에서 추출된 원문 텍스트 (신규)
- `jd_file`: 업로드된 JD 파일 (기존 필드, 변경 없음)
- `jd_source`: 현재 사용 중인 JD 입력 소스 (신규)
- `jd_drive_file_id`: Drive 파일 출처 참조용 ID (신규)
- `jd_analysis`: AI 분석 전체 결과 (신규)
- `requirements`: AI가 추출한 구조화 조건 — 서칭 필터 생성 소스 (기존 필드)

**analyze_jd() 텍스트 읽기 순서:** `jd_raw_text` → `jd_text` (둘 다 비어 있으면 에러)

### Migration 파일

```bash
uv run python manage.py makemigrations projects --name add_jd_analysis_fields
uv run python manage.py migrate
```

### 테스트

```python
# tests/test_projects_models.py

def test_project_jd_fields_default():
    """새 필드의 기본값이 올바른지 확인."""
    project = Project(client=client, organization=org, title="Test")
    assert project.jd_source == ""
    assert project.jd_raw_text == ""
    assert project.jd_analysis == {}
```

---

## Step 2: PDF 텍스트 추출 추가

### data_extraction/services/text.py 수정

```python
# extract_text() 함수에 PDF 분기 추가

def extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".docx":
        return _extract_docx(file_path)
    elif ext == ".doc":
        return _extract_doc(file_path)
    elif ext == ".pdf":
        return _extract_pdf(file_path)
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {ext}")


def _extract_pdf(file_path: str) -> str:
    """Extract text from a PDF file using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF not installed. Run: uv add pymupdf")

    doc = fitz.open(file_path)
    parts: list[str] = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            parts.append(text)
    doc.close()
    return "\n".join(parts)
```

### 의존성 추가

```bash
uv add pymupdf
```

### Drive MIME 필터 확장

```python
# data_extraction/services/drive.py — list_files_in_folder() query 수정
# PDF MIME type 추가

query = (
    f"'{folder_id}' in parents"
    " and ("
    "mimeType = 'application/msword'"
    " or mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'"
    " or mimeType = 'application/pdf'"
    ")"
    " and trashed = false"
)
```

### 테스트

```python
# tests/test_de_text.py에 추가

def test_extract_pdf_basic(tmp_path):
    """PDF 파일에서 텍스트를 추출한다."""
    import fitz
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "품질기획팀장 채용공고")
    doc.save(str(pdf_path))
    doc.close()

    result = extract_text(str(pdf_path))
    assert "품질기획팀장" in result

def test_extract_unsupported_format(tmp_path):
    """HWP 등 미지원 포맷은 ValueError."""
    hwp_path = tmp_path / "test.hwp"
    hwp_path.write_text("dummy")
    with pytest.raises(ValueError, match="지원하지 않는 파일 형식"):
        extract_text(str(hwp_path))
```

---

## Step 3: Gemini JD 분석 서비스

### projects/services/__init__.py

빈 파일 생성 (패키지 초기화).

### projects/services/jd_prompts.py

```python
"""JD 분석용 Gemini 프롬프트."""

JD_ANALYSIS_SYSTEM_PROMPT = """\
당신은 채용 공고(JD) 분석 전문가입니다.
JD 텍스트에서 구조화된 요구조건을 추출합니다.

## 원칙
1. JD에 명시된 조건만 추출합니다. 추정하지 마세요.
2. 누락된 항목은 null로 반환합니다.
3. 한국어 원문을 우선 사용합니다.
4. 연봉/급여 정보가 있으면 포함합니다.
5. 올해는 2026년입니다.

## 출력 형식 (JSON만 출력)
```json
{
  "position": "포지션명",
  "position_level": "직급 범위 (예: 과장~차장) 또는 null",
  "birth_year_from": null,
  "birth_year_to": null,
  "gender": null,
  "min_experience_years": null,
  "max_experience_years": null,
  "education_preference": "학력 선호 (예: 이공계열) 또는 null",
  "education_fields": ["전공1", "전공2"],
  "required_certifications": [],
  "preferred_certifications": [],
  "keywords": ["직무 관련 핵심 키워드"],
  "industry": "업종 (예: 제조업) 또는 null",
  "role_summary": "직무 요약 1-2문장",
  "responsibilities": ["주요 업무1", "주요 업무2"],
  "company_name": "채용 기업명 또는 null",
  "location": "근무지 또는 null",
  "salary_info": "연봉 정보 또는 null"
}
```

## 주의사항
- "나이" 조건이 있으면 birth_year_from/to로 변환 (2026 - 나이)
- "경력 N년 이상"은 min_experience_years로
- gender는 "male", "female", null 중 하나
- keywords는 직무 수행에 필요한 기술/도구/방법론 키워드
"""

JD_ANALYSIS_USER_PROMPT_TEMPLATE = """\
아래 채용 공고(JD)의 요구조건을 구조화된 JSON으로 추출하세요.

## JD 원문
{jd_text}
"""
```

### projects/services/jd_analysis.py

```python
"""JD 분석 파이프라인: 텍스트 추출 → AI 분석 → requirements 저장."""

import logging
import os
import tempfile

from django.conf import settings
from google import genai

from data_extraction.services.extraction.sanitizers import parse_llm_json
from data_extraction.services.text import extract_text

from .jd_prompts import JD_ANALYSIS_SYSTEM_PROMPT, JD_ANALYSIS_USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-preview-05-20"


def _get_gemini_client() -> genai.Client:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in settings")
    return genai.Client(api_key=api_key)


def analyze_jd(project) -> dict:
    """JD 텍스트를 분석하여 requirements를 추출한다.

    텍스트 읽기 순서: jd_raw_text → jd_text
    실패 시 기존 jd_analysis/requirements는 보존한다.

    Returns:
        {"requirements": dict, "full_analysis": dict} on success
    Raises:
        ValueError: JD 텍스트가 없는 경우
        RuntimeError: Gemini API 호출 실패 (3회 재시도 후)
    """
    raw_text = project.jd_raw_text or project.jd_text
    if not raw_text or not raw_text.strip():
        raise ValueError("분석할 JD 텍스트가 없습니다.")

    result = extract_jd_requirements(raw_text)

    project.jd_analysis = result["full_analysis"]
    project.requirements = result["requirements"]
    project.save(update_fields=["jd_analysis", "requirements", "updated_at"])
    return result


def extract_jd_requirements(text: str, max_retries: int = 3) -> dict:
    """Gemini API로 JD 텍스트에서 요구조건 추출.

    Returns:
        {
            "full_analysis": dict,  # Gemini 원본 응답 전체
            "requirements": dict,   # 검색 필터 생성용 정규화된 구조
        }
    Raises:
        RuntimeError: max_retries 초과 시
    """
    client = _get_gemini_client()
    user_prompt = JD_ANALYSIS_USER_PROMPT_TEMPLATE.format(jd_text=text)

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=JD_ANALYSIS_SYSTEM_PROMPT,
                    max_output_tokens=4000,
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )

            parsed = parse_llm_json(response.text)

            if not isinstance(parsed, dict) or "position" not in parsed:
                logger.warning(
                    "Gemini JD analysis: invalid structure (attempt %d/%d)",
                    attempt + 1, max_retries,
                )
                continue

            return {
                "full_analysis": parsed,
                "requirements": parsed,  # 동일 구조 저장
            }

        except Exception:
            logger.warning(
                "Gemini JD analysis failed (attempt %d/%d)",
                attempt + 1, max_retries,
                exc_info=True,
            )

    raise RuntimeError("JD 분석에 실패했습니다. 잠시 후 다시 시도해주세요.")


def extract_text_from_file(file_field) -> str:
    """Django FileField에서 텍스트를 추출한다.

    임시 파일로 저장 후 text.py의 extract_text() 호출.
    """
    ext = os.path.splitext(file_field.name)[1].lower()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        for chunk in file_field.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        return extract_text(tmp_path)
    finally:
        os.unlink(tmp_path)


def extract_text_from_drive(file_id: str) -> str:
    """Drive 파일 ID로부터 텍스트를 추출한다.

    Drive API로 다운로드 → 임시 파일 → extract_text() → 텍스트 반환.
    """
    from data_extraction.services.drive import (
        download_file,
        get_drive_service,
    )

    service = get_drive_service()

    # 파일 메타데이터에서 이름 가져오기
    file_meta = service.files().get(fileId=file_id, fields="name,mimeType").execute()
    file_name = file_meta.get("name", "unknown")
    ext = os.path.splitext(file_name)[1].lower()

    if ext not in (".doc", ".docx", ".pdf"):
        raise ValueError(f"지원하지 않는 파일 형식: {ext} ({file_name})")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        download_file(service, file_id, tmp_path)
        return extract_text(tmp_path)
    finally:
        os.unlink(tmp_path)


def requirements_to_search_filters(requirements: dict) -> dict:
    """requirements JSON을 SearchSession.current_filters 호환 dict로 변환.

    requirements 스키마 (AI 추출 결과):
        position, position_level, birth_year_from/to, gender,
        min/max_experience_years, education_preference, education_fields,
        required_certifications, preferred_certifications, keywords,
        industry, role_summary, responsibilities

    target 스키마 (FILTER_SPEC_TEMPLATE):
        category, name_keywords, company_keywords, school_keywords,
        school_groups, major_keywords, certification_keywords,
        language_keywords, position_keywords, skill_keywords,
        keyword, gender, min/max_experience_years,
        birth_year_from/to, is_abroad_education, recommendation_status
    """
    if not requirements:
        return {}

    filters = {
        "category": None,
        "name_keywords": [],
        "company_keywords": [],
        "school_keywords": [],
        "school_groups": [],
        "major_keywords": requirements.get("education_fields") or [],
        "certification_keywords": (
            (requirements.get("required_certifications") or [])
            + (requirements.get("preferred_certifications") or [])
        ),
        "language_keywords": [],
        "position_keywords": [requirements["position"]] if requirements.get("position") else [],
        "skill_keywords": requirements.get("keywords") or [],
        "keyword": None,
        "gender": requirements.get("gender"),
        "min_experience_years": requirements.get("min_experience_years"),
        "max_experience_years": requirements.get("max_experience_years"),
        "birth_year_from": requirements.get("birth_year_from"),
        "birth_year_to": requirements.get("birth_year_to"),
        "is_abroad_education": None,
        "recommendation_status": [],
    }

    return filters
```

### 테스트

```python
# tests/test_jd_analysis.py

import pytest
from unittest.mock import patch, MagicMock


class TestRequirementsToSearchFilters:
    def test_basic_mapping(self):
        """requirements → search filters 기본 매핑."""
        from projects.services.jd_analysis import requirements_to_search_filters

        reqs = {
            "position": "품질기획팀장",
            "min_experience_years": 12,
            "max_experience_years": 16,
            "birth_year_from": 1982,
            "birth_year_to": 1986,
            "gender": "male",
            "education_fields": ["전자공학", "재료공학"],
            "required_certifications": ["품질경영기사"],
            "preferred_certifications": ["6Sigma BB"],
            "keywords": ["QMS", "ISO"],
        }
        filters = requirements_to_search_filters(reqs)

        assert filters["position_keywords"] == ["품질기획팀장"]
        assert filters["min_experience_years"] == 12
        assert filters["major_keywords"] == ["전자공학", "재료공학"]
        assert "품질경영기사" in filters["certification_keywords"]
        assert "6Sigma BB" in filters["certification_keywords"]
        assert filters["skill_keywords"] == ["QMS", "ISO"]
        assert filters["gender"] == "male"

    def test_empty_requirements(self):
        """빈 requirements → 빈 필터."""
        from projects.services.jd_analysis import requirements_to_search_filters

        assert requirements_to_search_filters({}) == {}
        assert requirements_to_search_filters(None) == {}

    def test_partial_requirements(self):
        """일부 필드만 있는 requirements도 정상 처리."""
        from projects.services.jd_analysis import requirements_to_search_filters

        reqs = {"position": "개발자", "keywords": ["Python"]}
        filters = requirements_to_search_filters(reqs)
        assert filters["position_keywords"] == ["개발자"]
        assert filters["skill_keywords"] == ["Python"]
        assert filters["gender"] is None


class TestExtractJDRequirements:
    @patch("projects.services.jd_analysis._get_gemini_client")
    def test_successful_extraction(self, mock_client):
        """Gemini가 정상 응답 시 requirements를 반환한다."""
        from projects.services.jd_analysis import extract_jd_requirements

        mock_response = MagicMock()
        mock_response.text = '{"position": "개발자", "keywords": ["Python"]}'
        mock_client.return_value.models.generate_content.return_value = mock_response

        result = extract_jd_requirements("JD 텍스트")
        assert result["requirements"]["position"] == "개발자"

    @patch("projects.services.jd_analysis._get_gemini_client")
    def test_all_retries_fail(self, mock_client):
        """3회 재시도 모두 실패 시 RuntimeError."""
        from projects.services.jd_analysis import extract_jd_requirements

        mock_client.return_value.models.generate_content.side_effect = Exception("API error")

        with pytest.raises(RuntimeError, match="JD 분석에 실패"):
            extract_jd_requirements("JD 텍스트")

    @patch("projects.services.jd_analysis._get_gemini_client")
    def test_invalid_response_retries(self, mock_client):
        """유효하지 않은 응답은 재시도한다."""
        from projects.services.jd_analysis import extract_jd_requirements

        bad_response = MagicMock()
        bad_response.text = '{"invalid": true}'
        good_response = MagicMock()
        good_response.text = '{"position": "개발자"}'

        mock_client.return_value.models.generate_content.side_effect = [
            bad_response, good_response
        ]

        result = extract_jd_requirements("JD 텍스트")
        assert result["requirements"]["position"] == "개발자"


class TestAnalyzeJD:
    @patch("projects.services.jd_analysis.extract_jd_requirements")
    def test_reads_jd_raw_text_first(self, mock_extract):
        """jd_raw_text를 우선 읽는다."""
        from projects.services.jd_analysis import analyze_jd

        mock_extract.return_value = {
            "full_analysis": {"position": "개발자"},
            "requirements": {"position": "개발자"},
        }

        project = MagicMock()
        project.jd_raw_text = "raw text"
        project.jd_text = "user text"

        analyze_jd(project)
        mock_extract.assert_called_once_with("raw text")

    @patch("projects.services.jd_analysis.extract_jd_requirements")
    def test_falls_back_to_jd_text(self, mock_extract):
        """jd_raw_text가 비어있으면 jd_text를 읽는다."""
        from projects.services.jd_analysis import analyze_jd

        mock_extract.return_value = {
            "full_analysis": {"position": "개발자"},
            "requirements": {"position": "개발자"},
        }

        project = MagicMock()
        project.jd_raw_text = ""
        project.jd_text = "user text"

        analyze_jd(project)
        mock_extract.assert_called_once_with("user text")

    def test_raises_when_no_text(self):
        """JD 텍스트가 전혀 없으면 ValueError."""
        from projects.services.jd_analysis import analyze_jd

        project = MagicMock()
        project.jd_raw_text = ""
        project.jd_text = ""

        with pytest.raises(ValueError, match="분석할 JD 텍스트가 없습니다"):
            analyze_jd(project)


class TestExtractTextFromFile:
    def test_extracts_from_pdf(self, tmp_path):
        """PDF FileField에서 텍스트 추출."""
        import fitz
        from projects.services.jd_analysis import extract_text_from_file

        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "테스트 JD")
        doc.save(str(pdf_path))
        doc.close()

        # FileField mock
        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        mock_file.chunks.return_value = [open(pdf_path, "rb").read()]

        result = extract_text_from_file(mock_file)
        assert "테스트 JD" in result
```

---

## Step 4: 후보자 매칭 서비스

### projects/services/candidate_matching.py

```python
"""후보자 적합도 매칭: requirements 기반 스코어링."""

from __future__ import annotations

import logging

from django.db.models import Q, QuerySet

logger = logging.getLogger(__name__)

# 5차원 가중치
WEIGHTS = {
    "experience": 0.25,
    "keywords": 0.25,
    "certifications": 0.20,
    "education": 0.15,
    "demographics": 0.15,
}

# 대학 그룹 (search.py에서 재활용)
from candidates.services.search import UNIVERSITY_GROUPS


def match_candidates(
    requirements: dict,
    organization=None,
    limit: int = 100,
) -> list[dict]:
    """requirements 기반으로 후보자를 검색하고 적합도 점수를 산출.

    Args:
        requirements: AI가 추출한 JD 요구조건
        organization: Organization 필터 (현재 미사용, 향후 확장)
        limit: 최대 결과 수

    Returns:
        [{"candidate": Candidate, "score": float, "level": str, "details": dict}, ...]
        level: "높음" (70%+), "보통" (40-70%), "낮음" (40%-)
    """
    from candidates.models import Candidate
    from candidates.services.search import build_search_queryset, normalize_filter_spec
    from projects.services.jd_analysis import requirements_to_search_filters

    # 1. requirements → 검색 필터 변환
    filters = requirements_to_search_filters(requirements)
    if not filters:
        return []

    # 2. 기본 검색으로 후보자 풀 확보 (느슨한 필터)
    # 경력/성별/연령만으로 1차 필터링
    loose_filters = normalize_filter_spec({
        "min_experience_years": filters.get("min_experience_years"),
        "max_experience_years": filters.get("max_experience_years"),
        "gender": filters.get("gender"),
        "birth_year_from": filters.get("birth_year_from"),
        "birth_year_to": filters.get("birth_year_to"),
    })
    qs = build_search_queryset(loose_filters)[:limit * 3]

    # 3. 개별 스코어링
    results = []
    for candidate in qs:
        score, details = _score_candidate(candidate, requirements)
        level = _score_to_level(score)
        results.append({
            "candidate": candidate,
            "score": round(score, 2),
            "level": level,
            "details": details,
        })

    # 4. 점수순 정렬 + 상위 limit개
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def _score_candidate(candidate, requirements: dict) -> tuple[float, dict]:
    """후보자의 적합도 점수를 산출.

    Returns:
        (total_score: 0.0~1.0, details: {dimension: {score, reason}})
    """
    details = {}

    # 1. 경력 범위 (25%)
    exp_score, exp_reason = _score_experience(candidate, requirements)
    details["experience"] = {"score": exp_score, "reason": exp_reason}

    # 2. 키워드 매칭 (25%)
    kw_score, kw_reason = _score_keywords(candidate, requirements)
    details["keywords"] = {"score": kw_score, "reason": kw_reason}

    # 3. 자격증 (20%)
    cert_score, cert_reason = _score_certifications(candidate, requirements)
    details["certifications"] = {"score": cert_score, "reason": cert_reason}

    # 4. 학력 (15%)
    edu_score, edu_reason = _score_education(candidate, requirements)
    details["education"] = {"score": edu_score, "reason": edu_reason}

    # 5. 연령·성별 (15%)
    demo_score, demo_reason = _score_demographics(candidate, requirements)
    details["demographics"] = {"score": demo_score, "reason": demo_reason}

    total = (
        exp_score * WEIGHTS["experience"]
        + kw_score * WEIGHTS["keywords"]
        + cert_score * WEIGHTS["certifications"]
        + edu_score * WEIGHTS["education"]
        + demo_score * WEIGHTS["demographics"]
    )

    return total, details


def _score_experience(candidate, requirements: dict) -> tuple[float, str]:
    """경력 범위 일치 점수."""
    exp = candidate.total_experience_years
    if exp is None:
        return 0.5, "경력 정보 없음 (판정 불가)"

    min_exp = requirements.get("min_experience_years")
    max_exp = requirements.get("max_experience_years")

    if min_exp is None and max_exp is None:
        return 1.0, "경력 조건 없음"

    # 범위 내 = 만점
    in_range = True
    if min_exp is not None and exp < min_exp:
        in_range = False
    if max_exp is not None and exp > max_exp:
        in_range = False

    if in_range:
        return 1.0, f"경력 {exp}년 (범위 내)"

    # 범위에서 ±2년 = 감점
    gap = 0
    if min_exp is not None and exp < min_exp:
        gap = min_exp - exp
    elif max_exp is not None and exp > max_exp:
        gap = exp - max_exp

    if gap <= 2:
        return 0.5, f"경력 {exp}년 (범위에서 {gap}년 차이)"

    return 0.0, f"경력 {exp}년 (범위 초과)"


def _score_keywords(candidate, requirements: dict) -> tuple[float, str]:
    """키워드 매칭 점수: JD 키워드와 후보자 경력/스킬 텍스트 겹침 비율."""
    jd_keywords = requirements.get("keywords") or []
    if not jd_keywords:
        return 1.0, "키워드 조건 없음"

    # 후보자 텍스트 풀 구성
    candidate_text = _build_candidate_text(candidate).lower()

    matched = []
    for kw in jd_keywords:
        if kw.lower() in candidate_text:
            matched.append(kw)

    ratio = len(matched) / len(jd_keywords) if jd_keywords else 0
    matched_str = ", ".join(matched[:5]) if matched else "없음"
    return ratio, f"키워드 {len(matched)}/{len(jd_keywords)} 매칭 ({matched_str})"


def _build_candidate_text(candidate) -> str:
    """후보자의 검색 가능한 텍스트를 결합."""
    parts = [
        candidate.current_company or "",
        candidate.current_position or "",
        candidate.summary or "",
    ]

    # 경력
    for career in candidate.careers.all():
        parts.extend([
            career.company or "",
            career.position or "",
            career.duties or "",
            career.achievements or "",
        ])

    # 스킬
    skills = candidate.skills or []
    if isinstance(skills, list):
        for s in skills:
            if isinstance(s, str):
                parts.append(s)
            elif isinstance(s, dict):
                parts.append(s.get("name", ""))

    return " ".join(parts)


def _score_certifications(candidate, requirements: dict) -> tuple[float, str]:
    """자격증 보유 점수."""
    required = requirements.get("required_certifications") or []
    preferred = requirements.get("preferred_certifications") or []

    if not required and not preferred:
        return 1.0, "자격증 조건 없음"

    candidate_certs = [
        c.name.lower() for c in candidate.certifications.all()
    ]

    # required 충족 체크
    required_met = 0
    for cert in required:
        if any(cert.lower() in cc for cc in candidate_certs):
            required_met += 1

    # preferred 보너스
    preferred_met = 0
    for cert in preferred:
        if any(cert.lower() in cc for cc in candidate_certs):
            preferred_met += 1

    if required:
        base_score = required_met / len(required)
    else:
        base_score = 1.0

    if preferred:
        bonus = (preferred_met / len(preferred)) * 0.3  # 최대 30% 보너스
    else:
        bonus = 0

    score = min(base_score + bonus, 1.0)
    return score, f"필수 {required_met}/{len(required)}, 우대 {preferred_met}/{len(preferred)}"


def _score_education(candidate, requirements: dict) -> tuple[float, str]:
    """학력 조건 점수: 전공 일치 + 대학 그룹 매칭."""
    edu_fields = requirements.get("education_fields") or []
    edu_pref = requirements.get("education_preference") or ""

    if not edu_fields and not edu_pref:
        return 1.0, "학력 조건 없음"

    candidate_edus = list(candidate.educations.all())
    if not candidate_edus:
        return 0.5, "학력 정보 없음 (판정 불가)"

    score = 0.0
    reasons = []

    # 전공 일치
    if edu_fields:
        candidate_majors = [e.major.lower() for e in candidate_edus if e.major]
        field_matched = 0
        for field in edu_fields:
            if any(field.lower() in m for m in candidate_majors):
                field_matched += 1
        if field_matched > 0:
            score += 0.7
            reasons.append(f"전공 {field_matched}/{len(edu_fields)} 일치")
        else:
            reasons.append("전공 불일치")

    # 대학 그룹 매칭 (UNIVERSITY_GROUPS 재활용)
    candidate_schools = [e.institution for e in candidate_edus if e.institution]
    for group_name, schools in UNIVERSITY_GROUPS.items():
        for school in schools:
            if any(school in cs for cs in candidate_schools):
                score += 0.3
                reasons.append(f"{group_name} 소속")
                break
        else:
            continue
        break

    return min(score, 1.0), " / ".join(reasons) if reasons else "판정 불가"


def _score_demographics(candidate, requirements: dict) -> tuple[float, str]:
    """연령·성별 점수."""
    score = 1.0
    reasons = []

    # 성별
    req_gender = requirements.get("gender")
    if req_gender:
        if candidate.gender and candidate.gender.lower() != req_gender.lower():
            score = 0.0
            reasons.append(f"성별 불일치 (요구: {req_gender})")
        elif not candidate.gender:
            reasons.append("성별 정보 없음")
        else:
            reasons.append("성별 일치")

    # 연령
    birth_from = requirements.get("birth_year_from")
    birth_to = requirements.get("birth_year_to")
    if birth_from or birth_to:
        if candidate.birth_year:
            in_range = True
            if birth_from and candidate.birth_year < birth_from:
                in_range = False
            if birth_to and candidate.birth_year > birth_to:
                in_range = False
            if not in_range:
                score = 0.0
                reasons.append(f"연령 범위 밖 (출생: {candidate.birth_year})")
            else:
                reasons.append("연령 범위 내")
        else:
            reasons.append("출생연도 정보 없음")

    return score, " / ".join(reasons) if reasons else "인구통계 조건 없음"


def _score_to_level(score: float) -> str:
    """점수를 등급으로 변환."""
    if score >= 0.7:
        return "높음"
    elif score >= 0.4:
        return "보통"
    return "낮음"


def generate_gap_report(candidate, requirements: dict) -> dict:
    """후보자별 JD 요구사항 충족/미충족 항목 분석 리포트.

    Returns:
        {
            "candidate_name": str,
            "overall_score": float,
            "overall_level": str,
            "met": [{"item": str, "evidence": str}],
            "unmet": [{"item": str, "detail": str}],
            "unknown": [{"item": str, "reason": str}],
        }
    """
    score, details = _score_candidate(candidate, requirements)

    met = []
    unmet = []
    unknown = []

    for dim_name, dim_data in details.items():
        dim_score = dim_data["score"]
        dim_reason = dim_data["reason"]

        if "판정 불가" in dim_reason or "정보 없음" in dim_reason:
            unknown.append({"item": dim_name, "reason": dim_reason})
        elif dim_score >= 0.7:
            met.append({"item": dim_name, "evidence": dim_reason})
        else:
            unmet.append({"item": dim_name, "detail": dim_reason})

    return {
        "candidate_name": candidate.name,
        "overall_score": round(score, 2),
        "overall_level": _score_to_level(score),
        "met": met,
        "unmet": unmet,
        "unknown": unknown,
    }
```

### 테스트

```python
# tests/test_candidate_matching.py

import pytest
from unittest.mock import MagicMock, PropertyMock


def _make_candidate(**kwargs):
    """테스트용 mock 후보자 생성."""
    c = MagicMock()
    c.name = kwargs.get("name", "테스트")
    c.total_experience_years = kwargs.get("exp", 10)
    c.gender = kwargs.get("gender", "")
    c.birth_year = kwargs.get("birth_year", None)
    c.current_company = kwargs.get("company", "")
    c.current_position = kwargs.get("position", "")
    c.summary = kwargs.get("summary", "")
    c.skills = kwargs.get("skills", [])
    c.careers.all.return_value = []
    c.certifications.all.return_value = []
    c.educations.all.return_value = []
    return c


class TestScoreExperience:
    def test_in_range(self):
        from projects.services.candidate_matching import _score_experience

        c = _make_candidate(exp=14)
        score, _ = _score_experience(c, {"min_experience_years": 12, "max_experience_years": 16})
        assert score == 1.0

    def test_slightly_out_of_range(self):
        from projects.services.candidate_matching import _score_experience

        c = _make_candidate(exp=10)
        score, _ = _score_experience(c, {"min_experience_years": 12, "max_experience_years": 16})
        assert score == 0.5

    def test_far_out_of_range(self):
        from projects.services.candidate_matching import _score_experience

        c = _make_candidate(exp=5)
        score, _ = _score_experience(c, {"min_experience_years": 12, "max_experience_years": 16})
        assert score == 0.0

    def test_no_exp_data(self):
        from projects.services.candidate_matching import _score_experience

        c = _make_candidate(exp=None)
        score, reason = _score_experience(c, {"min_experience_years": 12})
        assert score == 0.5
        assert "판정 불가" in reason


class TestScoreKeywords:
    def test_full_match(self):
        from projects.services.candidate_matching import _score_keywords

        c = _make_candidate(summary="QMS ISO IATF 경험 보유")
        score, _ = _score_keywords(c, {"keywords": ["QMS", "ISO", "IATF"]})
        assert score == 1.0

    def test_partial_match(self):
        from projects.services.candidate_matching import _score_keywords

        c = _make_candidate(summary="QMS 시스템 구축")
        score, _ = _score_keywords(c, {"keywords": ["QMS", "ISO", "IATF"]})
        assert 0.3 <= score <= 0.4  # 1/3


class TestScoreDemographics:
    def test_gender_mismatch(self):
        from projects.services.candidate_matching import _score_demographics

        c = _make_candidate(gender="female")
        score, _ = _score_demographics(c, {"gender": "male"})
        assert score == 0.0

    def test_birth_year_out_of_range(self):
        from projects.services.candidate_matching import _score_demographics

        c = _make_candidate(birth_year=1990)
        score, _ = _score_demographics(c, {"birth_year_from": 1982, "birth_year_to": 1986})
        assert score == 0.0


class TestGenerateGapReport:
    def test_report_structure(self):
        from projects.services.candidate_matching import generate_gap_report

        c = _make_candidate(name="홍길동", exp=14)
        reqs = {"min_experience_years": 12, "keywords": ["QMS"]}
        report = generate_gap_report(c, reqs)

        assert report["candidate_name"] == "홍길동"
        assert "overall_score" in report
        assert "overall_level" in report
        assert isinstance(report["met"], list)
        assert isinstance(report["unmet"], list)
        assert isinstance(report["unknown"], list)


class TestScoreToLevel:
    def test_levels(self):
        from projects.services.candidate_matching import _score_to_level

        assert _score_to_level(0.8) == "높음"
        assert _score_to_level(0.5) == "보통"
        assert _score_to_level(0.2) == "낮음"
```

---

## Step 5: 폼 확장 + JD 소스 Validation

### projects/forms.py 수정

```python
from django import forms
from clients.models import Client
from .models import Project, JDSource

INPUT_CSS = (
    "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] "
    "focus:ring-2 focus:ring-primary focus:border-primary"
)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["client", "title", "jd_source", "jd_text", "jd_file", "status"]
        widgets = {
            "client": forms.Select(attrs={"class": INPUT_CSS}),
            "title": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "프로젝트명"}
            ),
            "jd_source": forms.Select(attrs={"class": INPUT_CSS}),
            "jd_text": forms.Textarea(
                attrs={
                    "class": INPUT_CSS,
                    "rows": 5,
                    "placeholder": "채용 공고 내용을 입력하세요",
                }
            ),
            "jd_file": forms.ClearableFileInput(attrs={"class": INPUT_CSS}),
            "status": forms.Select(attrs={"class": INPUT_CSS}),
        }
        labels = {
            "client": "고객사",
            "title": "프로젝트명",
            "jd_source": "JD 입력 방식",
            "jd_text": "JD 내용",
            "jd_file": "JD 파일",
            "status": "상태",
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields["client"].queryset = Client.objects.filter(
                organization=organization
            )
        self.fields["jd_text"].required = False
        self.fields["jd_file"].required = False
        self.fields["jd_source"].required = False

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("jd_source")

        if source == JDSource.TEXT and not cleaned.get("jd_text"):
            self.add_error("jd_text", "텍스트 입력 방식을 선택한 경우 JD 내용을 입력해야 합니다.")
        elif source == JDSource.UPLOAD and not cleaned.get("jd_file"):
            if not (self.instance and self.instance.jd_file):
                self.add_error("jd_file", "파일 업로드 방식을 선택한 경우 파일을 첨부해야 합니다.")

        return cleaned
```

### 소스 변경 시 기존 분석 리셋 로직 (views.py에서 처리)

```python
# project_create / project_update 뷰에서:
# 소스가 변경되면 기존 jd_raw_text, jd_analysis, requirements 초기화

def _reset_jd_analysis_if_source_changed(project, old_source):
    """JD 소스가 변경되면 기존 분석 결과를 초기화한다."""
    if old_source and project.jd_source != old_source:
        project.jd_raw_text = ""
        project.jd_analysis = {}
        project.requirements = {}
```

---

## Step 6: 뷰 추가

### projects/views.py 추가 뷰

```python
import json
import os

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import Project


@login_required
@require_http_methods(["POST"])
def analyze_jd(request, pk):
    """JD 분석 트리거. 파일 업로드 시 텍스트 추출 후 AI 분석."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    from projects.services.jd_analysis import (
        analyze_jd as run_analysis,
        extract_text_from_file,
    )

    # 파일 업로드 소스인 경우: 파일에서 텍스트 추출
    if project.jd_source == "upload" and project.jd_file:
        if not project.jd_raw_text:
            try:
                project.jd_raw_text = extract_text_from_file(project.jd_file)
                project.save(update_fields=["jd_raw_text"])
            except (ValueError, RuntimeError) as e:
                return render(
                    request,
                    "projects/partials/jd_analysis_error.html",
                    {"error": str(e), "project": project},
                )

    # AI 분석 실행
    try:
        result = run_analysis(project)
    except ValueError as e:
        return render(
            request,
            "projects/partials/jd_analysis_error.html",
            {"error": str(e), "project": project},
        )
    except RuntimeError as e:
        return render(
            request,
            "projects/partials/jd_analysis_error.html",
            {"error": str(e), "project": project},
        )

    # 분석 결과 partial 반환
    return render(
        request,
        "projects/partials/jd_analysis_result.html",
        {"project": project, "analysis": result},
    )


@login_required
def jd_results(request, pk):
    """JD 분석 결과 표시 (HTMX partial)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    return render(
        request,
        "projects/partials/jd_analysis_result.html",
        {
            "project": project,
            "analysis": {
                "requirements": project.requirements,
                "full_analysis": project.jd_analysis,
            },
        },
    )


@login_required
def drive_picker(request, pk):
    """Drive 파일 선택 UI. GET=파일 목록, POST=파일 선택+텍스트 추출."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if request.method == "POST":
        file_id = request.POST.get("file_id")
        if not file_id:
            return render(
                request,
                "projects/partials/jd_drive_picker.html",
                {"project": project, "error": "파일을 선택해주세요."},
            )

        from projects.services.jd_analysis import extract_text_from_drive

        try:
            raw_text = extract_text_from_drive(file_id)
        except (ValueError, RuntimeError) as e:
            return render(
                request,
                "projects/partials/jd_drive_picker.html",
                {"project": project, "error": str(e)},
            )

        project.jd_source = "drive"
        project.jd_drive_file_id = file_id
        project.jd_raw_text = raw_text
        # 기존 분석 리셋
        project.jd_analysis = {}
        project.requirements = {}
        project.save(update_fields=[
            "jd_source", "jd_drive_file_id", "jd_raw_text",
            "jd_analysis", "requirements",
        ])

        return render(
            request,
            "projects/partials/jd_drive_picker.html",
            {"project": project, "success": True},
        )

    # GET: Drive 파일 목록
    from data_extraction.services.drive import (
        get_drive_service,
        list_files_in_folder,
    )
    from django.conf import settings

    try:
        service = get_drive_service()
        parent_folder_id = getattr(settings, "GOOGLE_DRIVE_PARENT_FOLDER_ID", "")
        files = list_files_in_folder(service, parent_folder_id) if parent_folder_id else []
    except Exception as e:
        files = []

    return render(
        request,
        "projects/partials/jd_drive_picker.html",
        {"project": project, "drive_files": files},
    )


@login_required
@require_http_methods(["POST"])
def start_search_session(request, pk):
    """프로젝트 requirements → SearchSession 생성 → 후보자 검색으로 redirect."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if not project.requirements:
        return render(
            request,
            "projects/partials/jd_analysis_error.html",
            {"error": "JD 분석이 먼저 필요합니다.", "project": project},
        )

    from candidates.models import SearchSession
    from projects.services.jd_analysis import requirements_to_search_filters

    filters = requirements_to_search_filters(project.requirements)

    session = SearchSession.objects.create(
        user=request.user,
        current_filters=filters,
    )

    return redirect(f"/candidates/?session_id={session.pk}")


@login_required
def jd_matching_results(request, pk):
    """프로젝트 상세 내 후보자 매칭 결과 목록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if not project.requirements:
        return render(
            request,
            "projects/partials/jd_matching_empty.html",
            {"project": project},
        )

    from projects.services.candidate_matching import match_candidates

    results = match_candidates(project.requirements, limit=50)

    return render(
        request,
        "projects/partials/jd_matching_results.html",
        {"project": project, "results": results},
    )
```

---

## Step 7: URL 등록

### projects/urls.py 수정

```python
from django.urls import path
from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="project_list"),
    path("new/", views.project_create, name="project_create"),
    path("<uuid:pk>/", views.project_detail, name="project_detail"),
    path("<uuid:pk>/edit/", views.project_update, name="project_update"),
    path("<uuid:pk>/delete/", views.project_delete, name="project_delete"),
    path("<uuid:pk>/status/", views.status_update, name="status_update"),
    # P03a: JD 분석
    path("<uuid:pk>/analyze-jd/", views.analyze_jd, name="analyze_jd"),
    path("<uuid:pk>/jd-results/", views.jd_results, name="jd_results"),
    path("<uuid:pk>/drive-picker/", views.drive_picker, name="drive_picker"),
    path("<uuid:pk>/start-search/", views.start_search_session, name="start_search_session"),
    path("<uuid:pk>/matching/", views.jd_matching_results, name="jd_matching_results"),
]
```

---

## Step 8: 템플릿

### projects/templates/projects/partials/jd_analysis_result.html

```html
<div id="jd-analysis-result" class="space-y-4">
  {% if analysis.requirements %}
  <div class="bg-white rounded-lg border border-gray-100 p-5">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-[15px] font-semibold text-gray-700">JD 분석 결과</h3>
      <div class="flex items-center gap-2">
        <button hx-post="{% url 'projects:analyze_jd' project.pk %}"
                hx-target="#jd-analysis-result"
                hx-swap="outerHTML"
                class="text-[13px] text-primary hover:text-primary-dark">
          재분석
        </button>
      </div>
    </div>

    {% with reqs=analysis.requirements %}
    <div class="space-y-3">
      {% if reqs.position %}
      <div class="flex items-start justify-between">
        <span class="text-[14px] text-gray-500 w-24 shrink-0">포지션</span>
        <span class="text-[14px] text-gray-800 text-right">{{ reqs.position }}</span>
      </div>
      {% endif %}

      {% if reqs.min_experience_years or reqs.max_experience_years %}
      <div class="flex items-start justify-between">
        <span class="text-[14px] text-gray-500 w-24 shrink-0">경력</span>
        <span class="text-[14px] text-gray-800 text-right">
          {% if reqs.min_experience_years and reqs.max_experience_years %}
            {{ reqs.min_experience_years }}~{{ reqs.max_experience_years }}년
          {% elif reqs.min_experience_years %}
            {{ reqs.min_experience_years }}년 이상
          {% else %}
            {{ reqs.max_experience_years }}년 이하
          {% endif %}
        </span>
      </div>
      {% endif %}

      {% if reqs.education_fields %}
      <div class="flex items-start justify-between">
        <span class="text-[14px] text-gray-500 w-24 shrink-0">전공</span>
        <span class="text-[14px] text-gray-800 text-right">
          {{ reqs.education_fields|join:", " }}
        </span>
      </div>
      {% endif %}

      {% if reqs.keywords %}
      <div class="flex items-start">
        <span class="text-[14px] text-gray-500 w-24 shrink-0">키워드</span>
        <div class="flex flex-wrap gap-1.5">
          {% for kw in reqs.keywords %}
          <span class="px-2 py-0.5 bg-blue-50 text-blue-700 text-[12px] rounded-full">{{ kw }}</span>
          {% endfor %}
        </div>
      </div>
      {% endif %}

      {% if reqs.role_summary %}
      <div class="pt-2 border-t border-gray-50">
        <span class="text-[14px] text-gray-500 block mb-1">직무 요약</span>
        <p class="text-[14px] text-gray-700">{{ reqs.role_summary }}</p>
      </div>
      {% endif %}
    </div>
    {% endwith %}

    <!-- Action buttons -->
    <div class="mt-4 pt-4 border-t border-gray-100 flex items-center gap-3">
      <form method="post" action="{% url 'projects:start_search_session' project.pk %}">
        {% csrf_token %}
        <button type="submit"
                class="px-4 py-2 bg-primary text-white text-[14px] font-medium rounded-lg hover:bg-primary-dark transition">
          후보자 서칭
        </button>
      </form>
      <button hx-get="{% url 'projects:jd_matching_results' project.pk %}"
              hx-target="#matching-results"
              hx-swap="outerHTML"
              class="px-4 py-2 border border-gray-300 text-gray-700 text-[14px] font-medium rounded-lg hover:bg-gray-50 transition">
        매칭 결과 보기
      </button>
    </div>
  </div>
  {% else %}
  <div class="bg-gray-50 rounded-lg p-4 text-center">
    <p class="text-[14px] text-gray-500">분석 결과가 없습니다.</p>
  </div>
  {% endif %}
</div>
```

### projects/templates/projects/partials/jd_analysis_error.html

```html
<div class="bg-red-50 border border-red-200 rounded-lg p-4">
  <p class="text-[14px] text-red-600">{{ error }}</p>
  <button hx-post="{% url 'projects:analyze_jd' project.pk %}"
          hx-target="#jd-analysis-result"
          hx-swap="outerHTML"
          class="mt-2 text-[13px] text-red-500 hover:text-red-700 underline">
    다시 시도
  </button>
</div>
```

### projects/templates/projects/partials/jd_matching_results.html

```html
<div id="matching-results" class="space-y-3">
  <h3 class="text-[15px] font-semibold text-gray-700">매칭 후보자 (상위 {{ results|length }}명)</h3>

  {% for item in results %}
  <div class="bg-white rounded-lg border border-gray-100 p-4 flex items-center justify-between">
    <div>
      <span class="text-[14px] font-medium text-gray-800">{{ item.candidate.name }}</span>
      <span class="text-[13px] text-gray-500 ml-2">
        {{ item.candidate.current_company }} · {{ item.candidate.current_position }}
      </span>
    </div>
    <div class="flex items-center gap-2">
      <span class="text-[13px] font-medium
        {% if item.level == '높음' %}text-green-600
        {% elif item.level == '보통' %}text-yellow-600
        {% else %}text-red-500{% endif %}">
        {{ item.level }} ({{ item.score|floatformat:0 }}%)
      </span>
    </div>
  </div>
  {% empty %}
  <p class="text-[14px] text-gray-400">매칭되는 후보자가 없습니다.</p>
  {% endfor %}
</div>
```

### projects/templates/projects/partials/jd_matching_empty.html

```html
<div id="matching-results" class="bg-gray-50 rounded-lg p-4 text-center">
  <p class="text-[14px] text-gray-500">JD 분석을 먼저 수행해주세요.</p>
</div>
```

### projects/templates/projects/partials/jd_drive_picker.html

```html
<div class="space-y-3">
  {% if error %}
  <div class="bg-red-50 border border-red-200 rounded-lg p-3">
    <p class="text-[13px] text-red-600">{{ error }}</p>
  </div>
  {% endif %}

  {% if success %}
  <div class="bg-green-50 border border-green-200 rounded-lg p-3">
    <p class="text-[13px] text-green-600">Drive 파일에서 텍스트가 추출되었습니다.</p>
  </div>
  {% endif %}

  {% if drive_files %}
  <div class="max-h-60 overflow-y-auto space-y-1">
    {% for file in drive_files %}
    <form method="post" action="{% url 'projects:drive_picker' project.pk %}" class="inline">
      {% csrf_token %}
      <input type="hidden" name="file_id" value="{{ file.id }}">
      <button type="submit"
              class="w-full text-left px-3 py-2 rounded hover:bg-gray-50 transition flex items-center gap-2">
        <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
        </svg>
        <span class="text-[14px] text-gray-700">{{ file.name }}</span>
      </button>
    </form>
    {% endfor %}
  </div>
  {% else %}
  <p class="text-[14px] text-gray-400">Drive에서 파일을 찾을 수 없습니다.</p>
  {% endif %}
</div>
```

### project_detail.html 수정

프로젝트 상세 화면의 JD 섹션 뒤에 분석 결과 섹션 추가:

```html
<!-- JD Analysis Section (P03a) -->
<section class="bg-white rounded-lg border border-gray-100 p-5">
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-[15px] font-semibold text-gray-500">JD 분석</h2>
    {% if project.jd_text or project.jd_file or project.jd_raw_text %}
    <button hx-post="{% url 'projects:analyze_jd' project.pk %}"
            hx-target="#jd-analysis-result"
            hx-swap="outerHTML"
            class="text-[13px] text-primary hover:text-primary-dark font-medium transition">
      {% if project.jd_analysis %}재분석{% else %}분석 시작{% endif %}
    </button>
    {% endif %}
  </div>

  <div id="jd-analysis-result">
    {% if project.jd_analysis %}
      {% include "projects/partials/jd_analysis_result.html" with analysis=project %}
    {% elif project.jd_text or project.jd_file or project.jd_raw_text %}
      <p class="text-[14px] text-gray-400">분석을 시작해주세요.</p>
    {% else %}
      <p class="text-[14px] text-gray-400">JD를 먼저 등록해주세요.</p>
    {% endif %}
  </div>
</section>

<!-- Matching Results Section -->
<div id="matching-results"></div>
```

---

## Step 9: 뷰 테스트

```python
# tests/test_jd_views.py

import pytest
from django.test import Client as TestClient
from django.urls import reverse
from unittest.mock import patch, MagicMock


@pytest.mark.django_db
class TestAnalyzeJDView:
    def test_requires_login(self, client):
        """비인증 시 redirect."""
        url = reverse("projects:analyze_jd", kwargs={"pk": "00000000-0000-0000-0000-000000000001"})
        response = client.post(url)
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_org_isolation(self, authenticated_client, other_org_project):
        """타 조직 프로젝트 접근 시 404."""
        url = reverse("projects:analyze_jd", kwargs={"pk": other_org_project.pk})
        response = authenticated_client.post(url)
        assert response.status_code == 404

    @patch("projects.services.jd_analysis.analyze_jd")
    def test_successful_analysis(self, mock_analyze, authenticated_client, project_with_jd):
        """정상 분석 시 결과 partial 반환."""
        mock_analyze.return_value = {
            "requirements": {"position": "개발자"},
            "full_analysis": {"position": "개발자"},
        }
        url = reverse("projects:analyze_jd", kwargs={"pk": project_with_jd.pk})
        response = authenticated_client.post(url)
        assert response.status_code == 200

    @patch("projects.services.jd_analysis.analyze_jd")
    def test_no_text_error(self, mock_analyze, authenticated_client, project_no_jd):
        """JD 텍스트 없으면 에러 표시."""
        mock_analyze.side_effect = ValueError("분석할 JD 텍스트가 없습니다.")
        url = reverse("projects:analyze_jd", kwargs={"pk": project_no_jd.pk})
        response = authenticated_client.post(url)
        assert response.status_code == 200
        assert "분석할 JD 텍스트가 없습니다" in response.content.decode()


@pytest.mark.django_db
class TestStartSearchSession:
    def test_creates_session_and_redirects(self, authenticated_client, project_with_analysis):
        """requirements 있으면 SearchSession 생성 후 redirect."""
        url = reverse("projects:start_search_session", kwargs={"pk": project_with_analysis.pk})
        response = authenticated_client.post(url)
        assert response.status_code == 302
        assert "session_id=" in response.url

    def test_no_requirements_error(self, authenticated_client, project_no_jd):
        """requirements 없으면 에러."""
        url = reverse("projects:start_search_session", kwargs={"pk": project_no_jd.pk})
        response = authenticated_client.post(url)
        assert response.status_code == 200
```

---

## 구현 순서 요약

| Step | 작업 | 의존성 |
|------|------|--------|
| 1 | 모델 변경 + migration | 없음 |
| 2 | PDF 텍스트 추출 + 의존성 추가 | 없음 |
| 3 | JD 분석 서비스 (jd_analysis.py, jd_prompts.py) | Step 1, 2 |
| 4 | 후보자 매칭 서비스 (candidate_matching.py) | Step 3 |
| 5 | 폼 확장 + validation | Step 1 |
| 6 | 뷰 추가 | Step 3, 4, 5 |
| 7 | URL 등록 | Step 6 |
| 8 | 템플릿 | Step 6, 7 |
| 9 | 뷰 테스트 | Step 6, 7, 8 |

**병렬 가능 그룹:**
- Group A: Step 1, 2 (독립)
- Group B: Step 3, 4 (Step 1, 2 완료 후 병렬 가능)
- Group C: Step 5, 6, 7, 8 (Step 3, 4 완료 후 순차)
- Group D: Step 9 (마지막)

---

## 확립된 패턴 준수 확인

- [x] Organization 격리: 모든 뷰에서 `_get_org(request)` + `organization=org` 필터
- [x] @login_required: 모든 뷰
- [x] 동적 extends: 필요한 full-page 템플릿에 적용
- [x] HTMX target: `#main-content` (전체 네비), 분석 결과는 `#jd-analysis-result`
- [x] UI 텍스트: 한국어 존대말
- [x] 삭제 보호: 해당 없음 (분석은 덮어쓰기)
- [x] UUID primary keys: BaseModel 상속
- [x] Gemini 패턴: _get_gemini_client(), max_retries, parse_llm_json()
- [x] 에러 처리: Gemini 실패 → 사용자 메시지, 기존 데이터 보존

<!-- forge:p03a:구현담금질:complete:2026-04-08T12:00:00+09:00 -->
