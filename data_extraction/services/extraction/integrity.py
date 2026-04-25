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
from pathlib import Path

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
    validation_issues_to_flags,
)
from data_extraction.services.filters import apply_regex_field_filters

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"


# ===========================================================================
# Matching utilities (shared with backfill commands)
# ===========================================================================
# NOTE: `_normalize_company` is defined further down (Step 3c section) since
# both layers (carry-forward + cross-version comparison) need consistent
# company-name normalization. Keeping a single definition prevents the
# silent shadowing bug where two competing definitions yielded different
# match keys for the same input.


def _normalize_date_to_ym(date_str: str) -> str | None:
    """Convert various date formats to YYYY-MM. Returns None on failure.

    Supports: YYYY-MM, YYYY/MM, YYYY.MM, 2019년 3월, 2019년03월,
    range expressions like '2019.03 ~ 현재' (extracts start only).
    """
    if not date_str:
        return None
    # Strip range expressions — use start date only
    date_str = re.split(r"\s*[~\-–—]\s*", date_str)[0].strip()
    # YYYY-MM, YYYY/MM, YYYY.MM
    m = re.match(r"(\d{4})[-./](\d{1,2})", date_str)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    # 2019년 3월, 2019년03월
    m = re.match(r"(\d{4})년\s*(\d{1,2})월?", date_str)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    return None


# ===========================================================================
# Carry-forward: restore fields Step 2 may have dropped
# ===========================================================================

_CAREER_CARRY_FIELDS = [
    "reason_left",
    "achievements",
    "salary",
    "duration_text",
    "company_en",
    # Step 2 LLM이 통합 과정에서 떨어뜨릴 수 있는 핵심 식별·내용 필드 안전망.
    # CAREER_SYSTEM_PROMPT의 "필드 보존 원칙"과 정렬되어 있어, LLM이 잘 따르면
    # 무영향이고 떨어뜨리면 코드가 raw에서 복원한다.
    "position",
    "department",
    "duties",
]


def _carry_forward_career_fields(
    normalized: list[dict],
    raw_careers: list[dict],
) -> None:
    """Restore fields Step 2 may have dropped, using (company, start_date) composite key.

    Falls back gracefully: if composite key doesn't match, no carry-forward is done
    (missing data is safer than mismatched data).
    """
    raw_index: dict[tuple[str, str], list[dict]] = {}
    for raw in raw_careers:
        company_key = _normalize_company(raw.get("company") or "")
        date_key = _normalize_date_to_ym(raw.get("start_date") or "")
        if company_key and date_key:
            raw_index.setdefault((company_key, date_key), []).append(raw)

    for career in normalized:
        company_key = _normalize_company(career.get("company") or "")
        date_key = career.get("start_date") or ""  # Step 2 output is already YYYY-MM
        matches = raw_index.get((company_key, date_key), [])
        if not matches:
            continue
        best = max(
            matches,
            key=lambda r: sum(1 for f in _CAREER_CARRY_FIELDS if r.get(f)),
        )
        for field in _CAREER_CARRY_FIELDS:
            if not career.get(field) and best.get(field):
                career[field] = best[field]


_EDUCATION_CARRY_FIELDS = ["gpa", "status"]


def _carry_forward_education_fields(
    normalized: list[dict],
    raw_educations: list[dict],
) -> None:
    """Restore gpa/status from Step 1 if Step 2 dropped them.

    status는 위조 단서(중퇴/수료/편입)이므로 정규화 단계에서 떨어지면 안 됩니다.
    """
    raw_index: dict[tuple[str, int | None], dict] = {}
    for raw in raw_educations:
        key = (
            (raw.get("institution") or "").strip().lower(),
            raw.get("end_year"),
        )
        if key[0]:
            raw_index.setdefault(key, raw)

    for edu in normalized:
        key = (
            (edu.get("institution") or "").strip().lower(),
            edu.get("end_year"),
        )
        raw = raw_index.get(key)
        if not raw:
            continue
        for field in _EDUCATION_CARRY_FIELDS:
            if not edu.get(field) and raw.get(field):
                edu[field] = raw[field]


# ===========================================================================
# Shared Gemini helper
# ===========================================================================


def _get_client() -> genai.Client:
    """Get Gemini client from settings."""
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


# Module-level provider setting, controlled by pipeline.py
_provider: str = "gemini"


def set_provider(provider: str) -> None:
    """Set the LLM provider for this module ('gemini' or 'openai')."""
    global _provider
    _provider = provider


