"""Step 1.5: Semantic grouping of raw extracted items by same company/school.

Calls Gemini to identify which raw career/education entries refer to the same
institution, producing groups that Step 2 will normalize independently.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from candidates.services.integrity.step1_extract import _call_gemini

logger = logging.getLogger(__name__)

GROUPING_SYSTEM_PROMPT = """\
당신은 이력서 데이터의 시맨틱 그루핑 전문가입니다.

# 역할
추출된 이력서 항목들 중 **동일한 회사/학교를 가리키는 항목**을 그룹으로 묶어주세요.

# 핵심 원칙
1. **병합 금지**: 데이터를 합치거나 수정하지 마세요. 어떤 항목들이 같은 그룹인지만 식별합니다.
2. **다음 단계에서 정규화**: 그루핑 결과를 바탕으로 다음 단계에서 각 그룹을 독립적으로 정규화합니다.
3. **그루핑 실패 비용**: 잘못된 그루핑 > 잘못된 병합. 확신이 없으면 미분류(ungrouped)로 남기세요.

# 그루핑 기준
- **같은 기관, 다른 언어** → same_company (예: "삼성전자" + "Samsung Electronics")
- **모기간 + 세부기간** → parent_with_sub_periods (예: "삼성전자 2000-2010" + "삼성전자 메모리사업부 2005-2008")
- **계열사/그룹사** → affiliated_group (예: "삼성카드" + "삼성그룹 T/F")
- **확신 없음** → ungrouped에 남기기 (잘못 묶는 것보다 안전)

# 출력 형식
JSON으로 응답하세요. 설명 텍스트 없이 JSON만 출력하세요.
"""

GROUPING_SCHEMA: dict[str, Any] = {
    "career_groups": [
        {
            "group_id": "str — 고유 그룹 ID (예: cg_1)",
            "canonical_name": "str — 대표 회사명",
            "relationship": "same_company|parent_with_sub_periods|affiliated_group",
            "entry_indices": ["int — 원본 careers 배열의 인덱스"],
        }
    ],
    "education_groups": [
        {
            "group_id": "str — 고유 그룹 ID (예: eg_1)",
            "canonical_name": "str — 대표 기관명",
            "entry_indices": ["int — 원본 educations 배열의 인덱스"],
        }
    ],
    "ungrouped_career_indices": ["int — 어떤 그룹에도 속하지 않는 career 인덱스"],
    "ungrouped_education_indices": ["int — 어떤 그룹에도 속하지 않는 education 인덱스"],
}


def _build_summary(raw_data: dict) -> str:
    """Build a lightweight summary of careers and educations for the LLM.

    Sends only the fields needed for grouping decisions, not the full raw data.
    """
    lines: list[str] = []

    careers = raw_data.get("careers", [])
    if careers:
        lines.append("## Careers")
        for i, c in enumerate(careers):
            company = c.get("company", "") or c.get("organization", "") or "?"
            start = c.get("start_date", "?")
            end = c.get("end_date", "현재") if c.get("is_current") else c.get("end_date", "?")
            source = c.get("source_section", "")
            line = f"[{i}] {company} | {start}~{end}"
            if source:
                line += f" | source: {source}"
            lines.append(line)

    educations = raw_data.get("educations", [])
    if educations:
        lines.append("\n## Educations")
        for i, e in enumerate(educations):
            institution = e.get("institution", "") or e.get("school", "") or "?"
            start = e.get("start_year", "?")
            end = e.get("end_year", "?")
            source = e.get("source_section", "")
            line = f"[{i}] {institution} | {start}~{end}"
            if source:
                line += f" | source: {source}"
            lines.append(line)

    return "\n".join(lines)


def group_raw_data(
    raw_data: dict,
    *,
    feedback: str | None = None,
) -> dict | None:
    """Group raw extracted items by same company/school using Gemini.

    Args:
        raw_data: Raw extraction result with 'careers' and 'educations' lists.
        feedback: Optional feedback from a previous attempt (for retry).

    Returns:
        Grouping dict matching GROUPING_SCHEMA, or None on failure.
    """
    careers = raw_data.get("careers", [])
    educations = raw_data.get("educations", [])

    # Nothing to group
    if not careers and not educations:
        return {
            "career_groups": [],
            "education_groups": [],
            "ungrouped_career_indices": [],
            "ungrouped_education_indices": [],
        }

    summary = _build_summary(raw_data)

    user_message_parts = [
        "다음 이력서 항목들을 분석하여 동일 기관을 가리키는 항목들을 그루핑해주세요.",
        "",
        summary,
        "",
        "출력 스키마:",
        json.dumps(GROUPING_SCHEMA, ensure_ascii=False, indent=2),
    ]

    if feedback:
        user_message_parts.extend([
            "",
            "## 이전 시도 피드백",
            feedback,
        ])

    user_message = "\n".join(user_message_parts)

    try:
        result = _call_gemini(GROUPING_SYSTEM_PROMPT, user_message, max_tokens=2000)
    except Exception:
        logger.exception("Gemini call failed during grouping")
        return None

    if result is None:
        logger.warning("Gemini returned None for grouping")
        return None

    # Validate required keys
    required_keys = {
        "career_groups",
        "education_groups",
        "ungrouped_career_indices",
        "ungrouped_education_indices",
    }
    if not required_keys.issubset(result.keys()):
        missing = required_keys - set(result.keys())
        logger.warning("Grouping result missing keys: %s", missing)
        return None

    return result
