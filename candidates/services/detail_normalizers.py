"""Normalizers for candidate detail fields extracted from raw LLM JSON.

Each function maps various LLM output formats to a consistent structure.
These are used by both the backfill command and the import_resumes pipeline.
"""

from __future__ import annotations

from typing import Any


def normalize_military(data: Any) -> dict:
    """Normalize military service data.

    Returns: {branch, rank, start_date, end_date, status, unit, note}
    """
    if not data:
        return {}

    if isinstance(data, str):
        return {"note": data}

    if isinstance(data, list):
        # Some LLMs return a list of dicts; take the first or merge
        if len(data) == 1 and isinstance(data[0], dict):
            data = data[0]
        elif len(data) > 1:
            # Multiple entries: merge into a single dict with note
            return {
                "note": str(data),
                "entries": data,
            }
        else:
            return {}

    if not isinstance(data, dict):
        return {"note": str(data)}

    return {
        "branch": _str(data, "branch", "군별", "service_branch", "military_branch"),
        "rank": _str(data, "rank", "계급", "final_rank"),
        "start_date": _str(data, "start_date", "입대일", "enlistment_date", "시작일"),
        "end_date": _str(data, "end_date", "전역일", "discharge_date", "종료일"),
        "status": _str(
            data,
            "status",
            "병역구분",
            "service_type",
            "service_status",
            "exemption_reason",
            "면제사유",
        ),
        "unit": _str(data, "unit", "부대", "소속"),
        "note": _str(data, "note", "비고", "remarks", "description"),
    }


def normalize_awards(data: Any) -> list:
    """Normalize awards/honors data.

    Returns: [{name, issuer, date, project}]
    """
    if not data:
        return []

    if isinstance(data, dict):
        # Single award as dict
        data = [data]

    if not isinstance(data, list):
        return [{"name": str(data)}]

    result = []
    for item in data:
        if isinstance(item, str):
            result.append({"name": item})
        elif isinstance(item, dict):
            result.append(
                {
                    "name": _str(
                        item, "name", "award_name", "title", "수상명", "상훈명"
                    ),
                    "issuer": _str(
                        item, "issuer", "organization", "수여기관", "발급기관", "agency"
                    ),
                    "date": _str(item, "date", "award_date", "수상일", "year"),
                    "project": _str(item, "project", "관련프로젝트", "description"),
                }
            )
    return result


def normalize_overseas(data: Any) -> list:
    """Normalize overseas experience data.

    Returns: [{country, purpose, start_date, end_date, duration, type}]
    """
    if not data:
        return []

    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        return [{"country": str(data)}]

    result = []
    for item in data:
        if isinstance(item, str):
            result.append({"country": item})
        elif isinstance(item, dict):
            result.append(
                {
                    "country": _str(item, "country", "국가", "location", "region"),
                    "purpose": _str(item, "purpose", "목적", "type", "reason"),
                    "start_date": _str(item, "start_date", "시작일", "from"),
                    "end_date": _str(item, "end_date", "종료일", "to"),
                    "duration": _str(item, "duration", "기간", "period"),
                    "type": _str(item, "type", "구분", "category"),
                }
            )
    return result


def normalize_self_intro(data: Any) -> str:
    """Normalize self-introduction / cover letter / objective.

    Handles dict (with subkeys like motto, vision, swot) or plain string.
    Returns: single text string.
    """
    if not data:
        return ""

    if isinstance(data, str):
        return data.strip()

    if isinstance(data, list):
        # Join list items
        parts = []
        for item in data:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(_dict_to_text(item))
        return "\n\n".join(parts)

    if isinstance(data, dict):
        return _dict_to_text(data)

    return str(data)


