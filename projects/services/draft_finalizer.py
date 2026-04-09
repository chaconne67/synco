"""AI 최종 정리 (초안 + 상담 병합)."""

import json
import logging

from django.conf import settings
from google import genai

from data_extraction.services.extraction.sanitizers import parse_llm_json

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

FINALIZE_SYSTEM_PROMPT = """\
당신은 헤드헌팅 추천 서류 최종 정리 전문가입니다.
AI 초안과 상담 내용을 병합하여 최종 추천 서류 데이터를 완성합니다.

## 규칙
1. 초안의 구조를 유지하되, 상담 내용을 반영하여 보완합니다.
2. 이직 동기, 강점, 희망 연봉 등 상담에서 얻은 정보를 적절한 섹션에 추가합니다.
3. 상담 내용과 초안이 충돌하면 상담 내용을 우선합니다 (최신 정보).
4. 출력은 초안과 동일한 JSON 구조입니다 (corrections 제외).
"""


def finalize_draft(draft) -> None:
    """초안 + 상담 병합 -> final_content_json 저장."""
    if not draft.auto_draft_json:
        raise RuntimeError("초안이 생성되지 않았습니다.")

    prompt_parts = [
        f"## AI 초안\n{json.dumps(draft.auto_draft_json, ensure_ascii=False, indent=2)}"
    ]

    if draft.consultation_summary:
        prompt_parts.append(
            f"## 상담 정리\n"
            f"{json.dumps(draft.consultation_summary, ensure_ascii=False, indent=2)}"
        )
    if draft.consultation_input:
        prompt_parts.append(f"## 상담 원문 (참고용)\n{draft.consultation_input}")

    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=(
            "아래 초안과 상담 내용을 병합하여 "
            "최종 추천 서류 데이터를 완성하세요.\n\n" + "\n\n".join(prompt_parts)
        ),
        config=genai.types.GenerateContentConfig(
            system_instruction=FINALIZE_SYSTEM_PROMPT,
            max_output_tokens=8000,
            temperature=0.3,
            response_mime_type="application/json",
        ),
    )

    result = parse_llm_json(response.text)
    if not isinstance(result, dict):
        raise RuntimeError("AI 최종 정리에 실패했습니다.")

    draft.final_content_json = result
    draft.save(update_fields=["final_content_json", "updated_at"])
