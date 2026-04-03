"""Salary normalization from raw LLM-extracted JSON.

Handles 10+ different key names and wildly different structures
produced by the LLM across 1,145 resumes.

Usage:
    from candidates.services.salary_parser import normalize_salary

    result = normalize_salary(raw_extracted_json)
    # result = {
    #     "current_salary_int": 5400,   # 만원, or None
    #     "desired_salary_int": 6000,   # 만원, or None
    #     "salary_detail": { ... },     # full normalized JSON
    # }
"""

from __future__ import annotations

import re
from typing import Any

SALARY_SOURCE_KEYS = [
    "salary",
    "salary_info",
    "salary_information",
    "salary_current",
    "salary_expected",
    "current_salary",
    "desired_salary",
    "current_annual_income",
    "desired_annual_income",
    "expected_salary",
]

# Keys that typically hold current salary values
CURRENT_KEYS = {
    "current_salary",
    "current",
    "base_salary",
    "salary",
    "base",
    "amount",
    "current_base",
    "current_base_salary",
    "annual_salary",
    "total",
}

# Keys that typically hold desired salary values
DESIRED_KEYS = {
    "desired_salary",
    "desired",
    "expected_salary",
    "expected",
    "desired_base_salary",
    "expected_base",
    "desired_annual_salary",
    "희망연봉",
}


def normalize_salary(raw: dict) -> dict:
    """Extract and normalize salary data from raw_extracted_json.

    Args:
        raw: The full raw_extracted_json dict from a Candidate.

    Returns:
        Dict with keys: current_salary_int, desired_salary_int, salary_detail.
    """
    if not raw:
        return {"current_salary_int": None, "desired_salary_int": None, "salary_detail": {}}

    result = {
        "current_salary_int": None,
        "desired_salary_int": None,
        "salary_detail": {},
    }

    # Collect all salary-related data from source keys
    salary_data: dict[str, Any] = {}
    for key in SALARY_SOURCE_KEYS:
        val = raw.get(key)
        if val is not None and val != "" and val != {} and val != []:
            salary_data[key] = val

    if not salary_data:
        return result

    # Build salary_detail from all found data
    detail: dict[str, Any] = {}
    current_int: int | None = None
    desired_int: int | None = None

    for key, val in salary_data.items():
        if isinstance(val, dict):
            current_int, desired_int = _extract_from_dict(
                val, current_int, desired_int, detail
            )
        elif isinstance(val, (int, float)):
            amount = _normalize_to_manwon(val)
            if key in (
                "current_salary",
                "salary_current",
                "current_annual_income",
                "salary",
            ):
                current_int = current_int or amount
            elif key in (
                "desired_salary",
                "salary_expected",
                "desired_annual_income",
                "expected_salary",
            ):
                desired_int = desired_int or amount
            detail[key] = val
        elif isinstance(val, str):
            amount = _parse_salary_string(val)
            note = val if amount is None else None
            if key in (
                "current_salary",
                "salary_current",
                "current_annual_income",
            ):
                current_int = current_int or amount
                if note:
                    detail.setdefault("current_note", note)
            elif key in (
                "desired_salary",
                "salary_expected",
                "desired_annual_income",
                "expected_salary",
            ):
                desired_int = desired_int or amount
                if note:
                    detail.setdefault("desired_note", note)
            detail[key] = val
        elif isinstance(val, list):
            # Some LLMs return salary as a list — store raw
            detail[key] = val

    # Store merged detail
    for key, val in salary_data.items():
        if key not in detail:
            detail[key] = val

    result["current_salary_int"] = current_int
    result["desired_salary_int"] = desired_int
    result["salary_detail"] = detail

    return result


def _extract_from_dict(
    data: dict,
    current_int: int | None,
    desired_int: int | None,
    detail: dict,
) -> tuple[int | None, int | None]:
    """Recursively extract salary integers from a dict structure."""
    for k, v in data.items():
        k_lower = k.lower().replace("-", "_").replace(" ", "_")

        if isinstance(v, dict):
            # Nested dict: e.g. salary_info.current_salary = {base: ..., bonus: ...}
            if k_lower in ("current", "current_salary"):
                sub_amount = _try_extract_amount(v)
                current_int = current_int or sub_amount
                detail.setdefault("current", v)
            elif k_lower in ("desired", "desired_salary", "expected"):
                sub_amount = _try_extract_amount(v)
                desired_int = desired_int or sub_amount
                detail.setdefault("desired", v)
            else:
                detail[k] = v
        elif isinstance(v, (int, float)):
            amount = _normalize_to_manwon(v)
            if k_lower in CURRENT_KEYS:
                current_int = current_int or amount
            elif k_lower in DESIRED_KEYS:
                desired_int = desired_int or amount
            detail[k] = v
        elif isinstance(v, str):
            amount = _parse_salary_string(v)
            if k_lower in CURRENT_KEYS:
                current_int = current_int or amount
            elif k_lower in DESIRED_KEYS:
                desired_int = desired_int or amount
            detail[k] = v
        else:
            detail[k] = v

    return current_int, desired_int


def _try_extract_amount(data: dict) -> int | None:
    """Try to extract a numeric salary from a nested dict."""
    for key in ("base_salary", "salary", "base", "amount", "total", "annual"):
        val = data.get(key)
        if val is not None:
            if isinstance(val, (int, float)):
                return _normalize_to_manwon(val)
            if isinstance(val, str):
                return _parse_salary_string(val)
    return None


def _parse_salary_string(s: str) -> int | None:
    """Parse a salary string like '3,300만원', '54,000,000원', '회사내규'.

    Returns:
        Salary in 만원 units, or None if unparseable.
    """
    if not s:
        return None

    # Remove whitespace
    s_clean = s.strip()

    # Check if string contains any digits
    digits = re.sub(r"[^\d]", "", s_clean)
    if not digits:
        return None  # "회사내규", "면접 후 협의" etc.

    numeric_val = int(digits)
    if numeric_val == 0:
        return None

    # Detect unit — check 억 before 만원 to handle '1억 5천만원' correctly
    if "억" in s_clean:
        # 억 단위: extract 억 and 만 parts
        return _parse_eok_string(s_clean)
    elif "만원" in s_clean or "만 원" in s_clean:
        # Already in 만원
        return numeric_val
    else:
        # Raw number: apply heuristic
        return _normalize_to_manwon(numeric_val)


def _parse_eok_string(s: str) -> int | None:
    """Parse strings like '1억 2천만원', '2억'."""
    eok_match = re.search(r"(\d+)\s*억", s)
    man_match = re.search(r"(\d+)\s*만", s)
    cheon_match = re.search(r"(\d+)\s*천", s)

    total = 0
    if eok_match:
        total += int(eok_match.group(1)) * 10000  # 1억 = 10000만원
    if man_match:
        total += int(man_match.group(1))
    if cheon_match:
        total += int(cheon_match.group(1)) * 1000

    return total if total > 0 else None


def _normalize_to_manwon(value: int | float) -> int | None:
    """Convert a numeric value to 만원 using heuristic.

    Heuristic:
    - > 100,000 → likely in 원, divide by 10,000
    - <= 100,000 → likely already in 만원
    """
    if value is None or value == 0:
        return None

    v = int(value)
    if v > 100_000:
        # Likely in 원
        return v // 10_000
    else:
        # Likely already in 만원
        return v