def _call_llm(system: str, prompt: str, max_tokens: int = 6000) -> dict | None:
    """Call LLM (Gemini or OpenAI) and parse JSON response.

    Uses sanitizers.parse_llm_json for robust JSON recovery from
    malformed responses (control chars, extra braces, truncation, etc.).
    """
    if _provider == "openai":
        from data_extraction.services.extraction.openai import call_openai

        return call_openai(system, prompt, max_tokens)

    from data_extraction.services.extraction.sanitizers import parse_llm_json
    from data_extraction.services.extraction import telemetry

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
        telemetry.add_from_gemini_response(response)
        return parse_llm_json(response.text)
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
    max_retries: int = 3,
    file_name: str | None = None,
) -> dict | None:
    """Step 1: Extract all data faithfully from resume text.

    Args:
        resume_text: Preprocessed resume text.
        feedback: Optional feedback from previous extraction attempt.
        max_retries: Maximum retry attempts.
        file_name: Original file name (may contain name, age, company info).

    Returns:
        Raw extracted data dict, or None if extraction fails.
    """
    prompt = build_step1_prompt(resume_text, feedback=feedback, file_name=file_name)

    for attempt in range(max_retries):
        result = _call_llm(STEP1_SYSTEM_PROMPT, prompt)
        if result and "name" in result:
            return result
        if attempt < max_retries - 1:
            logger.warning(
                "Step 1 extraction attempt %d/%d failed, retrying...",
                attempt + 1,
                max_retries,
            )

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

    count_note = (
        "입력 항목이 0개이면 careers는 빈 배열, flags도 빈 배열로 반환하세요."
        if len(entries) == 0
        else f"입력 항목은 총 {len(entries)}개입니다."
    )
    prompt = (
        "아래 Step 1 경력 항목들에 대해 시스템 지시(통합·날짜 정규화·"
        "종료일 추정·필드 보존·flag 작성)를 모두 수행하여 결과를 반환하세요.\n"
        f"{count_note}{feedback_block}\n\n"
        f"## 출력 스키마\n```\n{CAREER_OUTPUT_SCHEMA}\n```\n\n"
        f"## 입력 항목\n```json\n{entries_json}\n```\n\n"
        "JSON만 출력하세요."
    )

    result = _call_llm(CAREER_SYSTEM_PROMPT, prompt, max_tokens=4000)
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

    count_note = (
        "입력 항목이 0개이면 educations는 빈 배열, flags도 빈 배열로 반환하세요."
        if len(entries) == 0
        else f"입력 항목은 총 {len(entries)}개입니다."
    )
    prompt = (
        "아래 Step 1 학력 항목들에 대해 시스템 지시(통합·status 보존·위조 의심 "
        "탐지·flag 작성)를 모두 수행하여 결과를 반환하세요.\n"
        f"{count_note}{feedback_block}\n\n"
        f"## 출력 스키마\n```\n{EDUCATION_OUTPUT_SCHEMA}\n```\n\n"
        f"## 입력 항목\n```json\n{entries_json}\n```\n\n"
        "JSON만 출력하세요."
    )

    result = _call_llm(EDUCATION_SYSTEM_PROMPT, prompt, max_tokens=2000)
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

        intervals.append(
            {
                "index": i,
                "company": c.get("company", ""),
                "start": _month_index(*start),
                "end": end_idx,
                "period": f"{c.get('start_date', '')}~{end_str or '현재'}",
            }
        )

    intervals.sort(key=lambda x: x["start"])

    raw_overlaps = []
    for i, a in enumerate(intervals):
        for b in intervals[i + 1 :]:
            if b["start"] > a["end"]:
                break
            overlap = min(a["end"], b["end"]) - b["start"]
            if overlap <= 0:
                continue
            if _is_affiliated(a["index"], b["index"], affiliated_groups):
                continue
            if overlap <= SHORT_OVERLAP_THRESHOLD:
                continue
            raw_overlaps.append(
                {
                    "company_a": a["company"],
                    "period_a": a["period"],
                    "company_b": b["company"],
                    "period_b": b["period"],
                    "overlap_months": overlap,
                }
            )

    if not raw_overlaps:
        return []

    has_repeated = len(raw_overlaps) >= 2
    flags = []
    for o in raw_overlaps:
        severity = "RED" if has_repeated else "YELLOW"
        flags.append(
            {
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
                    "반복적인 장기 중복 패턴"
                    if has_repeated
                    else "이직 인수인계를 넘어서는 장기 중복"
                ),
            }
        )

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
        career_intervals.append(
            {
                "company": c.get("company", ""),
                "start": _month_index(*start),
                "end": end_idx,
            }
        )

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

            flags.append(
                {
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
                }
            )

    return flags


# ===========================================================================
# Step 3b: Education fraud detection
# ===========================================================================

