"""Integrity pipeline: Step 1 (extract) -> Step 2 (normalize, parallel) -> Step 3 (cross-analysis).

Consolidated from:
- candidates/services/integrity/pipeline.py
- candidates/services/integrity/step1_extract.py
- candidates/services/integrity/step2_normalize.py
- candidates/services/integrity/step3_overlap.py
- candidates/services/integrity/step3_cross_version.py
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from django.conf import settings
from google import genai

from data_extraction.services.extraction.prompts import (
    CAREER_OUTPUT_SCHEMA,
    CAREER_SYSTEM_PROMPT,
    EDUCATION_OUTPUT_SCHEMA,
    EDUCATION_SYSTEM_PROMPT,
    STEP1_SYSTEM_PROMPT,
    build_step1_prompt,
)
from data_extraction.services.extraction.validators import (
    validate_step1,
    validate_step2,
)
from data_extraction.services.filters import apply_regex_field_filters

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"


# ===========================================================================
# Shared Gemini helper
# ===========================================================================


def _get_client() -> genai.Client:
    """Get Gemini client from settings."""
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


def _call_gemini(system: str, prompt: str, max_tokens: int = 6000) -> dict | None:
    """Call Gemini and parse JSON response."""
    client = _get_client()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        result = json.loads(response.text)
        if not isinstance(result, dict):
            return None
        return result
    except Exception:
        logger.warning("Gemini call failed", exc_info=True)
        return None


# ===========================================================================
# Step 1: Faithful extraction
# ===========================================================================


def extract_raw_data(
    resume_text: str,
    *,
    feedback: str | None = None,
    max_retries: int = 2,
) -> dict | None:
    """Step 1: Extract all data faithfully from resume text.

    Args:
        resume_text: Preprocessed resume text.
        feedback: Optional feedback from previous extraction attempt.
        max_retries: Maximum retry attempts.

    Returns:
        Raw extracted data dict, or None if extraction fails.
    """
    prompt = build_step1_prompt(resume_text, feedback=feedback)

    for attempt in range(max_retries):
        result = _call_gemini(STEP1_SYSTEM_PROMPT, prompt)
        if result and "name" in result:
            return result
        logger.warning("Step 1 extraction attempt %d/%d failed", attempt + 1, max_retries)

    return None


# ===========================================================================
# Step 2: Normalization + fraud detection
# ===========================================================================


def normalize_career_group(
    entries: list[dict],
    canonical_name: str,
    *,
    feedback: str | None = None,
) -> dict | None:
    """Normalize all career entries into deduplicated, ordered careers + flags."""
    entries_json = json.dumps(entries, ensure_ascii=False, indent=2)

    feedback_block = ""
    if feedback:
        feedback_block = f"\n## 피드백\n{feedback}\n"

    prompt = (
        f"아래 {len(entries)}개 경력 항목을 정규화하세요. "
        f"같은 회사의 중복 항목은 하나로 통합하세요.{feedback_block}\n\n"
        f"## 출력 스키마\n```\n{CAREER_OUTPUT_SCHEMA}\n```\n\n"
        f"## 입력 항목\n```json\n{entries_json}\n```\n\n"
        "JSON만 출력하세요."
    )

    result = _call_gemini(CAREER_SYSTEM_PROMPT, prompt, max_tokens=4000)
    if not result or "careers" not in result:
        # fallback: single career format
        if result and "career" in result:
            result["careers"] = [result.pop("career")]
            return result
        logger.warning("Step 2 career normalization failed")
        return None

    return result


def normalize_education_group(
    entries: list[dict],
    *,
    feedback: str | None = None,
) -> dict | None:
    """Normalize education entries + detect SHORT_DEGREE."""
    if not entries:
        return {"educations": [], "flags": []}

    entries_json = json.dumps(entries, ensure_ascii=False, indent=2)

    feedback_block = ""
    if feedback:
        feedback_block = f"\n## 피드백\n{feedback}\n"

    prompt = (
        f"아래 {len(entries)}개 학력 항목을 정규화하고 위조 의심을 탐지하세요."
        f"{feedback_block}\n\n"
        f"## 출력 스키마\n```\n{EDUCATION_OUTPUT_SCHEMA}\n```\n\n"
        f"## 입력 항목\n```json\n{entries_json}\n```\n\n"
        "JSON만 출력하세요."
    )

    result = _call_gemini(EDUCATION_SYSTEM_PROMPT, prompt, max_tokens=2000)
    if not result or "educations" not in result:
        logger.warning("Step 2 education normalization failed")
        return None

    return result


def normalize_skills(raw_data: dict) -> dict:
    """Code-based skills normalization. No LLM.

    Skills (proper nouns) are passed through without modification.
    """
    return {
        "certifications": raw_data.get("certifications", []),
        "language_skills": raw_data.get("language_skills", []),
        "skills": raw_data.get("skills", []),
    }


# ===========================================================================
# Step 3a: Period overlap detection
# ===========================================================================


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


# ===========================================================================
# Step 3b: Cross-version comparison
# ===========================================================================

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


# ===========================================================================
# Main pipeline orchestrator
# ===========================================================================


def run_integrity_pipeline(
    resume_text: str,
    *,
    previous_data: dict | None = None,
) -> dict | None:
    """Run the full integrity pipeline.

    Step 1: Faithful extraction (AI, 1 call)
    Step 2: Parallel normalization + fraud detection
        - Career agent (AI) -- all careers at once
        - Education agent (AI) -- all educations at once
        - Skills (code) -- passthrough
    Step 3: Cross-analysis (code)
        - Period overlaps between careers
        - Career-education overlaps
        - Cross-version comparison (if previous data available)

    Returns:
        Final result dict, or None on failure.
    """
    retries = 0

    # -- Step 1: Faithful extraction --
    raw_data = extract_raw_data(resume_text)
    if raw_data is None:
        logger.error("Step 1 extraction failed")
        return None

    # Step 1 validation + retry
    step1_issues = validate_step1(raw_data, resume_text)
    if any(i["severity"] == "warning" for i in step1_issues):
        feedback = ". ".join(i["message"] for i in step1_issues if i["severity"] == "warning")
        logger.info("Step 1 validation issues, retrying: %s", feedback)
        retry = extract_raw_data(resume_text, feedback=feedback)
        if retry and "name" in retry:
            raw_data = retry
            retries += 1

    careers_raw = raw_data.get("careers", [])
    educations_raw = raw_data.get("educations", [])

    # -- Step 2: Parallel normalization (career + education + skills) --
    all_flags: list[dict] = []
    normalized_careers: list[dict] = []
    normalized_educations: list[dict] = []

    def _normalize_careers():
        result = normalize_career_group(careers_raw, "전체 경력")
        if result is None:
            return
        # Validate
        issues = validate_step2(result)
        if any(i["severity"] == "error" for i in issues):
            feedback = ". ".join(i["message"] for i in issues if i["severity"] == "error")
            retry = normalize_career_group(careers_raw, "전체 경력", feedback=feedback)
            if retry:
                return retry
        return result

    def _normalize_educations():
        return normalize_education_group(educations_raw)

    # Run career and education normalization in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        career_future = executor.submit(_normalize_careers)
        edu_future = executor.submit(_normalize_educations)

        career_result = career_future.result()
        edu_result = edu_future.result()

    if career_result:
        careers_list = career_result.get("careers", [])
        if not careers_list:
            # single career format
            career = career_result.get("career")
            if career:
                careers_list = [career]
        normalized_careers = careers_list
        all_flags.extend(career_result.get("flags", []))

    if edu_result:
        normalized_educations = edu_result.get("educations", [])
        all_flags.extend(edu_result.get("flags", []))

    # Sort careers by start_date descending, assign order
    normalized_careers.sort(key=lambda c: c.get("start_date") or "", reverse=True)
    for i, c in enumerate(normalized_careers):
        c["order"] = i

    # Skills (code, instant)
    skills = normalize_skills(raw_data)

    # -- Step 3: Cross-analysis (code) --

    # 3a: Career period overlaps
    overlap_flags = check_period_overlaps(normalized_careers)
    all_flags.extend(overlap_flags)

    # 3b: Career-education overlaps
    ce_flags = check_career_education_overlap(normalized_careers, normalized_educations)
    all_flags.extend(ce_flags)

    # 3c: Cross-version comparison
    if previous_data:
        cv_flags = compare_versions(
            {"careers": normalized_careers, "educations": normalized_educations},
            previous_data,
        )
        all_flags.extend(cv_flags)

    # -- Assemble result --
    return apply_regex_field_filters({
        "name": raw_data.get("name"),
        "name_en": raw_data.get("name_en"),
        "birth_year": raw_data.get("birth_year"),
        "gender": raw_data.get("gender"),
        "email": raw_data.get("email"),
        "phone": raw_data.get("phone"),
        "address": raw_data.get("address"),
        "current_company": raw_data.get("current_company") or "",
        "current_position": raw_data.get("current_position") or "",
        "total_experience_years": raw_data.get("total_experience_years"),
        "resume_reference_date": raw_data.get("resume_reference_date"),
        "core_competencies": raw_data.get("core_competencies", []),
        "summary": raw_data.get("summary") or "",
        "careers": normalized_careers,
        "educations": normalized_educations,
        "certifications": skills.get("certifications", []),
        "language_skills": skills.get("language_skills", []),
        "skills": raw_data.get("skills", []),
        "personal_etc": raw_data.get("personal_etc", []),
        "education_etc": raw_data.get("education_etc", []),
        "career_etc": raw_data.get("career_etc", []),
        "skills_etc": raw_data.get("skills_etc", []),
        "integrity_flags": all_flags,
        "field_confidences": {},
        "pipeline_meta": {
            "step1_items": len(careers_raw) + len(educations_raw),
            "retries": retries,
        },
    })
