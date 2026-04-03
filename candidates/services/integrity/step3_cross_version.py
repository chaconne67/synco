"""Step 3: Cross-version comparison — detect suspicious changes between resume versions."""

from __future__ import annotations

import re


# Suffixes to strip for fuzzy company name matching
_COMPANY_SUFFIXES = re.compile(
    r"(\s*)(주식회사|㈜|\(주\)|co\.?\s*,?\s*ltd\.?|inc\.?|corp\.?|llc\.?|gmbh)(\s*)",
    re.IGNORECASE,
)


def _normalize_company(name: str) -> str:
    """Normalize company name for comparison: lowercase, strip suffixes/whitespace."""
    s = name.strip().lower()
    s = _COMPANY_SUFFIXES.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_ym_to_months(date_str: str | None) -> int | None:
    """Parse 'YYYY-MM' to absolute month index, or None."""
    if not date_str:
        return None
    try:
        parts = date_str.split("-")
        return int(parts[0]) * 12 + int(parts[1])
    except (ValueError, IndexError):
        return None


def _career_duration_months(career: dict) -> int:
    """Return career duration in months (0 if unparseable)."""
    start = _parse_ym_to_months(career.get("start_date"))
    end = _parse_ym_to_months(career.get("end_date"))
    if start is None or end is None:
        return 0
    return max(end - start, 0)


def _latest_career_end(careers: list[dict]) -> int | None:
    """Return the latest end_date (as month index) across all careers."""
    latest = None
    for c in careers:
        end = _parse_ym_to_months(c.get("end_date"))
        if end is not None:
            if latest is None or end > latest:
                latest = end
    return latest


def _match_careers(
    current: list[dict], previous: list[dict]
) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    """Match careers between current and previous by normalized company name.

    Returns:
        (matched_pairs, unmatched_current, unmatched_previous)
    """
    cur_by_name: dict[str, list[dict]] = {}
    for c in current:
        key = _normalize_company(c.get("company", ""))
        cur_by_name.setdefault(key, []).append(c)

    prev_by_name: dict[str, list[dict]] = {}
    for p in previous:
        key = _normalize_company(p.get("company", ""))
        prev_by_name.setdefault(key, []).append(p)

    matched = []
    unmatched_current = []
    unmatched_previous = []

    all_keys = set(cur_by_name.keys()) | set(prev_by_name.keys())
    for key in all_keys:
        cur_list = cur_by_name.get(key, [])
        prev_list = prev_by_name.get(key, [])

        # Pair up by index (simplest approach for same-company entries)
        for i in range(max(len(cur_list), len(prev_list))):
            if i < len(cur_list) and i < len(prev_list):
                matched.append((cur_list[i], prev_list[i]))
            elif i < len(cur_list):
                unmatched_current.append(cur_list[i])
            else:
                unmatched_previous.append(prev_list[i])

    return matched, unmatched_current, unmatched_previous


def _normalize_education(edu: dict) -> str:
    """Normalize institution name for comparison."""
    return re.sub(r"\s+", " ", edu.get("institution", "").strip().lower())


def _check_career_deleted(unmatched_previous: list[dict]) -> list[dict]:
    """Detect CAREER_DELETED: careers in previous that are missing from current."""
    flags = []
    for career in unmatched_previous:
        duration = _career_duration_months(career)
        severity = "RED" if duration > 24 else "YELLOW"
        company = career.get("company", "?")
        period = f"{career.get('start_date', '?')}~{career.get('end_date') or '?'}"

        flags.append({
            "type": "CAREER_DELETED",
            "severity": severity,
            "field": "careers",
            "detail": f"{company}({period}) 경력이 삭제됨",
            "chosen": None,
            "alternative": f"{company}({period})",
            "reasoning": (
                f"{duration}개월 이상 장기 경력 삭제 — 의도적 은폐 가능성"
                if severity == "RED"
                else "단기 경력 삭제 — 정리 목적일 수 있음"
            ),
        })
    return flags


def _check_career_period_changed(
    matched_pairs: list[tuple[dict, dict]],
) -> list[dict]:
    """Detect CAREER_PERIOD_CHANGED: significant date differences for the same company."""
    THRESHOLD = 3  # months

    changed = []
    for cur, prev in matched_pairs:
        cur_start = _parse_ym_to_months(cur.get("start_date"))
        prev_start = _parse_ym_to_months(prev.get("start_date"))
        cur_end = _parse_ym_to_months(cur.get("end_date"))
        prev_end = _parse_ym_to_months(prev.get("end_date"))

        start_diff = abs(cur_start - prev_start) if cur_start and prev_start else 0
        end_diff = abs(cur_end - prev_end) if cur_end and prev_end else 0

        if start_diff > THRESHOLD or end_diff > THRESHOLD:
            changed.append((cur, prev, start_diff, end_diff))

    # Multiple careers changed -> RED for all
    severity = "RED" if len(changed) >= 2 else "YELLOW"

    flags = []
    for cur, prev, start_diff, end_diff in changed:
        company = cur.get("company", "?")
        cur_period = f"{cur.get('start_date', '?')}~{cur.get('end_date') or '?'}"
        prev_period = f"{prev.get('start_date', '?')}~{prev.get('end_date') or '?'}"

        diff_parts = []
        if start_diff > 0:
            diff_parts.append(f"시작일 {start_diff}개월 차이")
        if end_diff > 0:
            diff_parts.append(f"종료일 {end_diff}개월 차이")

        flags.append({
            "type": "CAREER_PERIOD_CHANGED",
            "severity": severity,
            "field": "careers",
            "detail": (
                f"{company} 재직 기간 변경: {prev_period} → {cur_period} "
                f"({', '.join(diff_parts)})"
            ),
            "chosen": cur_period,
            "alternative": prev_period,
            "reasoning": (
                "복수 경력의 기간이 동시 변경됨 — 조작 가능성 높음"
                if severity == "RED"
                else "재직 기간이 유의미하게 변경됨 — 경력 부풀리기 가능성"
            ),
        })
    return flags