_GRAD_KEYWORDS = {
    "석사",
    "박사",
    "mba",
    "master",
    "doctor",
    "ph.d",
    "ph.d.",
    "m.s.",
    "m.a.",
    "m.b.a.",
    "m.eng.",
    "공학석사",
    "이학석사",
    "경영학석사",
    "공학박사",
    "이학박사",
}

_UNDERGRAD_KEYWORDS = {
    "학사",
    "bachelor",
    "b.s.",
    "b.a.",
    "b.eng.",
    "학부",
    "공학사",
    "이학사",
    "경영학사",
    "문학사",
    "법학사",
}


def check_education_gaps(educations: list[dict]) -> list[dict]:
    """Detect missing undergrad and missing admission year."""
    flags: list[dict] = []

    has_grad = False
    has_undergrad = False

    for edu in educations:
        degree = (edu.get("degree") or "").lower().strip()
        if any(kw in degree for kw in _GRAD_KEYWORDS):
            has_grad = True
        if any(kw in degree for kw in _UNDERGRAD_KEYWORDS):
            has_undergrad = True

        # Missing start_year
        if edu.get("end_year") and not edu.get("start_year"):
            institution = edu.get("institution", "")
            flags.append(
                {
                    "type": "EDUCATION_GAP",
                    "severity": "YELLOW",
                    "field": "educations",
                    "detail": f"{institution} 입학년도가 누락됨 (졸업년도만 기재)",
                    "chosen": None,
                    "alternative": None,
                    "reasoning": "편입 이력을 숨기기 위해 입학년도를 생략하는 경우가 있음",
                }
            )

    if has_grad and not has_undergrad:
        flags.append(
            {
                "type": "EDUCATION_GAP",
                "severity": "YELLOW",
                "field": "educations",
                "detail": "대학원(석사/박사) 학력만 있고 학부(학사) 학력이 없음",
                "chosen": None,
                "alternative": None,
                "reasoning": "학부 학력이 대학원보다 낮아 의도적으로 생략한 경우가 있음",
            }
        )

    return flags


_MULTI_CAMPUS_DATA: dict | None = None


def _load_multi_campus_data() -> dict:
    global _MULTI_CAMPUS_DATA
    if _MULTI_CAMPUS_DATA is None:
        data_path = (
            Path(__file__).resolve().parent.parent.parent
            / "data"
            / "multi_campus_universities.json"
        )
        if data_path.exists():
            with open(data_path, encoding="utf-8") as f:
                _MULTI_CAMPUS_DATA = json.load(f)
        else:
            _MULTI_CAMPUS_DATA = {}
    return _MULTI_CAMPUS_DATA


def _match_university(institution: str, data: dict) -> tuple[str, dict] | None:
    """Match an institution name to a multi-campus university entry."""
    inst_lower = institution.lower().strip()
    for uni_name, uni_data in data.items():
        # Exact name match
        if uni_name.lower() in inst_lower:
            return uni_name, uni_data
        # Alias match
        for alias in uni_data.get("aliases", []):
            if alias.lower() in inst_lower:
                return uni_name, uni_data
    return None


def check_campus_match(educations: list[dict]) -> list[dict]:
    """Detect missing or suspicious campus for multi-campus universities."""
    data = _load_multi_campus_data()
    if not data:
        return []

    flags: list[dict] = []

    for edu in educations:
        institution = edu.get("institution", "")
        if not institution:
            continue

        match = _match_university(institution, data)
        if match is None:
            continue

        uni_name, uni_data = match
        campus_keywords = uni_data.get("campus_keywords", {})
        campus_only_depts = uni_data.get("campus_only_departments", {})
        main_campus = uni_data.get("main_campus", "")

        # Check if campus is identifiable from institution text
        inst_lower = institution.lower()
        major = (edu.get("major") or "").strip()
        detected_campus = None

        for campus, keywords in campus_keywords.items():
            if any(kw.lower() in inst_lower for kw in keywords):
                detected_campus = campus
                break

        # Check major against campus-only departments
        major_campus = None
        if major:
            for campus, depts in campus_only_depts.items():
                if any(dept in major for dept in depts):
                    major_campus = campus
                    break

        if major_campus and major_campus != main_campus and detected_campus is None:
            # Department only exists at non-main campus but no campus specified
            flags.append(
                {
                    "type": "CAMPUS_DEPARTMENT_MATCH",
                    "severity": "RED",
                    "field": "educations",
                    "detail": (
                        f"{uni_name} {major} — "
                        f"해당 학과는 {major_campus}캠퍼스에만 존재"
                    ),
                    "chosen": None,
                    "alternative": None,
                    "reasoning": (
                        f"캠퍼스를 밝히지 않았으나, {major} 학과는 "
                        f"{major_campus}캠퍼스에만 개설되어 있음"
                    ),
                }
            )
        elif detected_campus is None:
            # Multi-campus university but no campus identifiable
            campuses = list(campus_keywords.keys())
            flags.append(
                {
                    "type": "CAMPUS_MISSING",
                    "severity": "YELLOW",
                    "field": "educations",
                    "detail": (f"{uni_name} 캠퍼스 확인 필요 ({'/'.join(campuses)})"),
                    "chosen": None,
                    "alternative": None,
                    "reasoning": (
                        "멀티캠퍼스 대학인데 캠퍼스 정보가 없음. "
                        "지방 캠퍼스일 가능성 확인 필요"
                    ),
                }
            )

    return flags