def normalize_family(data: Any) -> dict:
    """Normalize family info data.

    Returns: {marital_status, spouse, children_count, detail}
    """
    if not data:
        return {}

    if isinstance(data, str):
        # e.g. "기혼, 자녀 2명"
        return {"note": data}

    if isinstance(data, list):
        if len(data) == 1 and isinstance(data[0], dict):
            data = data[0]
        else:
            return {"detail": data}

    if not isinstance(data, dict):
        return {"note": str(data)}

    return {
        "marital_status": _str(
            data,
            "marital_status",
            "결혼여부",
            "marriage",
            "status",
            "혼인상태",
            "결혼",
        ),
        "spouse": _str(data, "spouse", "spouse_age", "배우자", "spouse_info"),
        "children_count": _int_val(
            data, "children_count", "children", "자녀수", "number_of_children"
        ),
        "detail": _str(
            data, "detail", "children_detail", "자녀정보", "family_members", "note"
        ),
    }


def normalize_trainings(data: Any) -> list:
    """Normalize training/courses data.

    Returns: [{name, institution, date, duration}]
    """
    if not data:
        return []

    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        return [{"name": str(data)}]

    result = []
    for item in data:
        if isinstance(item, str):
            result.append({"name": item})
        elif isinstance(item, dict):
            result.append(
                {
                    "name": _str(
                        item,
                        "name",
                        "course_name",
                        "training_name",
                        "과정명",
                        "title",
                        "program",
                    ),
                    "institution": _str(
                        item,
                        "institution",
                        "organization",
                        "기관",
                        "provider",
                        "training_institution",
                    ),
                    "date": _str(
                        item, "date", "completion_date", "수료일", "period", "year"
                    ),
                    "duration": _str(item, "duration", "기간", "hours", "period"),
                }
            )
    return result


def normalize_patents(data: Any) -> list:
    """Normalize patents data.

    Returns: [{title, type, country, date, number}]
    """
    if not data:
        return []

    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        return [{"title": str(data)}]

    result = []
    for item in data:
        if isinstance(item, str):
            result.append({"title": item})
        elif isinstance(item, dict):
            result.append(
                {
                    "title": _str(item, "title", "patent_name", "name", "특허명"),
                    "type": _str(item, "type", "구분", "category", "patent_type"),
                    "country": _str(item, "country", "국가", "region"),
                    "date": _str(
                        item,
                        "date",
                        "registration_date",
                        "filing_date",
                        "등록일",
                        "출원일",
                    ),
                    "number": _str(
                        item,
                        "number",
                        "patent_number",
                        "registration_number",
                        "등록번호",
                    ),
                }
            )
    return result


def normalize_projects(data: Any) -> list:
    """Normalize projects data.

    Returns: [{name, role, description, start_date, end_date, budget}]
    """
    if not data:
        return []

    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        return [{"name": str(data)}]

    result = []
    for item in data:
        if isinstance(item, str):
            result.append({"name": item})
        elif isinstance(item, dict):
            result.append(
                {
                    "name": _str(item, "name", "project_name", "title", "프로젝트명"),
                    "role": _str(item, "role", "역할", "position"),
                    "description": _str(
                        item, "description", "설명", "details", "summary"
                    ),
                    "start_date": _str(item, "start_date", "시작일", "from"),
                    "end_date": _str(item, "end_date", "종료일", "to"),
                    "budget": _str(item, "budget", "예산", "규모", "scale"),
                }
            )
    return result


# ---- Internal helpers ----


def _str(data: dict, *keys: str) -> str:
    """Extract the first non-empty string value from data using multiple possible keys."""
    for key in keys:
        val = data.get(key)
        if val is not None and val != "" and val != [] and val != {}:
            if isinstance(val, str):
                return val.strip()
            return str(val)
    return ""


def _int_val(data: dict, *keys: str) -> int | None:
    """Extract the first integer value from data using multiple possible keys."""
    for key in keys:
        val = data.get(key)
        if val is not None:
            if isinstance(val, int):
                return val
            if isinstance(val, str):
                try:
                    return int(val)
                except (ValueError, TypeError):
                    pass
    return None


def _dict_to_text(d: dict) -> str:
    """Convert a dict to a readable text representation."""
    parts = []
    for k, v in d.items():
        if v and v not in ([], {}, "", None):
            if isinstance(v, (list, dict)):
                parts.append(f"[{k}] {str(v)}")
            else:
                parts.append(f"[{k}] {v}")
    return "\n".join(parts)
