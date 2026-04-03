"""Step 3: Rule-based PERIOD_OVERLAP detection on normalized career data."""

from __future__ import annotations

from datetime import date


def _month_index(year: int, month: int) -> int:
    return year * 12 + month


def _parse_ym(date_str: str) -> tuple[int, int] | None:
    if not date_str:
        return None
    try:
        parts = date_str.split("-")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None


def _is_affiliated(idx_a: int, idx_b: int, affiliated_groups: list[dict]) -> bool:
    for group in affiliated_groups:
        if group.get("relationship") != "affiliated_group":
            continue
        indices = group.get("entry_indices", [])
        if idx_a in indices and idx_b in indices:
            return True
    return False


SHORT_OVERLAP_THRESHOLD = 3


def check_period_overlaps(
    careers: list[dict],
    *,
    affiliated_groups: list[dict] | None = None,
) -> list[dict]:
    """Detect PERIOD_OVERLAP between normalized careers.

    Returns list of integrity_flag dicts.
    """
    today = date.today()
    today_idx = _month_index(today.year, today.month)
    affiliated_groups = affiliated_groups or []

    intervals = []
    for i, c in enumerate(careers):
        start = _parse_ym(c.get("start_date", ""))
        if start is None:
            continue

        end_str = c.get("end_date", "")
        if end_str:
            end = _parse_ym(end_str)
            if end is None:
                continue
            end_idx = _month_index(*end)
        elif c.get("is_current"):
            end_idx = today_idx
        else:
            continue

        intervals.append({
            "index": i,
            "company": c.get("company", ""),
            "start": _month_index(*start),
            "end": end_idx,
            "period": f"{c.get('start_date', '')}~{end_str or '현재'}",
        })

    intervals.sort(key=lambda x: x["start"])

    raw_overlaps = []
    for i, a in enumerate(intervals):
        for b in intervals[i + 1:]:
            if b["start"] > a["end"]:
                break
            overlap = min(a["end"], b["end"]) - b["start"]
            if overlap <= 0:
                continue
            if _is_affiliated(a["index"], b["index"], affiliated_groups):
                continue
            if overlap <= SHORT_OVERLAP_THRESHOLD:
                continue
            raw_overlaps.append({
                "company_a": a["company"],
                "period_a": a["period"],
                "company_b": b["company"],
                "period_b": b["period"],
                "overlap_months": overlap,
            })

    if not raw_overlaps:
        return []

    has_repeated = len(raw_overlaps) >= 2
    flags = []
    for o in raw_overlaps:
        severity = "RED" if has_repeated else "YELLOW"
        flags.append({
            "type": "PERIOD_OVERLAP",
            "severity": severity,
            "field": "careers",
            "detail": (
                f"{o['company_a']}({o['period_a']})와 "
                f"{o['company_b']}({o['period_b']}) "
                f"재직 기간이 {o['overlap_months']}개월 중복됨"
            ),
            "chosen": None,
            "alternative": None,
            "reasoning": (
                "반복적인 장기 중복 패턴" if has_repeated
                else "이직 인수인계를 넘어서는 장기 중복"
            ),
        })

    return flags


def check_career_education_overlap(
    careers: list[dict],
    educations: list[dict],
) -> list[dict]:
    """Detect overlap between full-time careers and education periods."""
    today = date.today()
    today_idx = _month_index(today.year, today.month)

    career_intervals = []
    for c in careers:
        start = _parse_ym(c.get("start_date", ""))
        if start is None:
            continue
        end_str = c.get("end_date", "")
        if end_str:
            end = _parse_ym(end_str)
            if end is None:
                continue
            end_idx = _month_index(*end)
        elif c.get("is_current"):
            end_idx = today_idx
        else:
            continue
        career_intervals.append({
            "company": c.get("company", ""),
            "start": _month_index(*start),
            "end": end_idx,
        })

    flags = []
    for edu in educations:
        start_year = edu.get("start_year")
        end_year = edu.get("end_year")
        if not start_year or not end_year:
            continue

        edu_start = _month_index(start_year, 3)  # assume March
        edu_end = _month_index(end_year, 2)  # assume February

        institution = edu.get("institution", "")

        for ci in career_intervals:
            overlap_start = max(ci["start"], edu_start)
            overlap_end = min(ci["end"], edu_end)
            overlap = overlap_end - overlap_start
            if overlap <= 6:  # 6 months or less is normal (graduation + job start)
                continue

            flags.append({
                "type": "CAREER_EDUCATION_OVERLAP",
                "severity": "YELLOW",
                "field": "careers+educations",
                "detail": (
                    f"{ci['company']} 재직 기간과 {institution} 재학 기간이 "
                    f"{overlap}개월 겹침"
                ),
                "chosen": None,
                "alternative": None,
                "reasoning": "정규직 재직과 재학이 장기간 겹치는 경우 확인 필요",
            })

    return flags