def check_birth_year_consistency(
    current_birth_year: int | None,
    previous_birth_year: int | None,
) -> list[dict]:
    """Detect birth year mismatch between resume versions."""
    if current_birth_year is None or previous_birth_year is None:
        return []
    if current_birth_year == previous_birth_year:
        return []

    return [
        {
            "type": "BIRTH_YEAR_MISMATCH",
            "severity": "RED",
            "field": "birth_year",
            "detail": (
                f"출생연도가 이전 이력서({previous_birth_year}년)와 "
                f"현재({current_birth_year}년)에서 다름. 호적 기준 확인 필요"
            ),
            "chosen": str(current_birth_year),
            "alternative": str(previous_birth_year),
            "reasoning": "나이를 줄이기 위해 출생연도를 변경하는 경우가 있음. 호적 등록 기준으로 확인 필요",
        }
    ]


# ===========================================================================
# Step 3c: Cross-version comparison
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


def _company_keys(career: dict) -> set[str]:
    """Return all match keys for a career — covers Korean and English variants.

    Includes both `company` and `company_en` (each normalized) so that the
    same company recorded as `삼성전자` in one version and `Samsung Electronics`
    in another still matches as a single entity.
    """
    keys = set()
    for k in ("company", "company_en"):
        v = career.get(k)
        if v:
            n = _normalize_company(v)
            if n:
                keys.add(n)
    return keys


def _match_careers(
    current: list[dict], previous: list[dict]
) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    """Match careers between current and previous versions.

    Match strategy (in priority order):
      1. Any normalized company key (company OR company_en) overlap.
         Handles 한국어 ↔ 영문 표기 variants of the same company.
      2. start_date YYYY-MM equal.
         Backup for legitimate cases where a company changed names entirely
         (merger, rebrand) — same person rarely starts two jobs in the same
         month.

    Returns:
        (matched_pairs, unmatched_current, unmatched_previous)
    """
    matched = []
    matched_prev_idx: set[int] = set()
    unmatched_current = []

    for cur in current:
        cur_keys = _company_keys(cur)
        cur_start = _parse_ym_to_months(cur.get("start_date"))
        match_idx = None

        # Pass 1 — company key overlap
        for i, prev in enumerate(previous):
            if i in matched_prev_idx:
                continue
            if cur_keys & _company_keys(prev):
                match_idx = i
                break

        # Pass 2 — same start month (different company name = renaming/merger)
        if match_idx is None and cur_start is not None:
            for i, prev in enumerate(previous):
                if i in matched_prev_idx:
                    continue
                prev_start = _parse_ym_to_months(prev.get("start_date"))
                if prev_start == cur_start:
                    match_idx = i
                    break

        if match_idx is not None:
            matched.append((cur, previous[match_idx]))
            matched_prev_idx.add(match_idx)
        else:
            unmatched_current.append(cur)

    unmatched_previous = [
        p for i, p in enumerate(previous) if i not in matched_prev_idx
    ]
    return matched, unmatched_current, unmatched_previous


