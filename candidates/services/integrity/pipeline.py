"""Integrity pipeline: Step 1 (extract) → Step 2 (normalize, parallel) → Step 3 (cross-analysis)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from candidates.services.extraction_filters import apply_regex_field_filters
from candidates.services.integrity.step1_extract import extract_raw_data
from candidates.services.integrity.step2_normalize import (
    normalize_career_group,
    normalize_education_group,
    normalize_skills,
)
from candidates.services.integrity.step3_overlap import (
    check_period_overlaps,
    check_career_education_overlap,
)
from candidates.services.integrity.step3_cross_version import compare_versions
from candidates.services.integrity.validators import (
    validate_step1,
    validate_step2,
)

logger = logging.getLogger(__name__)


def run_integrity_pipeline(
    resume_text: str,
    *,
    previous_data: dict | None = None,
) -> dict | None:
    """Run the full integrity pipeline.

    Step 1: Faithful extraction (AI, 1 call)
    Step 2: Parallel normalization + fraud detection
        - Career agent (AI) — all careers at once
        - Education agent (AI) — all educations at once
        - Skills (code) — passthrough
    Step 3: Cross-analysis (code)
        - Period overlaps between careers
        - Career-education overlaps
        - Cross-version comparison (if previous data available)

    Returns:
        Final result dict, or None on failure.
    """
    retries = 0

    # ── Step 1: Faithful extraction ──
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

    # ── Step 2: Parallel normalization (career + education + skills) ──
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

    # ── Step 3: Cross-analysis (code) ──

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

    # ── Assemble result ──
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
        "integrity_flags": all_flags,
        "field_confidences": {},
        "pipeline_meta": {
            "step1_items": len(careers_raw) + len(educations_raw),
            "retries": retries,
        },
    })