def _check_career_added_retroactively(
    unmatched_current: list[dict],
    previous_careers: list[dict],
) -> list[dict]:
    """Detect CAREER_ADDED_RETROACTIVELY: new careers with dates before previous latest end."""
    latest_end = _latest_career_end(previous_careers)
    if latest_end is None:
        return []

    flags = []
    for career in unmatched_current:
        end = _parse_ym_to_months(career.get("end_date"))
        if end is not None and end < latest_end:
            company = career.get("company", "?")
            period = f"{career.get('start_date', '?')}~{career.get('end_date') or '?'}"
            flags.append({
                "type": "CAREER_ADDED_RETROACTIVELY",
                "severity": "YELLOW",
                "field": "careers",
                "detail": f"{company}({period}) 경력이 소급 추가됨",
                "chosen": f"{company}({period})",
                "alternative": None,
                "reasoning": "이전 이력서에 없던 과거 경력이 추가됨 — 경력 날조 가능성",
            })
    return flags


def _check_education_changed(
    current_educations: list[dict],
    previous_educations: list[dict],
) -> list[dict]:
    """Detect EDUCATION_CHANGED: institution or degree changed between versions."""
    # Match educations by normalized institution name
    cur_by_inst: dict[str, list[dict]] = {}
    for e in current_educations:
        key = _normalize_education(e)
        cur_by_inst.setdefault(key, []).append(e)

    prev_by_inst: dict[str, list[dict]] = {}
    for e in previous_educations:
        key = _normalize_education(e)
        prev_by_inst.setdefault(key, []).append(e)

    flags = []

    # Check matched institutions for degree changes
    for inst_key in set(cur_by_inst.keys()) & set(prev_by_inst.keys()):
        cur_list = cur_by_inst[inst_key]
        prev_list = prev_by_inst[inst_key]

        for i in range(min(len(cur_list), len(prev_list))):
            cur_deg = (cur_list[i].get("degree") or "").strip()
            prev_deg = (prev_list[i].get("degree") or "").strip()

            if cur_deg and prev_deg and cur_deg != prev_deg:
                institution = cur_list[i].get("institution", "?")
                flags.append({
                    "type": "EDUCATION_CHANGED",
                    "severity": "RED",
                    "field": "educations",
                    "detail": f"{institution} 학위 변경: {prev_deg} → {cur_deg}",
                    "chosen": cur_deg,
                    "alternative": prev_deg,
                    "reasoning": "학위 변경은 정당한 사유가 거의 없음 — 학력 위조 가능성",
                })

    # Check institution changes: previous institution completely gone, new one appeared
    removed = set(prev_by_inst.keys()) - set(cur_by_inst.keys())
    added = set(cur_by_inst.keys()) - set(prev_by_inst.keys())

    # If institutions were both removed and added, flag as institution change
    if removed and added:
        for rem_key in removed:
            for add_key in added:
                rem_edu = prev_by_inst[rem_key][0]
                add_edu = cur_by_inst[add_key][0]
                flags.append({
                    "type": "EDUCATION_CHANGED",
                    "severity": "RED",
                    "field": "educations",
                    "detail": (
                        f"교육기관 변경: {rem_edu.get('institution', '?')} → "
                        f"{add_edu.get('institution', '?')}"
                    ),
                    "chosen": add_edu.get("institution", "?"),
                    "alternative": rem_edu.get("institution", "?"),
                    "reasoning": "교육기관 자체가 변경됨 — 학력 위조 가능성",
                })

    return flags


def compare_versions(current: dict, previous: dict) -> list[dict]:
    """Compare two normalized candidate data versions and detect suspicious changes.

    Both `current` and `previous` have the structure:
        {"careers": [...], "educations": [...]}

    Returns list of integrity flags.
    """
    current_careers = current.get("careers", [])
    previous_careers = previous.get("careers", [])
    current_educations = current.get("educations", [])
    previous_educations = previous.get("educations", [])

    matched, unmatched_cur, unmatched_prev = _match_careers(
        current_careers, previous_careers
    )

    flags: list[dict] = []
    flags.extend(_check_career_deleted(unmatched_prev))
    flags.extend(_check_career_period_changed(matched))
    flags.extend(
        _check_career_added_retroactively(unmatched_cur, previous_careers)
    )
    flags.extend(
        _check_education_changed(current_educations, previous_educations)
    )

    return flags