# Korean university name aliases (한↔영 표기 매핑).
# Used by cross-version institution matching to bridge LLM non-determinism
# in extracted institution naming. canonical form on the left, lowercased
# variants on the right. Add new entries when verification surfaces them.
_INSTITUTION_ALIASES: dict[str, tuple[str, ...]] = {
    "동국대학교": ("dongguk university", "dongguk univ", "the university of dongguk", "the graduate school of dongguk"),
    "한국외국어대학교": ("hankuk university of foreign studies", "hankuk university of foreign language", "hankuk univ of foreign studies", "hufs"),
    "한국해양대학교": ("korea maritime and ocean university", "korea maritime university"),
    "고려대학교": ("korea university", "korea univ"),
    "서울대학교": ("seoul national university", "snu"),
    "연세대학교": ("yonsei university", "yonsei univ"),
    "한양대학교": ("hanyang university", "hanyang univ"),
    "성균관대학교": ("sungkyunkwan university", "skku"),
    "이화여자대학교": ("ewha womans university", "ewha univ", "ewha"),
    "서강대학교": ("sogang university", "sogang univ"),
    "중앙대학교": ("chung-ang university", "chung ang university", "chungang university", "cau"),
    "경희대학교": ("kyung hee university", "kyunghee university", "khu"),
    "한국과학기술원": ("kaist", "korea advanced institute of science and technology"),
    "포항공과대학교": ("postech", "pohang university of science and technology"),
    "단국대학교": ("dankook university", "the university of dankook", "the graduate school of dankook"),
    "건국대학교": ("konkuk university",),
    "동덕여자대학교": ("dongduk womans university", "dongduk women's university"),
    "서울여자대학교": ("seoul women's university", "seoul womens university"),
    "숙명여자대학교": ("sookmyung women's university", "sookmyung womens university"),
    "성신여자대학교": ("sungshin women's university", "sungshin womens university"),
    "덕성여자대학교": ("duksung women's university", "duksung womens university"),
    "광운대학교": ("kwangwoon university",),
    "국민대학교": ("kookmin university",),
    "명지대학교": ("myongji university",),
    "상명대학교": ("sangmyung university",),
    "세종대학교": ("sejong university",),
    "숭실대학교": ("soongsil university",),
    "아주대학교": ("ajou university",),
    "인하대학교": ("inha university",),
    "전남대학교": ("chonnam national university", "jeonnam national university"),
    "전북대학교": ("chonbuk national university", "jeonbuk national university"),
    "충남대학교": ("chungnam national university",),
    "충북대학교": ("chungbuk national university",),
    "강원대학교": ("kangwon national university",),
    "경상국립대학교": ("gyeongsang national university", "gyeongsang nat'l university"),
    "경북대학교": ("kyungpook national university", "knu"),
    "부산대학교": ("pusan national university", "pnu"),
    "제주대학교": ("jeju national university",),
    "한국기술교육대학교": ("korea university of technology and education", "koreatech"),
    "서울과학기술대학교": ("seoul national university of science and technology", "seoultech"),
    "한경국립대학교": ("hankyong national university",),
    "한밭대학교": ("hanbat national university",),
    "공주대학교": ("kongju national university",),
    "강남대학교": ("kangnam university",),
    "가천대학교": ("gachon university",),
    "을지대학교": ("eulji university",),
    "차의과학대학교": ("cha university",),
    "홍익대학교": ("hongik university",),
    "한성대학교": ("hansung university",),
    "동아대학교": ("dong-a university", "donga university"),
}

# Build reverse lookup once: lowercased name → canonical
_INSTITUTION_REVERSE: dict[str, str] = {}
for _canonical, _aliases in _INSTITUTION_ALIASES.items():
    _INSTITUTION_REVERSE[_canonical.lower()] = _canonical
    for _alias in _aliases:
        _INSTITUTION_REVERSE[_alias.lower()] = _canonical


def _strip_korean_spaces(s: str) -> str:
    """Remove whitespace between Hangul characters only — preserves spaces in
    English text. "청주 대학교" → "청주대학교" but "Seoul National University"
    stays "seoul national university" (lowercase).
    """
    return re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", s)


def _normalize_education(edu: dict) -> str:
    """Normalize institution name for comparison.

    Maps known Korean university name variants (한↔영, 약어, 한+영 병기) to a
    canonical Korean form so that cross-version matching tolerates LLM
    non-determinism in institution naming.
    """
    raw = (edu.get("institution") or "").strip()
    if not raw:
        return ""
    norm = re.sub(r"\s+", " ", raw.lower())
    norm = _strip_korean_spaces(norm)
    # Strip trailing parenthetical bilingual annotation: "X (Y)" → "X" / "Y"
    no_paren = re.sub(r"\s*\([^)]*\)\s*$", "", norm).strip()
    paren_inner = None
    paren_match = re.search(r"\(([^)]+)\)", norm)
    if paren_match:
        paren_inner = _strip_korean_spaces(paren_match.group(1).strip())

    # Try canonical mapping on each form
    for candidate in (norm, no_paren, paren_inner):
        if candidate and candidate in _INSTITUTION_REVERSE:
            return _INSTITUTION_REVERSE[candidate].lower()

    # Substring within combined Korean+English notation (e.g.,
    # "한국외국어대학교 (Hankuk Univ of Foreign Language)" — both halves match)
    for canonical_lower, canonical in (
        (k, v) for k, v in _INSTITUTION_REVERSE.items() if len(k) >= 5
    ):
        if canonical_lower in norm:
            return canonical.lower()

    return no_paren or norm


