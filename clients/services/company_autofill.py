"""Company autofill via Gemini API + Google Search grounding.

Sends company name to Gemini to retrieve public company info
(industry, size, revenue, listing status, region).
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from google import genai
from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """다음 한국 기업의 정보를 조사해주세요: "{company_name}"

아래 JSON 형식으로만 응답하세요. 확인되지 않는 필드는 빈 문자열로 남기세요.
{{
  "industry": "업종 (예: 반도체, 금융, 건설)",
  "size_category": "대기업/중견/중소/외국계/스타트업 중 하나",
  "revenue_range": "연매출 규모 (예: 1조~5조)",
  "employee_count_range": "직원 수 규모 (예: 1000~5000명)",
  "listed": "KOSPI/KOSDAQ/비상장/해외상장 중 하나",
  "region": "본사 소재지 (예: 서울 강남구)"
}}"""

AUTOFILL_FIELDS = [
    "industry",
    "size_category",
    "revenue_range",
    "employee_count_range",
    "listed",
    "region",
]


def autofill_company(company_name: str) -> dict[str, str]:
    """Look up public company info via Gemini + Google Search.

    Args:
        company_name: Korean company name to look up.

    Returns:
        Dict with keys: industry, size_category, revenue_range,
        employee_count_range, listed, region. Empty string for unknown fields.

    Raises:
        RuntimeError: If Gemini API key is not configured.
        Exception: On API call failure (caller should handle).
    """
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in settings")

    client = genai.Client(api_key=api_key)
    google_search_tool = Tool(google_search=GoogleSearch())

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=_PROMPT_TEMPLATE.format(company_name=company_name),
        config=GenerateContentConfig(
            tools=[google_search_tool],
            temperature=0.1,
        ),
    )

    text = response.text.strip()
    # Extract JSON from response (may be wrapped in markdown code block)
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    data = json.loads(text)

    # Only return expected fields with string values
    result = {}
    for field in AUTOFILL_FIELDS:
        result[field] = str(data.get(field, "")).strip()
    return result
