"""Retry orchestrator: extract -> validate -> retry with root-cause-specific strategy."""

from __future__ import annotations

import logging

from candidates.services.codex_validation import validate_with_codex
from candidates.services.fewshot_store import (
    format_fewshot_prompt,
    get_fewshot_examples,
)
from candidates.services.llm_extraction import extract_candidate_data
from candidates.services.text_extraction import extract_text_libreoffice
from candidates.services.validation import validate_extraction

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _dominant_root_cause(issues: list[dict]) -> str:
    """Determine the dominant root cause from critical issues."""
    critical = [i for i in issues if i.get("severity") == "critical"]
    if not critical:
        return "none"
    causes = [i.get("root_cause", "ambiguous_source") for i in critical]
    if "text_extraction" in causes:
        return "text_extraction"
    if "llm_parsing" in causes:
        return "llm_parsing"
    return "ambiguous_source"


def _build_diagnosis_hints(diagnosis: dict) -> str:
    """Build prompt hints from Codex diagnosis for retry."""
    issues = diagnosis.get("issues", [])
    if not issues:
        return ""
    lines = ["\n\n## 이전 추출에서 발견된 문제 (반드시 교정하세요)\n"]
    for issue in issues:
        field = issue.get("field", "")
        evidence = issue.get("evidence", "")
        suggested = issue.get("suggested_value", "")
        lines.append(f"- **{field}**: {evidence}")
        if suggested:
            lines.append(f"  → 올바른 값: `{suggested}`")
    return "\n".join(lines)


def run_extraction_with_retry(
    raw_text: str,
    file_path: str,
    category: str,
    filename_meta: dict,
) -> dict:
    """Run extraction with Codex cross-validation and automatic retry.

    Returns:
        {
            "extracted": dict | None,
            "diagnosis": dict,
            "attempts": int,
            "retry_action": str,  # "none" | "re_extract" | "re_parse" | "human_review"
            "raw_text_used": str,
        }
    """
    current_text = raw_text
    fewshot_section = ""
    diagnosis_hints = ""
    re_extracted = False

    examples = get_fewshot_examples(category)
    if examples:
        fewshot_section = format_fewshot_prompt(examples)

    for attempt in range(1, MAX_RETRIES + 2):  # 1 initial + MAX_RETRIES
        extracted = extract_candidate_data(
            current_text,
            fewshot_section=fewshot_section + diagnosis_hints,
        )
        if not extracted:
            logger.warning("LLM extraction returned None on attempt %d", attempt)
            if attempt > MAX_RETRIES:
                return {
                    "extracted": None,
                    "diagnosis": {
                        "verdict": "fail",
                        "issues": [],
                        "field_scores": {},
                        "overall_score": 0.0,
                    },
                    "attempts": attempt,
                    "retry_action": "human_review",
                    "raw_text_used": current_text,
                }
            continue

        diagnosis = validate_with_codex(current_text, extracted, filename_meta)

        # Codex CLI failed (timeout, parse error, etc.) — fallback to rule-based validation
        # and return immediately (no more Codex retries — they'll just timeout again)
        if diagnosis["verdict"] == "error":
            logger.warning(
                "Codex CLI failed on attempt %d, falling back to rule-based validation",
                attempt,
            )
            rule_result = validate_extraction(extracted, filename_meta)
            diagnosis = {
                "verdict": "pass"
                if rule_result["confidence_score"] >= 0.85
                else "fail",
                "issues": rule_result["issues"],
                "field_scores": rule_result["field_confidences"],
                "overall_score": rule_result["confidence_score"],
            }
            return {
                "extracted": extracted,
                "diagnosis": diagnosis,
                "attempts": attempt,
                "retry_action": "rule_fallback",
                "raw_text_used": current_text,
            }

        if diagnosis["verdict"] == "pass":
            return {
                "extracted": extracted,
                "diagnosis": diagnosis,
                "attempts": attempt,
                "retry_action": "none",
                "raw_text_used": current_text,
            }

        if attempt > MAX_RETRIES:
            return {
                "extracted": extracted,
                "diagnosis": diagnosis,
                "attempts": attempt,
                "retry_action": "human_review",
                "raw_text_used": current_text,
            }

        root_cause = _dominant_root_cause(diagnosis.get("issues", []))

        if root_cause == "text_extraction" and not re_extracted:
            import shutil

            if shutil.which("libreoffice"):
                logger.info("Attempt %d: re-extracting text via LibreOffice", attempt)
                try:
                    current_text = extract_text_libreoffice(file_path)
                    re_extracted = True
                except Exception:
                    logger.exception("LibreOffice re-extraction failed")
            else:
                logger.info("LibreOffice not installed, skipping re-extraction")
                re_extracted = True  # prevent repeated attempts

        elif root_cause == "llm_parsing":
            logger.info("Attempt %d: retrying with diagnosis hints", attempt)
            diagnosis_hints = _build_diagnosis_hints(diagnosis)

        elif root_cause == "ambiguous_source":
            return {
                "extracted": extracted,
                "diagnosis": diagnosis,
                "attempts": attempt,
                "retry_action": "human_review",
                "raw_text_used": current_text,
            }

    return {
        "extracted": extracted,  # type: ignore[possibly-undefined]
        "diagnosis": diagnosis,  # type: ignore[possibly-undefined]
        "attempts": MAX_RETRIES + 1,
        "retry_action": "human_review",
        "raw_text_used": current_text,
    }