_DEGREE_PHD_RE = re.compile(
    r"\b(?:phd|ph\.?d|d\.?phil|doctor|doctorate|ed\.?d|sc\.?d|dr\.?)\b"
)
_DEGREE_MASTER_RE = re.compile(
    r"\b(?:master|mba|m\.?b\.?a|msc|m\.?sc|m\.?s|m\.?a|m\.?eng|m\.?ed|m\.?phil|llm)\b"
)
_DEGREE_BACHELOR_RE = re.compile(
    r"\b(?:bachelor|bsc|b\.?sc|b\.?s|b\.?a|b\.?eng|b\.?ed|llb|ba|bs)\b"
)
_DEGREE_ASSOCIATE_RE = re.compile(
    r"\b(?:associate|diploma|hnd|foundation|aa|as)\b"
)


def _normalize_degree(degree: str | None) -> str:
    """Map degree variants to a canonical token for cross-language matching.

    Handles:
      - 한국어: 박사/석사/학사/전문학사/학부
      - 영문 풀네임: doctor/master/bachelor/associate/diploma 등
      - 영문 약어 (점 유무 무관): PhD/MA/MS/MBA/BA/BS/BSc/Diploma 등

    Word-boundary regex로 약어를 안전하게 매칭하여 false match를 방지한다
    (예: "Cuba"의 "ba" 같은 우연한 substring 제외).
    """
    d = (degree or "").lower().strip()
    if not d:
        return ""
    # 한국어 키워드는 substring 매치 — "전문학사"가 "학사"의 substring이므로
    # 더 긴 키워드부터 순서대로 체크해야 한다.
    if "박사" in d:
        return "phd"
    if "석사" in d:
        return "master"
    if "전문학사" in d:
        return "associate"
    if "학사" in d or "학부" in d:
        return "bachelor"
    # 영문 약어/풀네임은 word boundary 매치
    if _DEGREE_PHD_RE.search(d):
        return "phd"
    if _DEGREE_MASTER_RE.search(d):
        return "master"
    if _DEGREE_BACHELOR_RE.search(d):
        return "bachelor"
    if _DEGREE_ASSOCIATE_RE.search(d):
        return "associate"
    return d


def _education_match_keys(edu: dict) -> set[str]:
    """Match keys for an education entry — currently institution name only.

    A "year:degree" composite key was attempted to bridge Korean ↔ English
    institution variants (e.g., "USC GOULD" ↔ "USC대학원" both 2018 master),
    but it suppressed legitimate institution-change detection (e.g.,
    고려대 → 서울대 same year/degree = real fraud signal). Until we have a
    transliteration map, fall back to institution-name match only and accept
    that 음역(transliterated) variants will surface as EDUCATION_CHANGED.
    """
    keys = set()
    inst_norm = _normalize_education(edu)
    if inst_norm:
        keys.add(inst_norm)
    return keys


def _career_in_etc(career: dict, current_career_etc: list[dict]) -> bool:
    """Check if a previous career has been re-classified into current career_etc.

    Reclassification (careers → career_etc) is not deletion — the information
    is still preserved as a non-formal career entry. Match by normalized
    company name (substring either direction) so we tolerate minor variants.
    """
    prev_company_norm = _normalize_company(career.get("company") or "")
    if not prev_company_norm or len(prev_company_norm) < 2:
        return False
    for etc in current_career_etc or []:
        etc_company_norm = _normalize_company(etc.get("company") or "")
        if not etc_company_norm:
            continue
        if (
            prev_company_norm == etc_company_norm
            or prev_company_norm in etc_company_norm
            or etc_company_norm in prev_company_norm
        ):
            return True
    return False


def _check_career_deleted(
    unmatched_previous: list[dict],
    current_career_etc: list[dict] | None = None,
) -> list[dict]:
    """Detect CAREER_DELETED: careers in previous that are missing from current.

    Excludes reclassification cases (previous career now in current career_etc)
    — those preserve the information so are not actual deletions.
    """
    flags = []
    for career in unmatched_previous:
        if _career_in_etc(career, current_career_etc or []):
            continue  # reclassified to career_etc, not deleted
        duration = _career_duration_months(career)
        severity = "RED" if duration > 24 else "YELLOW"
        company = career.get("company", "?")
        period = f"{career.get('start_date', '?')}~{career.get('end_date') or '?'}"

        flags.append(
            {
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
            }
        )

    # Upgrade all to RED if 2+ careers deleted simultaneously
    if len(flags) >= 2:
        for flag in flags:
            flag["severity"] = "RED"
            flag["reasoning"] = (
                "2건 이상의 경력이 동시 삭제됨 — 의도적 은폐 가능성 높음"
            )

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

        flags.append(
            {
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
            }
        )
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
            flags.append(
                {
                    "type": "CAREER_ADDED_RETROACTIVELY",
                    "severity": "YELLOW",
                    "field": "careers",
                    "detail": f"{company}({period}) 경력이 소급 추가됨",
                    "chosen": f"{company}({period})",
                    "alternative": None,
                    "reasoning": "이전 이력서에 없던 과거 경력이 추가됨 — 경력 날조 가능성",
                }
            )
    return flags


