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
                    attempt + 1,
                    max_retries,
                )
                continue

            return {
                "full_analysis": parsed,
                "requirements": parsed,
            }

        except Exception:
            logger.warning(
                "Gemini JD analysis failed (attempt %d/%d)",
                attempt + 1,
                max_retries,
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
        "position_keywords": (
            [requirements["position"]] if requirements.get("position") else []
        ),
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
