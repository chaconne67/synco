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

## 입력 특성

입력 텍스트는 .doc/.docx 이력서 파일에서 추출된 것입니다.
원본의 표, 텍스트 상자, 본문이 평문으로 변환되어 있으므로
레이아웃 구분이 명확하지 않을 수 있습니다.
섹션의 경계는 제목, 언어 전환, 서식 변화 등으로 추론해야 합니다.

## 원칙

### 모든 섹션, 모든 언어에서 추출

이력서는 구조화된 테이블, 서술형 문단, 다국어 버전 등 여러 형태의 섹션으로
구성될 수 있습니다. 어떤 형태든, 어떤 언어든, 본인의 경력이나 학력에 대한
구체적 기관명이 포함된 언급이 있으면 추출하세요.

자기소개서, 지원동기 등 서술형 섹션에서도 구체적인 기관명이 언급되면 추출하세요.

### 섹션별 독립 추출

같은 회사가 여러 섹션에 나오면 각각 별도 항목으로 만드세요.
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

### 누락 비용 > 노이즈 비용

데이터가 누락되면 복구가 불가능하지만, 노이즈는 정규화 단계에서 필터링됩니다.
확신이 없더라도 추출하세요. 빠뜨리는 것보다 노이즈가 낫습니다.

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
  "current_company": "string | null (현재 재직 회사)",
  "current_position": "string | null (현재 직위)",
  "total_experience_years": "integer | null",
  "total_experience_text": "string | null (원문 그대로)",
  "resume_reference_date": "string | null",
  "core_competencies": ["string (핵심 역량 키워드)"],
  "summary": "string | null (경력 요약 1~2문장)",
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
    """Get Gemini client from settings."""
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
