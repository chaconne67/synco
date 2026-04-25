"""OpenAI GPT extraction for resume parsing pipeline.

Alternative provider to Gemini — uses the same prompts/schema,
selectable via --provider openai on the extract command.
"""

import logging

from django.conf import settings
from openai import OpenAI

from data_extraction.services.extraction.sanitizers import parse_llm_json
from data_extraction.services.extraction.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    build_extraction_prompt,
)

_KO_PRIORITY = (
    "\n\n## 한국어 우선 규칙 (위 1~10번 규칙에 추가):"
    "\n- 이름(name)은 반드시 한국어로 반환하세요. 영문 이름은 name_en에만 넣으세요."
    "\n- 회사명, 학교명 등 한국어 원본이 있으면 한국어를 우선 사용하세요."
)
OPENAI_SYSTEM_PROMPT = EXTRACTION_SYSTEM_PROMPT + _KO_PRIORITY

logger = logging.getLogger(__name__)

OPENAI_MODEL = "gpt-5.4-nano"


def _get_openai_client() -> OpenAI:
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in settings")
    return OpenAI(api_key=api_key)


def extract_candidate_data(
    resume_text: str,
    max_retries: int = 3,
    file_reference_date: str | None = None,
) -> dict | None:
    """Extract structured candidate data from resume text using OpenAI GPT.

    Args:
        resume_text: Raw text extracted from a resume file.
        max_retries: Maximum number of retry attempts on failure.
        file_reference_date: File modification date for context.

    Returns:
        Parsed dict with candidate data, or None if all retries fail.
    """
    client = _get_openai_client()
    user_prompt = build_extraction_prompt(
        resume_text,
        file_reference_date=file_reference_date,
    )

    from data_extraction.services.extraction import telemetry

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": OPENAI_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_completion_tokens=4000,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            telemetry.add_from_openai_response(response)

            result = parse_llm_json(response.choices[0].message.content)

            if not isinstance(result, dict) or "name" not in result:
                logger.warning(
                    "OpenAI returned invalid structure (attempt %d/%d): missing 'name' key",
                    attempt + 1,
                    max_retries,
                )
                continue

            return result

        except Exception:
            logger.warning(
                "OpenAI extraction failed (attempt %d/%d)",
                attempt + 1,
                max_retries,
                exc_info=True,
            )

    return None


def call_openai(
    system: str, prompt: str, max_completion_tokens: int = 6000
) -> dict | None:
    """Generic OpenAI call with JSON response — used by integrity pipeline."""
    from data_extraction.services.extraction import telemetry

    client = _get_openai_client()
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=max_completion_tokens,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        telemetry.add_from_openai_response(response)
        return parse_llm_json(response.choices[0].message.content)
    except Exception:
        logger.warning("OpenAI call failed", exc_info=True)
        return None
