"""LLM-based structured extraction from resume text.

Uses common/llm.py's call_llm_json() to parse Korean resumes into
a structured dict with field-level confidence scores.
"""

import logging

from common.llm import call_llm_json

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = (
    "당신은 한국어 이력서 파싱 전문가입니다. "
    "이력서 텍스트를 분석하여 구조화된 JSON으로 변환합니다.\n\n"
    "규칙:\n"
    "1. 데이터가 없는 필드는 빈 문자열, 빈 배열, 또는 null로 반환하세요.\n"
    "2. 2자리 연도는 4자리로 변환하세요 (예: '85 → 1985, '03 → 2003).\n"
    "3. 경력(careers)은 최신순으로 정렬하고 order 값을 0부터 부여하세요.\n"
    "4. 현재 재직 중인 직장은 is_current=true로 표시하세요.\n"
    "5. 각 필드별 신뢰도 점수(field_confidences)를 0.0~1.0 사이로 반환하세요.\n"
    "6. JSON만 출력하세요. 설명이나 마크다운은 포함하지 마세요."
)

EXTRACTION_JSON_SCHEMA = """{
  "name": "string (이름)",
  "name_en": "string | null (영문 이름)",
  "birth_year": "integer | null (출생연도 4자리)",
  "gender": "string | null (male/female)",
  "email": "string | null",
  "phone": "string | null",
  "address": "string | null",
  "current_company": "string | null (현재 재직 회사명)",
  "current_position": "string | null (현재 직위)",
  "total_experience_years": "integer | null (총 경력 연수)",
  "core_competencies": ["string (핵심 역량 키워드)"],
  "summary": "string | null (경력 요약 1~2문장)",
  "educations": [
    {
      "institution": "string (학교명)",
      "degree": "string | null (학위: 학사/석사/박사)",
      "major": "string | null (전공)",
      "gpa": "number | null",
      "start_year": "integer | null",
      "end_year": "integer | null",
      "is_abroad": "boolean (해외 학력 여부)"
    }
  ],
  "careers": [
    {
      "company": "string (회사명)",
      "company_en": "string | null (영문 회사명)",
      "position": "string | null (직위)",
      "department": "string | null (부서)",
      "start_date": "string | null (YYYY-MM 형식)",
      "end_date": "string | null (YYYY-MM 형식, 현재 재직 시 null)",
      "is_current": "boolean (현재 재직 여부)",
      "duties": "string | null (담당 업무)",
      "achievements": "string | null (주요 성과)",
      "order": "integer (최신순 0부터)"
    }
  ],
  "certifications": [
    {
      "name": "string (자격증명)",
      "issuer": "string | null (발급기관)",
      "acquired_date": "string | null (YYYY-MM 형식)"
    }
  ],
  "language_skills": [
    {
      "language": "string (언어명)",
      "test_name": "string | null (시험명: TOEIC, JLPT 등)",
      "score": "string | null (점수)",
      "level": "string | null (등급)"
    }
  ],
  "field_confidences": {
    "name": "float 0.0-1.0",
    "birth_year": "float 0.0-1.0",
    "careers": "float 0.0-1.0",
    "educations": "float 0.0-1.0",
    "certifications": "float 0.0-1.0",
    "overall": "float 0.0-1.0"
  }
}"""


def build_extraction_prompt(resume_text: str) -> str:
    """Build prompt containing the JSON schema and the resume text.

    Asks the LLM for JSON-only output.
    """
    return (
        "아래 이력서 텍스트를 분석하여 다음 JSON 스키마에 맞게 구조화하세요.\n\n"
        f"## 출력 JSON 스키마\n```\n{EXTRACTION_JSON_SCHEMA}\n```\n\n"
        f"## 이력서 텍스트\n```\n{resume_text}\n```\n\n"
        "위 스키마에 맞는 JSON만 출력하세요. 다른 텍스트는 포함하지 마세요."
    )


def extract_candidate_data(resume_text: str, max_retries: int = 3) -> dict | None:
    """Extract structured candidate data from resume text using LLM.

    Args:
        resume_text: Raw text extracted from a resume file.
        max_retries: Maximum number of retry attempts on failure.

    Returns:
        Parsed dict with candidate data, or None if all retries fail
        or the response is invalid.
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

            # Validate: must be a dict with a "name" key
            if not isinstance(result, dict) or "name" not in result:
                logger.warning(
                    "LLM returned invalid structure (attempt %d/%d): missing 'name' key",
                    attempt + 1,
                    max_retries,
                )
                return None

            return result

        except Exception:
            logger.warning(
                "LLM extraction failed (attempt %d/%d)",
                attempt + 1,
                max_retries,
                exc_info=True,
            )

    return None
