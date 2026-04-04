"""Extraction pipeline: extract -> validate -> return result."""

from __future__ import annotations

import logging

from data_extraction.services.filters import apply_regex_field_filters
from data_extraction.services.extraction.gemini import extract_candidate_data
from data_extraction.services.validation import validate_extraction

logger = logging.getLogger(__name__)

def run_extraction_with_retry(
    raw_text: str,
    file_path: str,
    category: str,
    filename_meta: dict,
    file_reference_date: str | None = None,
    *,
    use_integrity_pipeline: bool = False,
    previous_data: dict | None = None,
) -> dict:
    """Run extraction with rule-based validation.

    Args:
        raw_text: Preprocessed resume text.
        file_path: Path to the resume file.
        category: Category folder name.
        filename_meta: Parsed metadata from filename.
        file_reference_date: File modification date from Drive.
        use_integrity_pipeline: If True, use the new integrity pipeline
            (Step 1 → 1.5 → 2 → 3) instead of the legacy single-call extraction.
        previous_data: Normalized data from a previous resume version
            for cross-version comparison.

    Returns:
        {
            "extracted": dict | None,
            "diagnosis": dict,
            "attempts": int,
            "retry_action": str,  # "none" | "human_review"
            "raw_text_used": str,
            "integrity_flags": list,  # only with integrity pipeline
        }
    """
    from data_extraction.services.text import classify_text_quality

    quality = classify_text_quality(raw_text)
    if quality != "ok":
        return {
            "extracted": None,
            "diagnosis": {
                "verdict": "fail",
                "issues": [{"field": "raw_text", "severity": "error",
                            "message": f"Text quality: {quality}"}],
                "field_scores": {},
                "overall_score": 0.0,
            },
            "attempts": 0,
            "retry_action": "none",
            "raw_text_used": raw_text,
            "integrity_flags": [],
        }

    if use_integrity_pipeline:
        return _run_integrity_pipeline(raw_text, previous_data=previous_data)

    return _run_legacy_pipeline(raw_text, filename_meta, file_reference_date)


def _run_integrity_pipeline(
    raw_text: str,
    *,
    previous_data: dict | None = None,
) -> dict:
    """New integrity pipeline: faithful extraction → grouping → normalization → cross-analysis."""
    from data_extraction.services.extraction.integrity import run_integrity_pipeline

    result = run_integrity_pipeline(raw_text, previous_data=previous_data)

    if result is None:
        logger.warning("Integrity pipeline returned None")
        return {
            "extracted": None,
            "diagnosis": {
                "verdict": "fail",
                "issues": [],
                "field_scores": {},
                "overall_score": 0.0,
            },
            "attempts": 1,
            "retry_action": "human_review",
            "raw_text_used": raw_text,
            "integrity_flags": [],
        }

    retries = result.get("pipeline_meta", {}).get("retries", 0)
    flags = result.get("integrity_flags", [])

    # Compute field-quality-based confidences (integrity pipeline doesn't get them from LLM)
    from data_extraction.services.validation import compute_field_confidences
    field_scores, category_scores = compute_field_confidences(result, {})
    result["field_confidences"] = field_scores

    return {
        "extracted": result,
        "diagnosis": _build_integrity_diagnosis(flags, field_scores),
        "attempts": 1 + retries,
        "retry_action": (
            "human_review"
            if any(f.get("severity") == "RED" for f in flags)
            else "none"
        ),
        "raw_text_used": raw_text,
        "integrity_flags": flags,
    }


def _run_legacy_pipeline(
    raw_text: str,
    filename_meta: dict,
    file_reference_date: str | None,
) -> dict:
    """Legacy single-call extraction pipeline."""
    extracted = extract_candidate_data(
        raw_text,
        file_reference_date=file_reference_date,
    )
    extracted = apply_regex_field_filters(extracted)
    if not extracted:
        logger.warning("LLM extraction returned None")
        return {
            "extracted": None,
            "diagnosis": {
                "verdict": "fail",
                "issues": [],
                "field_scores": {},
                "overall_score": 0.0,
            },
            "attempts": 1,
            "retry_action": "human_review",
            "raw_text_used": raw_text,
            "integrity_flags": [],
        }

    rule_result = validate_extraction(extracted, filename_meta)
    diagnosis = {
        "verdict": "pass" if rule_result["validation_status"] == "auto_confirmed" else "fail",
        "issues": rule_result["issues"],
        "field_scores": rule_result["field_confidences"],
        "overall_score": rule_result["confidence_score"],
    }

    retry_action = "none" if diagnosis["verdict"] == "pass" else "human_review"

    return {
        "extracted": extracted,
        "diagnosis": diagnosis,
        "attempts": 1,
        "retry_action": retry_action,
        "raw_text_used": raw_text,
        "integrity_flags": [],
    }


def apply_cross_version_comparison(
    pipeline_result: dict,
    previous_data: dict | None,
) -> dict:
    """Attach cross-version flags after identity is resolved from extracted data."""
    extracted = pipeline_result.get("extracted")
    if not extracted or not previous_data:
        return pipeline_result

    from data_extraction.services.extraction.integrity import compare_versions

    cross_version_flags = compare_versions(
        {
            "careers": extracted.get("careers", []),
            "educations": extracted.get("educations", []),
        },
        previous_data,
    )
    if not cross_version_flags:
        return pipeline_result

    combined_flags = [
        *pipeline_result.get("integrity_flags", []),
        *cross_version_flags,
    ]
    pipeline_result["integrity_flags"] = combined_flags
    extracted["integrity_flags"] = combined_flags
    pipeline_result["diagnosis"] = _build_integrity_diagnosis(
        combined_flags,
        extracted.get("field_confidences", {}),
    )
    pipeline_result["retry_action"] = (
        "human_review"
        if any(f.get("severity") == "RED" for f in combined_flags)
        else "none"
    )
    return pipeline_result


def _build_integrity_diagnosis(flags: list[dict], field_scores: dict) -> dict:
    from data_extraction.services.validation import compute_overall_confidence

    red_count = sum(1 for f in flags if f.get("severity") == "RED")
    yellow_count = sum(1 for f in flags if f.get("severity") == "YELLOW")
    score = max(0.0, 1.0 - (red_count * 0.25) - (yellow_count * 0.1))

    # Apply critical field gates via compute_overall_confidence
    _, gated_status = compute_overall_confidence({"_": score}, [], field_scores)

    if gated_status == "failed":
        verdict = "fail"
    elif red_count:
        verdict = "fail"
    else:
        verdict = "pass"

    return {
        "verdict": verdict,
        "issues": [
            {"severity": f["severity"], "message": f["detail"]}
            for f in flags
        ],
        "field_scores": field_scores,
        "overall_score": round(score, 3),
    }