def _check_education_changed(
    current_educations: list[dict],
    previous_educations: list[dict],
) -> list[dict]:
    """Detect EDUCATION_CHANGED: institution or degree changed between versions.

    Matches educations across versions by either:
      - normalized institution name (exact string match), or
      - "year:degree" composite (handles 한국어 ↔ 영문 institution variants
        of the same degree-year, e.g., 가천대학교 ↔ Gachon University 2017 학사)
    """
    matched_prev_idx: set[int] = set()
    matched_pairs: list[tuple[dict, dict]] = []
    cur_unmatched: list[dict] = []

    for cur in current_educations:
        cur_keys = _education_match_keys(cur)
        match_idx = None
        for i, prev in enumerate(previous_educations):
            if i in matched_prev_idx:
                continue
            if cur_keys & _education_match_keys(prev):
                match_idx = i
                break
        if match_idx is not None:
            matched_pairs.append((cur, previous_educations[match_idx]))
            matched_prev_idx.add(match_idx)
        else:
            cur_unmatched.append(cur)
    prev_unmatched = [
        p for i, p in enumerate(previous_educations)
        if i not in matched_prev_idx
    ]

    flags: list[dict] = []

    # Matched pair: only flag if degree differs after canonicalization
    for cur_edu, prev_edu in matched_pairs:
        cur_deg = _normalize_degree(cur_edu.get("degree"))
        prev_deg = _normalize_degree(prev_edu.get("degree"))
        if cur_deg and prev_deg and cur_deg != prev_deg:
            institution = cur_edu.get("institution", "?")
            flags.append(
                {
                    "type": "EDUCATION_CHANGED",
                    "severity": "RED",
                    "field": "educations",
                    "detail": (
                        f"{institution} 학위 변경: "
                        f"{prev_edu.get('degree')} → {cur_edu.get('degree')}"
                    ),
                    "chosen": cur_edu.get("degree"),
                    "alternative": prev_edu.get("degree"),
                    "reasoning": "학위 변경은 정당한 사유가 거의 없음 — 학력 위조 가능성",
                }
            )

    # Genuine institution changes: both an unmatched current AND an unmatched previous
    if cur_unmatched and prev_unmatched:
        for rem_edu in prev_unmatched:
            for add_edu in cur_unmatched:
                flags.append(
                    {
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
                    }
                )

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

    current_career_etc = current.get("career_etc", []) or []

    flags: list[dict] = []
    flags.extend(_check_career_deleted(unmatched_prev, current_career_etc))
    flags.extend(_check_career_period_changed(matched))
    flags.extend(_check_career_added_retroactively(unmatched_cur, previous_careers))
    flags.extend(_check_education_changed(current_educations, previous_educations))

    return flags


# ===========================================================================
# Auto-correction helpers
# ===========================================================================


def _is_current_end_date_flag(flag: dict, autocorrected_companies: set[str]) -> bool:
    """Check if a flag is about is_current/end_date contradiction for an auto-corrected company.

    Only returns True when the flag both (a) describes the is_current/end_date
    contradiction we just auto-corrected AND (b) references one of the
    auto-corrected companies. If we cannot tie the flag to a specific company,
    we keep it — dropping unrelated flags would silently hide other problems.
    """
    detail = (flag.get("detail") or "").lower()
    field = (flag.get("field") or "").lower()

    # Check if this flag is about is_current contradiction
    is_about_current = (
        "is_current" in detail
        or ("current" in detail and "end_date" in detail)
        or "is_current" in field
    )
    if not is_about_current:
        return False

    # Check if it's about one of the auto-corrected companies
    for company in autocorrected_companies:
        if not company:
            continue
        flag_text = f"{detail} {(flag.get('chosen') or '').lower()} {(flag.get('alternative') or '').lower()}"
        if company in flag_text:
            return True

    # Flag is about is_current/end_date but doesn't reference any of the
    # companies we just auto-corrected. Keep it — it likely refers to a
    # different career we did not touch.
    return False


# ===========================================================================
# Main pipeline orchestrator
# ===========================================================================


