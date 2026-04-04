"""Gemini 3.1 Flash extraction for resume parsing pipeline.

Main extraction module -- parses Korean resumes into structured JSON
using the same prompt/schema as the legacy Sonnet pipeline.
"""

import json
import logging

from django.conf import settings
from google import genai

from data_extraction.services.extraction.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    build_extraction_prompt,
)

_KO_PRIORITY = (
    "\n7. 이름(name)은 반드시 한국어로 반환하세요. 영문 이름은 name_en에만 넣으세요."
    "\n8. 회사명, 학교명 등 한국어 원본이 있으면 한국어를 우선 사용하세요."
)
GEMINI_SYSTEM_PROMPT = EXTRACTION_SYSTEM_PROMPT + _KO_PRIORITY

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"


def _get_gemini_client() -> genai.Client:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in settings")
    return genai.Client(api_key=api_key)


def extract_candidate_data(
    resume_text: str,
    max_retries: int = 3,
    file_reference_date: str | None = None,
) -> dict | None:
    """Extract structured candidate data from resume text using Gemini 3.1 Flash.

    Args:
        resume_text: Raw text extracted from a resume file.
        max_retries: Maximum number of retry attempts on failure.

    Returns:
        Parsed dict with candidate data, or None if all retries fail.
    """
    client = _get_gemini_client()
    user_prompt = build_extraction_prompt(
        resume_text,
        file_reference_date=file_reference_date,
    )

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=GEMINI_SYSTEM_PROMPT,
                    max_output_tokens=4000,
                    temperature=0.3,
                    response_mime_type="application/json",
                ),
            )

            result = json.loads(response.text)

            if not isinstance(result, dict) or "name" not in result:
                logger.warning(
                    "Gemini returned invalid structure (attempt %d/%d): missing 'name' key",
                    attempt + 1,
                    max_retries,
                )
                continue

            return result

        except Exception:
            logger.warning(
                "Gemini extraction failed (attempt %d/%d)",
                attempt + 1,
                max_retries,
                exc_info=True,
            )

    return None
