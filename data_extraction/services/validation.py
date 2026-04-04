"""Rule-based validation for resume extraction: data rules + filename cross-check."""

from __future__ import annotations


def _date_to_number(date_str: str) -> float | None:
    """Convert a date string like '2020.03' to a float like 2020.03.

    Returns None if the string cannot be parsed.
    """
    if not date_str or not isinstance(date_str, str):
        return None
    parts = date_str.strip().replace("-", ".").split(".")
    if len(parts) == 2:
        try:
            year = int(parts[0])
            month = int(parts[1])
            return year + month / 100.0
        except (ValueError, TypeError):
            return None
    if len(parts) == 1:
        try:
            return float(parts[0])
        except (ValueError, TypeError):
            return None
    return None


def validate_rules(data: dict) -> list[dict]:
    """Layer 2: Rule-based validation.

    Returns a list of issue dicts:
        [{"field": str, "severity": "error"|"warning", "message": str}]

    Rules:
    - name required (empty -> error)
    - birth_year range 1940-2005 (outside -> error)
    - career date order: start_date <= end_date (reversed -> warning)
    """
    issues: list[dict] = []

    # Name required
    name = data.get("name", "")
    if not name or (isinstance(name, str) and not name.strip()):
        issues.append(
            {
                "field": "name",
                "severity": "error",
                "message": "Name is required",
            }
        )

    # Birth year range
    birth_year = data.get("birth_year")
    if birth_year is not None:
        if not (1940 <= birth_year <= 2005):
            issues.append(
                {
                    "field": "birth_year",
                    "severity": "error",
                    "message": f"Birth year {birth_year} is outside valid range (1940-2005)",
                }
            )

    # Career date order
    careers = data.get("careers", [])
    for idx, career in enumerate(careers):
        start = _date_to_number(career.get("start_date", ""))
        end = _date_to_number(career.get("end_date", "")) or _date_to_number(
            career.get("end_date_inferred", "")
        )
        if start is not None and end is not None and start > end:
            end_label = career.get("end_date") or career.get("end_date_inferred")
            issues.append(
                {
                    "field": f"careers[{idx}].date_order",
                    "severity": "warning",
                    "message": (
                        f"Career #{idx + 1} start_date ({career['start_date']}) "
                        f"is after end_date ({end_label})"
                    ),
                }
            )

        date_confidence = career.get("date_confidence")
        if date_confidence is not None:
            try:
                confidence_value = float(date_confidence)
            except (TypeError, ValueError):
                confidence_value = None
            if confidence_value is None or not (0.0 <= confidence_value <= 1.0):
                issues.append(
                    {
                        "field": f"careers[{idx}].date_confidence",
                        "severity": "warning",
                        "message": (
                            f"Career #{idx + 1} date_confidence ({date_confidence}) "
                            "is outside valid range (0.0-1.0)"
                        ),
                    }
                )

    return issues


def validate_cross_check(filename_parsed: dict, extracted: dict) -> list[dict]:
    """Layer 3: Cross-check filename parse result vs LLM extraction.

    Compares parse_filename() result with LLM-extracted data.
    Skips if filename_parsed has no name (unparseable).

    Returns a list of issue dicts with severity "warning".
    """
    issues: list[dict] = []

    # Skip if filename was unparseable
    if not filename_parsed.get("name"):
        return issues

    # Name mismatch
    parsed_name = filename_parsed.get("name")
    extracted_name = extracted.get("name")
    if parsed_name and extracted_name and parsed_name != extracted_name:
        issues.append(
            {
                "field": "name",
                "severity": "warning",
                "message": (
                    f"Name mismatch: filename says '{parsed_name}', "
                    f"extraction says '{extracted_name}'"
                ),
            }
        )

    # Birth year mismatch
    parsed_year = filename_parsed.get("birth_year")
    extracted_year = extracted.get("birth_year")
    if (
        parsed_year is not None
        and extracted_year is not None
        and parsed_year != extracted_year
    ):
        issues.append(
            {
                "field": "birth_year",
                "severity": "warning",
                "message": (
                    f"Birth year mismatch: filename says {parsed_year}, "
                    f"extraction says {extracted_year}"
                ),
            }
        )

    return issues


def compute_overall_confidence(
    field_confidences: dict, issues: list[dict]
) -> tuple[float, str]:
    """Compute overall confidence score and validation status.

    Base score = field_confidences["overall"] or average of values.
    Penalty: -0.15 per error, -0.05 per warning.
    Thresholds:
        >= 0.85 -> "auto_confirmed"
        0.6-0.85 -> "needs_review"
        < 0.6 -> "failed"

    Returns (rounded_score, status).
    """
    # Base score
    if "overall" in field_confidences:
        base = field_confidences["overall"]
    else:
        values = [v for v in field_confidences.values() if isinstance(v, (int, float))]
        base = sum(values) / len(values) if values else 0.0

    # Apply penalties
    score = base
    for issue in issues:
        if issue.get("severity") == "error":
            score -= 0.15
        elif issue.get("severity") == "warning":
            score -= 0.05

    # Clamp to [0, 1]
    score = max(0.0, min(1.0, score))
    score = round(score, 3)

    # Determine status
    if score >= 0.85:
        status = "auto_confirmed"
    elif score >= 0.6:
        status = "needs_review"
    else:
        status = "failed"

    return score, status


def validate_extraction(extracted: dict, filename_parsed: dict) -> dict:
    """Run full 3-layer validation on an extraction result.

    Combines rule-based validation, cross-check, and confidence scoring.

    Returns:
        {
            "confidence_score": float,
            "validation_status": str,
            "field_confidences": dict,
            "issues": list[dict],
        }
    """
    # Gather all issues
    rule_issues = validate_rules(extracted)
    cross_issues = validate_cross_check(filename_parsed, extracted)
    all_issues = rule_issues + cross_issues

    # Get field confidences from extracted data
    field_confidences = extracted.get("field_confidences", {})

    # Compute overall confidence
    score, status = compute_overall_confidence(field_confidences, all_issues)

    return {
        "confidence_score": score,
        "validation_status": status,
        "field_confidences": field_confidences,
        "issues": all_issues,
    }
