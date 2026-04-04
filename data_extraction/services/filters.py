from __future__ import annotations

import copy
import re

from candidates.services.candidate_identity import select_primary_phone

_EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)
_FOUR_DIGIT_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_TWO_DIGIT_YEAR_RE = re.compile(r"(?<!\d)(\d{2})(?!\d)")
_YM_RE = re.compile(
    r"(?P<year>(?:19|20)?\d{2})\s*(?:[./\-년]\s*)?(?P<month>\d{1,2})"
    r"(?:\s*(?:[./\-월]\s*)?(?P<day>\d{1,2}))?\s*(?:일)?"
)


def apply_regex_field_filters(extracted: dict | None) -> dict | None:
    """Normalize fields whose formats are stable enough for regex cleanup."""
    if not isinstance(extracted, dict):
        return extracted

    normalized = copy.deepcopy(extracted)
    normalized["email"] = _normalize_email(normalized.get("email"))
    normalized["phone"] = _normalize_phone(normalized.get("phone"))
    normalized["birth_year"] = _normalize_birth_year(normalized.get("birth_year"))
    normalized["gender"] = _normalize_gender(normalized.get("gender"))
    normalized["resume_reference_date"] = _normalize_reference_date(
        normalized.get("resume_reference_date")
    )

    for career in normalized.get("careers") or []:
        if not isinstance(career, dict):
            continue
        career["start_date"] = _normalize_year_month(career.get("start_date"))
        career["end_date"] = _normalize_year_month(career.get("end_date"))
        career["end_date_inferred"] = _normalize_year_month(
            career.get("end_date_inferred")
        )

    for cert in normalized.get("certifications") or []:
        if not isinstance(cert, dict):
            continue
        cert["acquired_date"] = _normalize_year_month(cert.get("acquired_date"))

    for skill in normalized.get("language_skills") or []:
        if not isinstance(skill, dict):
            continue
        skill["score"] = _normalize_score(skill.get("score"))

    return normalized


def _normalize_email(value: str | None) -> str:
    raw = _collapse_whitespace(value)
    if not raw:
        return ""
    match = _EMAIL_RE.search(raw)
    return match.group(0).lower() if match else raw.lower()


def _normalize_phone(value: str | None) -> str:
    raw = _collapse_whitespace(value)
    if not raw:
        return ""
    return select_primary_phone(raw)


def _normalize_birth_year(value) -> int | None:
    if value in ("", None):
        return None
    if isinstance(value, int):
        return value if 1940 <= value <= 2010 else None

    raw = _collapse_whitespace(str(value))
    match = _FOUR_DIGIT_YEAR_RE.search(raw)
    if match:
        parsed = int(match.group(1))
        return parsed if 1940 <= parsed <= 2010 else None

    match = _TWO_DIGIT_YEAR_RE.search(raw)
    if not match:
        return None

    short = int(match.group(1))
    if 50 <= short <= 99:
        return 1900 + short
    if 0 <= short <= 25:
        return 2000 + short
    return None


def _normalize_gender(value: str | None) -> str:
    raw = _collapse_whitespace(value).lower()
    if raw in {"m", "male", "man", "남", "남자", "남성"}:
        return "male"
    if raw in {"f", "female", "woman", "여", "여자", "여성"}:
        return "female"
    return raw


def _normalize_reference_date(value: str | None) -> str:
    raw = _collapse_whitespace(value)
    if not raw:
        return ""

    normalized = _extract_date(raw, allow_day=True)
    return normalized or raw


def _normalize_year_month(value: str | None) -> str:
    raw = _collapse_whitespace(value)
    if not raw:
        return ""
    if re.search(r"(현재|present|current|재직)", raw, re.IGNORECASE):
        return ""

    normalized = _extract_date(raw, allow_day=False)
    return normalized or raw


def _normalize_score(value: str | None) -> str:
    raw = _collapse_whitespace(value)
    if not raw:
        return ""

    score_match = re.search(r"\b\d{2,3}(?:\.\d+)?(?:점)?\b", raw)
    if score_match:
        return score_match.group(0)

    level_match = re.search(
        r"\b(AL|AH|IH|IM3|IM2|IM1|IL|NH|NM|NL|N[1-5]|[1-9]급)\b",
        raw,
        re.IGNORECASE,
    )
    if level_match:
        return level_match.group(1).upper()

    return raw


def _extract_date(raw: str, *, allow_day: bool) -> str:
    match = _YM_RE.search(raw)
    if not match:
        return ""

    year = _normalize_date_year(match.group("year"))
    month = int(match.group("month"))
    day_group = match.group("day")
    if year is None or not 1 <= month <= 12:
        return ""

    if allow_day and day_group:
        day = int(day_group)
        if 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"

    return f"{year:04d}-{month:02d}"


def _normalize_date_year(value: str) -> int | None:
    if not value:
        return None
    if len(value) == 4:
        parsed = int(value)
        return parsed if 1900 <= parsed <= 2100 else None

    short = int(value)
    if 50 <= short <= 99:
        return 1900 + short
    if 0 <= short <= 49:
        return 2000 + short
    return None


def _collapse_whitespace(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()
