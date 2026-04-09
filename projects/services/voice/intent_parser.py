"""Gemini-based intent parsing + entity extraction."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from django.conf import settings

from data_extraction.services.extraction.sanitizers import parse_llm_json

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-preview-05-20"

VALID_INTENTS = {
    "project_create",
    "contact_record",
    "contact_reserve",
    "submission_create",
    "interview_schedule",
    "offer_create",
    "status_query",
    "todo_query",
    "search_candidate",
    "navigate",
    "meeting_navigate",
    "unknown",
}

INTENT_SYSTEM_PROMPT = """\
당신은 헤드헌팅 플랫폼의 음성 명령 의도 파서입니다.
사용자의 음성 입력 텍스트를 분석하여 의도(intent)와 엔티티를 추출합니다.

가능한 intent 목록:
- project_create: 프로젝트 등록. 엔티티: client(str), title(str)
- contact_record: 컨택 결과 기록. 엔티티: candidate_name(str), channel(전화|문자|카톡|이메일|LinkedIn), contacted_at(ISO datetime, 없으면 null), result(응답|미응답|거절|관심|보류), notes(str, optional)
- contact_reserve: 컨택 예정 등록. 엔티티: candidate_names(list[str])
- submission_create: 추천 서류 생성. 엔티티: candidate_name(str), template(str, optional)
- interview_schedule: 면접 일정 등록. 엔티티: candidate_name(str), scheduled_at(ISO datetime), type(대면|화상|전화), location(str, optional)
- offer_create: 오퍼 등록. 엔티티: candidate_name(str), salary(str), position_title(str, optional)
- status_query: 현황 조회. 엔티티: project_name(str, optional)
- todo_query: 오늘 할 일. 엔티티: 없음
- search_candidate: 후보자 검색. 엔티티: keywords(str)
- navigate: 화면 이동. 엔티티: target_page(str)
- meeting_navigate: 미팅 녹음 업로드 화면 열기. 엔티티: candidate_name(str, optional)

규칙:
1. 확실하지 않으면 intent를 "unknown"으로 설정
2. 엔티티에서 이름은 원래 발화 그대로 유지 (UUID 변환하지 않음)
3. channel은 정확히 매칭되는 값 사용 (전화/문자/카톡/이메일/LinkedIn)
4. contacted_at이 명시되지 않으면 null
5. confidence는 0.0~1.0 사이 값

반드시 아래 JSON 형식으로만 응답:
{"intent": "string", "entities": {}, "confidence": 0.0}
"""

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


@dataclasses.dataclass
class IntentResult:
    intent: str
    entities: dict[str, Any]
    confidence: float
    missing_fields: list[str] = dataclasses.field(default_factory=list)


# Required entities per intent (for missing field detection)
# AMENDMENT A2: contacted_at added to contact_record, template added to submission_create
REQUIRED_ENTITIES: dict[str, list[str]] = {
    "project_create": ["client", "title"],
    "contact_record": ["candidate_name", "channel", "contacted_at", "result"],
    "contact_reserve": ["candidate_names"],
    "submission_create": ["candidate_name", "template"],
    "interview_schedule": ["candidate_name", "scheduled_at", "type"],
    "offer_create": ["candidate_name", "salary"],
    "search_candidate": ["keywords"],
    "navigate": ["target_page"],
}


def parse_intent(
    text: str,
    context: dict[str, Any],
) -> IntentResult:
    """Parse user text into intent + entities using Gemini.

    Args:
        text: Transcribed user speech.
        context: Resolved context from context_resolver.

    Returns:
        IntentResult with intent, entities, confidence, missing_fields.
    """
    user_prompt = f"현재 화면: {context.get('page', 'unknown')}\n"
    if context.get("project_title"):
        user_prompt += f"현재 프로젝트: {context['project_title']}\n"
    user_prompt += f"\n사용자 발화: {text}"

    try:
        client = _get_gemini_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                {"role": "user", "parts": [{"text": INTENT_SYSTEM_PROMPT + "\n\n" + user_prompt}]},
            ],
        )
        raw = response.text.strip()
        parsed = parse_llm_json(raw)

        if parsed is None:
            logger.warning("Failed to parse LLM JSON response: %s", raw[:200])
            return IntentResult(intent="unknown", entities={}, confidence=0.0)

        intent = parsed.get("intent", "unknown")
        if intent not in VALID_INTENTS:
            intent = "unknown"

        entities = parsed.get("entities", {})
        confidence = float(parsed.get("confidence", 0.0))

        # Detect missing required fields
        required = REQUIRED_ENTITIES.get(intent, [])
        missing = [f for f in required if not entities.get(f)]

        return IntentResult(
            intent=intent,
            entities=entities,
            confidence=confidence,
            missing_fields=missing,
        )
    except Exception:
        logger.exception("Intent parsing failed for: %s", text)
        return IntentResult(intent="unknown", entities={}, confidence=0.0)
