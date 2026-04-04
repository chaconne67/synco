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
    "핵심 원칙:\n"
    "- duties와 achievements는 이력서 본문에 명시적으로 기재된 내용만 추출하세요. "
    "기재되지 않았으면 null로 반환하세요.\n"
    "- inferred_capabilities는 직책·부서·경력 수준을 바탕으로 "
    "이 사람이 수행할 수 있을 것으로 예상되는 역량을 추정하세요. "
    "duties가 이미 상세히 기재된 경우에는 null로 반환하세요.\n\n"
    "규칙:\n"
    "1. 데이터가 없는 필드는 빈 문자열, 빈 배열, 또는 null로 반환하세요.\n"
    "2. 2자리 연도는 4자리로 변환하세요 (예: '85 → 1985, '03 → 2003).\n"
    "3. 경력(careers)은 최신순으로 정렬하고 order 값을 0부터 부여하세요.\n"
    "4. 현재 재직 중인 직장은 is_current=true로 표시하세요.\n"
    "5. 각 필드별 신뢰도 점수(field_confidences)를 0.0~1.0 사이로 반환하세요.\n"
    "6. 이력서 본문에 작성일/수정일/제출일이 명시된 경우에만 "
    "resume_reference_date에 YYYY-MM 또는 YYYY-MM-DD 형식으로 반환하세요.\n"
    "7. resume_reference_date는 문서 안의 명시적 근거가 있을 때만 채우고, "
    "경력 기간만 보고 추정하지 마세요.\n"
    "8. 경력 기간이 '2004/06 ~', '(1년 7개월)'처럼 불완전하게 적혀 있으면, "
    "duration_text, end_date_inferred, date_evidence, date_confidence에 근거와 추정값을 함께 반환하세요.\n"
    "9. end_date_inferred는 start_date와 duration_text 등 문서 안 근거로 합리적으로 계산 가능한 경우에만 채우세요.\n"
    "10. JSON만 출력하세요. 설명이나 마크다운은 포함하지 마세요.\n\n"
    "### skills vs core_competencies 구분\n\n"
    "skills에는 이력서 전체에서 언급된 특정 기술·도구·시스템의 고유명사를 추출하세요.\n"
    "이 데이터는 후보자 검색 시 기술 키워드 매칭에 사용됩니다.\n"
    "구체적 명칭이 대상이고, 일반적 역량 서술(\"의사소통 능력\", \"리더십\")은 core_competencies에 넣으세요.\n\n"
    "구분 원칙: 그 단어로 검색했을 때 해당 기술을 가진 사람만 나와야 하면 skills, "
    "다수의 사람에게 해당하는 일반적 역량이면 core_competencies.\n\n"
    "### skills 표기 정규화\n\n"
    "- 영문 공식 명칭을 우선 사용하세요: \"파이썬\" → \"Python\", \"오라클\" → \"Oracle\"\n"
    "- 공식 표기를 따르세요: \"MSSQL\" → \"MS SQL Server\", \"C++\" (O), \"씨플플\" (X)\n"
    "- 약어가 널리 쓰이면 약어를 사용하세요: \"SAP\", \"PMP\", \"ISO 9001\"\n"
    "- 한글만 존재하는 고유명사는 한글 그대로\n\n"
    "### etc[] 필드 사용 원칙\n\n"
    "이력서의 모든 정보는 4개 카테고리 중 하나에 반드시 속합니다:\n"
    "- 인적사항: 이 사람이 누구인지에 관한 정보 → personal_etc\n"
    "- 학력: 무엇을 배웠는지에 관한 정보 → education_etc\n"
    "- 경력: 어떤 일을 했는지에 관한 정보 → career_etc\n"
    "- 능력: 무엇을 할 수 있는지에 관한 정보 → skills_etc\n\n"
    "각 카테고리에서 핵심 필드에 맞지 않지만 해당 카테고리에 속하는 정보는 etc[]에 넣으세요.\n"
    "원본에 있는 정보는 반드시 어딘가에 포함되어야 합니다. 누락보다 중복이 낫습니다.\n"
    "etc[] 항목에는 반드시 type을 넣어 무엇인지 식별할 수 있게 하세요.\n"
    "etc[] 항목의 type과 description은 한국어로 작성하세요. 원문이 영어인 경우 한국어로 번역하세요."
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
  "resume_reference_date": "string | null (이력서 작성/수정/제출 기준일, YYYY-MM 또는 YYYY-MM-DD)",
  "resume_reference_date_source": "string | null (document_text when explicitly stated in the resume)",
  "resume_reference_date_evidence": "string | null (기준일을 판단한 문서 내 근거 문구)",
  "core_competencies": ["string (이력서에 명시된 핵심 역량 키워드만)"],
  "summary": "string | null (이력서에 기재된 내용 기반 경력 요약 1~2문장)",
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
      "duration_text": "string | null (원문에 적힌 기간 표현 예: 1년 7개월, 18개월)",
      "end_date_inferred": "string | null (문서 근거로 추정한 종료월, YYYY-MM 형식)",
      "date_evidence": "string | null (날짜/기간을 판단한 원문 근거)",
      "date_confidence": "float | null (0.0~1.0, 날짜 추정 신뢰도)",
      "is_current": "boolean (현재 재직 여부)",
      "duties": "string | null (이력서에 명시된 담당 업무만. 기재되지 않았으면 null)",
      "inferred_capabilities": "string | null (직책·부서·경력 수준으로 추정한 수행 가능 역량. duties가 상세히 기재된 경우 null)",
      "achievements": "string | null (이력서에 명시된 주요 성과만. 기재되지 않았으면 null)",
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
  "skills": ["string (기술·도구·시스템·방법론 등 고유명사 키워드, 영문 공식명 우선)"],
  "personal_etc": [{"type": "string", "description": "string"}],
  "education_etc": [{"type": "string", "title": "string", "institution": "string", "date": "string", "description": "string"}],
  "career_etc": [{"type": "string", "name": "string", "company": "string", "role": "string", "start_date": "string", "end_date": "string", "technologies": ["string"], "description": "string"}],
  "skills_etc": [{"type": "string", "title": "string", "description": "string", "date": "string"}],
  "field_confidences": {
    "name": "float 0.0-1.0",
    "birth_year": "float 0.0-1.0",
    "careers": "float 0.0-1.0",
    "educations": "float 0.0-1.0",
    "certifications": "float 0.0-1.0",
    "overall": "float 0.0-1.0"
  }
}"""


def build_extraction_prompt(
    resume_text: str,
    file_reference_date: str | None = None,
) -> str:
    """Build prompt containing the JSON schema and the resume text."""
    metadata_block = ""
    if file_reference_date:
        metadata_block = (
            "## 파일 메타데이터\n"
            f"- Drive modifiedTime: {file_reference_date}\n"
            "- 이 값은 애플리케이션 참고용입니다. 문서 본문에 작성/수정/제출일이 "
            "명시된 경우에만 resume_reference_date에 반영하세요.\n\n"
        )
    return (
        "아래 이력서 텍스트를 분석하여 다음 JSON 스키마에 맞게 구조화하세요.\n\n"
        f"## 출력 JSON 스키마\n```\n{EXTRACTION_JSON_SCHEMA}\n```\n"
        f"{metadata_block}"
        f"\n## 이력서 텍스트\n```\n{resume_text}\n```\n\n"
        "위 스키마에 맞는 JSON만 출력하세요. 다른 텍스트는 포함하지 마세요."
    )


def extract_candidate_data(
    resume_text: str,
    max_retries: int = 3,
    file_reference_date: str | None = None,
) -> dict | None:
    """Extract structured candidate data from resume text using Claude Sonnet.

    Legacy extraction function — kept for compare_extraction command.
    Main pipeline now uses gemini_extraction.extract_candidate_data().

    Args:
        resume_text: Raw text extracted from a resume file.
        max_retries: Maximum number of retry attempts on failure.

    Returns:
        Parsed dict with candidate data, or None if all retries fail
        or the response is invalid.
    """
    prompt = build_extraction_prompt(
        resume_text,
        file_reference_date=file_reference_date,
    )

    for attempt in range(max_retries):
        try:
            result = call_llm_json(
                prompt,
                system=EXTRACTION_SYSTEM_PROMPT,
                timeout=120,
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
