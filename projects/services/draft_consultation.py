"""상담 내용 처리 (직접 입력 정리, AI 정리)."""

import logging

from django.conf import settings
from google import genai

from data_extraction.services.extraction.sanitizers import parse_llm_json

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

CONSULTATION_SYSTEM_PROMPT = """\
당신은 헤드헌팅 상담 내용을 정리하는 전문가입니다.
컨설턴트가 후보자와 상담한 내용을 구조화합니다.

## 출력 형식
JSON으로 응답합니다:
{
  "motivation": "이직 동기",
  "salary_expectation": "희망 연봉 관련 내용",
  "availability": "입사 가능 시기",
  "strengths": ["강점1"],
  "concerns": ["우려 사항1"],
  "additional_info": "기타 특이사항",
  "key_points": ["핵심 포인트1"]
}
"""


def summarize_consultation(draft) -> None:
    """상담 내용(직접 입력 + transcript)을 AI로 정리."""
    # 입력 소스 병합
    parts = []
    if draft.consultation_input:
        parts.append(f"[직접 입력]\n{draft.consultation_input}")
    if draft.consultation_transcript:
        parts.append(f"[녹음 내용]\n{draft.consultation_transcript}")

    if not parts:
        return  # 입력 없으면 정리할 것 없음

    combined = "\n\n".join(parts)

    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"아래 상담 내용을 정리해주세요:\n\n{combined}",
        config=genai.types.GenerateContentConfig(
            system_instruction=CONSULTATION_SYSTEM_PROMPT,
            max_output_tokens=4000,
            temperature=0.3,
            response_mime_type="application/json",
        ),
    )

    result = parse_llm_json(response.text)
    if isinstance(result, dict):
        draft.consultation_summary = result
        draft.save(update_fields=["consultation_summary", "updated_at"])
