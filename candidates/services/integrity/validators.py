"""Validators for integrity pipeline step outputs.

Each validator function checks the output of a pipeline step and returns
a list of issue dicts: {"severity": "error"|"warning"|"info", "message": "..."}.
"""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_JAPANESE_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF]")
_ENGLISH_WORD_RE = re.compile(r"[A-Za-z]{15,}")
_DURATION_PAREN_RE = re.compile(
    r"\("
    r"(?:\d+\s*(?:개월|년|Y|M|y|m))"
    r"(?:\s*\d*\s*(?:개월|년|Y|M|y|m))*"
    r"\)"
)
_DATE_YM_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")


# ---------------------------------------------------------------------------
# Step 1 — extraction completeness
# ---------------------------------------------------------------------------


def validate_step1(raw_data: dict, resume_text: str) -> list[dict]:
    """Validate Step 1 extraction completeness.

    Checks:
    - source_section diversity
    - Japanese text coverage
    - English text coverage
    - duration_text capture for parenthetical durations
    """
    issues: list[dict] = []
    careers: list[dict] = raw_data.get("careers", [])
    source_sections = {c.get("source_section", "") for c in careers if c.get("source_section")}

    # --- source_section diversity ---
    if len(careers) > 1 and len(source_sections) == 1:
        issues.append({
            "severity": "warning",
            "message": (
                f"All {len(careers)} careers share the same source_section "
                f"'{next(iter(source_sections))}'; other resume sections may have been missed"
            ),
        })

    # --- Japanese coverage ---
    if _JAPANESE_RE.search(resume_text):
        has_jp_section = any(
            _JAPANESE_RE.search(s) for s in source_sections
        )
        if not has_jp_section:
            issues.append({
                "severity": "warning",
                "message": (
                    "Resume contains Japanese text (katakana/hiragana) "
                    "but no source_section references Japanese content"
                ),
            })

    # --- English coverage ---
    if _ENGLISH_WORD_RE.search(resume_text):
        has_en_section = any(
            _ENGLISH_WORD_RE.search(s) for s in source_sections
        )
        if not has_en_section:
            issues.append({
                "severity": "warning",
                "message": (
                    "Resume contains significant English text "
                    "but no source_section references English content"
                ),
            })

    # --- duration_text capture ---
    if _DURATION_PAREN_RE.search(resume_text):
        has_duration = any(c.get("duration_text") for c in careers)
        if not has_duration:
            issues.append({
                "severity": "warning",
                "message": (
                    "Resume contains parenthetical duration patterns "
                    "but no career has duration_text filled"
                ),
            })

    return issues


# ---------------------------------------------------------------------------
# Step 1.5 — grouping quality
# ---------------------------------------------------------------------------


def validate_step1_5(
    grouping: dict,
    total_careers: int,
    total_educations: int,
) -> list[dict]:
    """Validate Step 1.5 grouping quality.

    Checks:
    - ungrouped ratio: warn if >50% of careers are ungrouped
    """
    issues: list[dict] = []

    groups: list[dict] = grouping.get("groups", [])
    grouped_indices: set[int] = set()
    for g in groups:
        for idx in g.get("entry_indices", []):
            grouped_indices.add(idx)

    if total_careers > 0:
        ungrouped = total_careers - len(grouped_indices)
        ratio = ungrouped / total_careers
        if ratio > 0.5:
            issues.append({
                "severity": "warning",
                "message": (
                    f"{ungrouped}/{total_careers} careers "
                    f"({ratio:.0%}) are ungrouped; grouping may be incomplete"
                ),
            })

    return issues


# ---------------------------------------------------------------------------
# Step 2 — normalization quality
# ---------------------------------------------------------------------------


def validate_step2(normalized: dict) -> list[dict]:
    """Validate Step 2 normalization quality.

    Checks:
    - Required fields: company and start_date must be present in each career
    - Date format: start_date/end_date must match YYYY-MM pattern
    - Flag consistency: if a flag has severity, it must have reasoning
    """
    issues: list[dict] = []
    careers: list[dict] = normalized.get("careers", [])
    flags: list[dict] = normalized.get("flags", [])

    for i, career in enumerate(careers):
        company = career.get("company")
        start_date = career.get("start_date")

        # --- required fields ---
        if not company:
            issues.append({
                "severity": "error",
                "message": f"Career #{i}: missing required field 'company'",
            })
        if not start_date:
            issues.append({
                "severity": "error",
                "message": f"Career #{i}: missing required field 'start_date'",
            })

        # --- date format ---
        if start_date and not _DATE_YM_RE.match(start_date):
            issues.append({
                "severity": "error",
                "message": (
                    f"Career #{i}: start_date '{start_date}' "
                    f"does not match YYYY-MM format"
                ),
            })

        end_date = career.get("end_date")
        if end_date and not _DATE_YM_RE.match(end_date):
            issues.append({
                "severity": "error",
                "message": (
                    f"Career #{i}: end_date '{end_date}' "
                    f"does not match YYYY-MM format"
                ),
            })

    # --- flag consistency ---
    for i, flag in enumerate(flags):
        if flag.get("severity") and not flag.get("reasoning"):
            issues.append({
                "severity": "warning",
                "message": (
                    f"Flag #{i} has severity '{flag['severity']}' "
                    f"but no reasoning provided"
                ),
            })

    return issues
