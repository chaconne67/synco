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


import re


def compute_field_confidences(
    extracted: dict, filename_parsed: dict
) -> tuple[dict, dict]:
    """Compute per-field quality scores and category scores from extraction result.

    Returns (field_scores, category_scores).

    field_scores: individual field keys for discrepancy.py compatibility
    category_scores: 4 category scores for UI display and overall confidence
    """
    fc = {}

    # name: present + filename match
    name = (extracted.get("name") or "").strip()
    if not name:
        fc["name"] = 0.0
    else:
        parsed_name = (filename_parsed.get("name") or "").strip()
        fc["name"] = 1.0 if (not parsed_name or parsed_name == name) else 0.7

    # birth_year: present + valid range
    birth_year = extracted.get("birth_year")
    if birth_year is None:
        fc["birth_year"] = 0.0
    elif 1940 <= birth_year <= 2005:
        parsed_year = filename_parsed.get("birth_year")
        fc["birth_year"] = (
            1.0 if (parsed_year is None or parsed_year == birth_year) else 0.7
        )
    else:
        fc["birth_year"] = 0.3

    # email: valid format
    email = (extracted.get("email") or "").strip()
    if not email:
        fc["email"] = 0.0
    elif re.match(r"[^@]+@[^@]+\.[^@]+", email):
        fc["email"] = 1.0
    else:
        fc["email"] = 0.5

    # phone: normalized successfully
    phone = (extracted.get("phone") or "").strip()
    if not phone:
        fc["phone"] = 0.0
    else:
        digits = re.sub(r"\D", "", phone)
        fc["phone"] = 1.0 if len(digits) >= 10 else 0.7

    # address
    fc["address"] = 1.0 if (extracted.get("address") or "").strip() else 0.0

    # current_company
    fc["current_company"] = (
        1.0 if (extracted.get("current_company") or "").strip() else 0.0
    )

    # current_position
    fc["current_position"] = (
        1.0 if (extracted.get("current_position") or "").strip() else 0.0
    )

    # summary
    fc["summary"] = 1.0 if (extracted.get("summary") or "").strip() else 0.0

    # careers: present + dates quality
    careers = extracted.get("careers") or []
    if not careers:
        fc["careers"] = 0.0
    else:
        dated = sum(1 for c in careers if c.get("start_date"))
        ratio = dated / len(careers)
        fc["careers"] = round(0.5 + 0.5 * ratio, 2)

    # educations
    educations = extracted.get("educations") or []
    if not educations:
        fc["educations"] = 0.0
    else:
        fc["educations"] = 1.0

    # Category scores (4 categories for UI display)
    category_scores = {}

    # 인적사항: name, email, phone
    personal_items = [fc["name"], fc["email"], fc["phone"]]
    category_scores["인적사항"] = sum(personal_items) / len(personal_items)

    # 학력: educations
    category_scores["학력"] = fc["educations"]

    # 경력: careers
    category_scores["경력"] = fc["careers"]

    # 능력: skills + (certifications or language_skills)
    skills_val = extracted.get("skills") or []
    skills_score = 1.0 if skills_val else 0.0
    certs = extracted.get("certifications") or []
    langs = extracted.get("language_skills") or []
    cert_lang_score = 1.0 if (certs or langs) else 0.0
    category_scores["능력"] = (skills_score + cert_lang_score) / 2

    return fc, category_scores


def compute_overall_confidence(
    category_scores: dict,
    issues: list[dict],
    field_scores: dict | None = None,
) -> tuple[float, str]:
    """Compute overall confidence score from category scores and issue penalties.

    Base = average of category_scores.
    Penalty: -0.05 per error, -0.02 per warning.

    Critical field gates (applied before status thresholds):
    - name missing (0.0) → always "failed"
    - both email and phone missing → cap at "needs_review"
    """
    values = [v for v in category_scores.values() if isinstance(v, (int, float))]
    base = sum(values) / len(values) if values else 0.0

    score = base
    for issue in issues:
        if issue.get("severity") == "error":
            score -= 0.05
        elif issue.get("severity") == "warning":
            score -= 0.02

    score = max(0.0, min(1.0, round(score, 3)))

    # Critical field gates (override average-based status)
    if field_scores:
        if field_scores.get("name", 0) == 0.0:
            return score, "failed"
        if field_scores.get("email", 0) == 0.0 and field_scores.get("phone", 0) == 0.0:
            if score >= 0.85:
                return score, "needs_review"

    if score >= 0.85:
        status = "auto_confirmed"
    elif score >= 0.6:
        status = "needs_review"
    else:
        status = "failed"

    return score, status


def validate_extraction(extracted: dict, filename_parsed: dict) -> dict:
    """Run full validation: field quality scoring + rule checks + confidence.

    Returns:
        {
            "confidence_score": float,
            "validation_status": str,
            "field_confidences": dict,
            "issues": list[dict],
        }
    """
    rule_issues = validate_rules(extracted)
    cross_issues = validate_cross_check(filename_parsed, extracted)
    all_issues = rule_issues + cross_issues

    field_scores, category_scores = compute_field_confidences(
        extracted, filename_parsed
    )

    score, status = compute_overall_confidence(
        category_scores, all_issues, field_scores
    )

    return {
        "confidence_score": score,
        "validation_status": status,
        "field_confidences": field_scores,
        "issues": all_issues,
    }