def run_integrity_pipeline(
    resume_text: str,
    *,
    previous_data: dict | None = None,
    file_name: str | None = None,
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
    raw_data = extract_raw_data(resume_text, file_name=file_name)
    if raw_data is None:
        logger.error("Step 1 extraction failed")
        return None

    # Step 1 validation + retry. We re-run validation on the post-retry result
    # so the issues we surface as flags reflect the *final* extraction we keep,
    # matching how integrity batch records step1_validation_issues from the
    # latest stage (step1 or step1_retry).
    step1_issues = validate_step1(raw_data, resume_text)
    if any(i["severity"] == "warning" for i in step1_issues):
        feedback = ". ".join(
            i["message"] for i in step1_issues if i["severity"] == "warning"
        )
        logger.info("Step 1 validation issues, retrying: %s", feedback)
        retry = extract_raw_data(resume_text, feedback=feedback, file_name=file_name)
        if retry and "name" in retry:
            raw_data = retry
            retries += 1
            step1_issues = validate_step1(raw_data, resume_text)

    careers_raw = raw_data.get("careers", [])
    educations_raw = raw_data.get("educations", [])

    # -- Step 2: Parallel normalization (career + education + skills) --
    all_flags: list[dict] = []
    normalized_careers: list[dict] = []
    normalized_educations: list[dict] = []
    # Final career validation issues reflecting the result we ultimately keep,
    # so the flags we emit here mirror integrity batch's STEP2_VALIDATION flags.
    career_validation_issues: list[dict] = []

    def _normalize_careers():
        nonlocal career_validation_issues
        result = normalize_career_group(careers_raw, "전체 경력")
        if result is None:
            return None
        # Validate
        issues = validate_step2(result, raw_careers=careers_raw)
        if any(i["severity"] == "error" for i in issues):
            feedback = ". ".join(
                i["message"] for i in issues if i["severity"] == "error"
            )
            retry = normalize_career_group(careers_raw, "전체 경력", feedback=feedback)
            if retry:
                career_validation_issues = validate_step2(
                    retry, raw_careers=careers_raw
                )
                return retry
        career_validation_issues = issues
        return result

    def _normalize_educations():
        return normalize_education_group(educations_raw)

    # Run career and education normalization in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        career_future = executor.submit(_normalize_careers)
        edu_future = executor.submit(_normalize_educations)

        career_result = career_future.result()
        edu_result = edu_future.result()

    # Surface validator issues as integrity_flags (parity with integrity batch).
    # Without this, the realtime path silently drops warnings/errors that the
    # retry didn't fully resolve, so reviewers wouldn't see them.
    all_flags.extend(
        validation_issues_to_flags(
            step1_issues, stage="step1", default_severity="YELLOW"
        )
    )
    all_flags.extend(
        validation_issues_to_flags(
            career_validation_issues, stage="step2", default_severity="RED"
        )
    )

    if career_result:
        careers_list = career_result.get("careers", [])
        if not careers_list:
            # single career format
            career = career_result.get("career")
            if career:
                careers_list = [career]
        normalized_careers = careers_list
        _carry_forward_career_fields(normalized_careers, careers_raw)
        all_flags.extend(career_result.get("flags", []))

    if edu_result:
        normalized_educations = edu_result.get("educations", [])
        _carry_forward_education_fields(normalized_educations, educations_raw)
        all_flags.extend(edu_result.get("flags", []))

    # Sort careers by start_date descending, assign order
    normalized_careers.sort(key=lambda c: c.get("start_date") or "", reverse=True)
    for i, c in enumerate(normalized_careers):
        c["order"] = i

    # Auto-correct is_current/end_date contradiction:
    # If a career has an end_date, it cannot be current.
    autocorrected_companies = set()
    for c in normalized_careers:
        if c.get("end_date") and c.get("is_current"):
            c["is_current"] = False
            autocorrected_companies.add(_normalize_company(c.get("company", "")))

    # Remove AI flags that were about the contradiction we just auto-corrected
    if autocorrected_companies:
        all_flags = [
            f
            for f in all_flags
            if not _is_current_end_date_flag(f, autocorrected_companies)
        ]

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
            {
                "careers": normalized_careers,
                "educations": normalized_educations,
                "career_etc": raw_data.get("career_etc", []),
            },
            previous_data,
        )
        all_flags.extend(cv_flags)

    # 3d: Education gaps
    edu_gap_flags = check_education_gaps(normalized_educations)
    all_flags.extend(edu_gap_flags)

    # 3e: Campus match
    campus_flags = check_campus_match(normalized_educations)
    all_flags.extend(campus_flags)

    # -- Assemble result --
    return apply_regex_field_filters(
        {
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
                # Validator audit trail mirrors integrity batch's pipeline_meta
                # so downstream tools (review queue, diagnostics) see the same
                # shape regardless of execution mode.
                "step1_validation_issues": step1_issues,
                "step2_career_validation_issues": career_validation_issues,
                # Carry-forward audit trail: Step 1 raw data preserved here.
                # NOTE: This is a temporary preservation strategy. Long-term direction
                # is to restructure raw_extracted_json as {step1, step2, final}.
                "step1_careers_raw": careers_raw,
                "step1_educations_raw": educations_raw,
            },
        }
    )
