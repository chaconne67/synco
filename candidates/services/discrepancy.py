"""Rule-based discrepancy scanner for candidate self-consistency."""

from __future__ import annotations

from collections import Counter
import re

from django.utils import timezone

from candidates.models import (
    Candidate,
    DiscrepancyReport,
    _month_index,
    _parse_year_month,
)

LAYER_SELF_CONSISTENCY = "self_consistency"
SEVERITY_ORDER = {"RED": 0, "YELLOW": 1, "BLUE": 2}
SEVERITY_PENALTIES = {"RED": 0.25, "YELLOW": 0.1, "BLUE": 0.03}


def _severity_rank(severity: str) -> int:
    return SEVERITY_ORDER.get(severity, 99)


def _downgrade_severity(severity: str) -> str:
    if severity == "RED":
        return "YELLOW"
    if severity == "YELLOW":
        return "BLUE"
    return "BLUE"


def _build_alert(
    *,
    alert_type: str,
    severity: str,
    field: str,
    detail: str,
    evidence: dict | None = None,
    confidence_gate: dict | None = None,
) -> dict:
    alert = {
        "type": alert_type,
        "severity": severity,
        "field": field,
        "layer": LAYER_SELF_CONSISTENCY,
        "detail": detail,
    }
    if evidence:
        alert["evidence"] = evidence
    if confidence_gate:
        alert["confidence_gate"] = confidence_gate
    return alert


def _apply_field_confidence(alert: dict, field_confidence: float | None) -> dict:
    if field_confidence is None or field_confidence >= 0.9:
        return alert

    downgraded = dict(alert)
    downgraded["severity"] = _downgrade_severity(alert["severity"])
    downgraded["confidence_gate"] = {
        "field_confidence": round(field_confidence, 3),
        "downgraded": True,
    }
    return downgraded


def _normalize_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", (value or "").lower(), flags=re.UNICODE)


def _normalize_company_name(company: str) -> str:
    return _normalize_text(company)


def _field_confidence(candidate: Candidate, field: str) -> float | None:
    return (candidate.field_confidences or {}).get(field)


def _same_role(current: dict, other: dict) -> bool:
    return (
        current["department_key"]
        and current["department_key"] == other["department_key"]
    ) or (current["position_key"] and current["position_key"] == other["position_key"])


def _classify_overlap_case(current: dict, other: dict, overlap_months: int) -> dict:
    same_company = (
        current["company_key"] and current["company_key"] == other["company_key"]
    )
    same_role = _same_role(current, other)

    if same_company and not same_role:
        return {
            "skip": True,
            "reason": "same_company_internal_transfer",
            "same_company": True,
            "same_role": False,
        }

    if same_company and same_role:
        return {
            "skip": False,
            "severity": "BLUE",
            "reason": "same_company_same_role_overlap",
            "same_company": True,
            "same_role": True,
        }

    if overlap_months <= 3:
        return {
            "skip": False,
            "severity": "BLUE",
            "reason": "short_cross_company_transition_overlap",
            "same_company": False,
            "same_role": same_role,
        }

    return {
        "skip": False,
        "severity": "YELLOW",
        "reason": "cross_company_overlap",
        "same_company": False,
        "same_role": same_role,
    }


def _education_stage_context(education) -> dict:
    institution = _normalize_text(education.institution)
    degree = _normalize_text(education.degree)

    if "highschool" in institution or "고등학교" in (education.institution or ""):
        return {
            "stage": "high_school",
            "min_age": 15,
            "label": "고등학교",
        }
    if (
        any(token in degree for token in ("석사", "박사", "mba", "master", "phd"))
        or "대학원" in (education.institution or "")
        or "graduateschool" in institution
    ):
        return {
            "stage": "graduate",
            "min_age": 21,
            "label": "대학원",
        }
    if (
        any(token in degree for token in ("학사", "학부", "bachelor"))
        or "대학교" in (education.institution or "")
        or "대학" in (education.institution or "")
        or "university" in institution
        or "college" in institution
    ):
        return {
            "stage": "undergraduate",
            "min_age": 17,
            "label": "대학교",
        }
    return {
        "stage": "unknown",
        "min_age": 15,
        "label": "일반 학력",
    }


def _latest_career_missing_end_date_exception(candidate: Candidate) -> dict | None:
    latest_missing = None
    latest_start_index = None

    for career in candidate.careers.all():
        if career.is_current or career.end_date.strip():
            continue

        start = _parse_year_month(career.start_date, default_month=1)
        if start is None:
            continue

        start_index = _month_index(*start)
        if latest_start_index is None or start_index > latest_start_index:
            latest_start_index = start_index
            latest_missing = career

    if latest_missing is None:
        return None

    return {
        "reason": "latest_career_missing_end_date",
        "company": latest_missing.company,
        "position": latest_missing.position,
        "department": latest_missing.department,
        "start_date": latest_missing.start_date,
    }


def _career_records(candidate: Candidate) -> list[dict]:
    today = timezone.localdate()
    current_month_index = _month_index(today.year, today.month)

    records: list[dict] = []
    for career in candidate.careers.all():
        start = _parse_year_month(career.start_date, default_month=1)
        raw_end = _parse_year_month(career.end_date, default_month=12)

        record = {
            "career": career,
            "start": start,
            "raw_end": raw_end,
            "future_start": False,
            "future_end": False,
            "future_start_months": 0,
            "future_end_months": 0,
            "date_order_invalid": False,
            "interval": None,
        }

        if start is not None and _month_index(*start) > current_month_index:
            record["future_start"] = True
            record["future_start_months"] = _month_index(*start) - current_month_index

        end = None
        if career.is_current and not career.end_date.strip():
            end = (today.year, today.month)
        elif raw_end is not None:
            if _month_index(*raw_end) > current_month_index:
                record["future_end"] = True
                record["future_end_months"] = (
                    _month_index(*raw_end) - current_month_index
                )
                end = (today.year, today.month)
            else:
                end = raw_end

        if start is not None and end is not None:
            start_index = _month_index(*start)
            end_index = _month_index(*end)
            if end_index < start_index:
                record["date_order_invalid"] = True
            else:
                record["interval"] = (start_index, end_index)

        records.append(record)

    return records


def check_career_overlaps(candidate: Candidate) -> list[dict]:
    intervals = [
        {
            "company": record["career"].company,
            "company_key": _normalize_company_name(record["career"].company),
            "position_key": _normalize_text(record["career"].position),
            "department_key": _normalize_text(record["career"].department),
            "start_date": record["career"].start_date,
            "end_date": record["career"].end_date or "현재",
            "start_index": record["interval"][0],
            "end_index": record["interval"][1],
        }
        for record in _career_records(candidate)
        if record["interval"] is not None
    ]
    intervals.sort(key=lambda item: item["start_index"])

    overlaps: list[dict] = []
    skipped_contexts: list[dict] = []
    for idx, current in enumerate(intervals):
        for other in intervals[idx + 1 :]:
            if other["start_index"] > current["end_index"]:
                break
            overlap_months = (
                min(current["end_index"], other["end_index"]) - other["start_index"] + 1
            )
            if overlap_months <= 1:
                continue
            context = _classify_overlap_case(current, other, overlap_months)
            if context["skip"]:
                skipped_contexts.append(
                    {
                        "career_a_company": current["company"],
                        "career_b_company": other["company"],
                        "reason": context["reason"],
                        "overlap_months": overlap_months,
                    }
                )
                continue
            overlaps.append(
                {
                    "career_a": {
                        "company": current["company"],
                        "start": current["start_date"],
                        "end": current["end_date"],
                    },
                    "career_b": {
                        "company": other["company"],
                        "start": other["start_date"],
                        "end": other["end_date"],
                    },
                    "overlap_months": overlap_months,
                    "same_company": bool(context["same_company"]),
                    "same_role": bool(context["same_role"]),
                    "reason": context["reason"],
                    "severity": context["severity"],
                }
            )

    if not overlaps:
        return []

    first = min(
        overlaps,
        key=lambda item: (_severity_rank(item["severity"]), -item["overlap_months"]),
    )
    if first["reason"] == "same_company_same_role_overlap":
        detail = (
            f"{first['career_a']['company']} 내 동일하거나 유사한 역할의 경력 기간이 "
            f"{first['overlap_months']}개월 겹칩니다. 중복 기재 또는 동시 역할일 수 있습니다."
        )
    elif first["reason"] == "short_cross_company_transition_overlap":
        detail = (
            f"{first['career_a']['company']}와 {first['career_b']['company']}의 "
            f"경력 기간이 {first['overlap_months']}개월 겹칩니다. 짧은 인수인계나 이직 겹침일 수 있습니다."
        )
    else:
        detail = (
            f"{first['career_a']['company']}와 {first['career_b']['company']}의 "
            f"경력 기간이 {first['overlap_months']}개월 겹칩니다."
        )
    severity = min((item["severity"] for item in overlaps), key=_severity_rank)
    alert = _build_alert(
        alert_type="OVERLAP",
        severity=severity,
        field="careers",
        detail=detail,
        evidence={
            "count": len(overlaps),
            "examples": overlaps[:3],
            "skipped_examples": skipped_contexts[:3],
            "considered_exceptions": [
                "same_company_internal_transfer",
                "same_company_same_role_overlap",
                "short_cross_company_transition_overlap",
            ],
        },
    )
    return [_apply_field_confidence(alert, _field_confidence(candidate, "careers"))]


def check_career_date_order(candidate: Candidate) -> list[dict]:
    invalid = []
    for record in _career_records(candidate):
        if record["date_order_invalid"]:
            career = record["career"]
            invalid.append(
                {
                    "company": career.company,
                    "start": career.start_date,
                    "end": career.end_date,
                }
            )

    if not invalid:
        return []

    first = invalid[0]
    alert = _build_alert(
        alert_type="DATE_ORDER",
        severity="YELLOW",
        field="careers",
        detail=(
            f"{first['company']} 경력의 시작일({first['start']})이 "
            f"종료일({first['end']})보다 뒤에 있습니다."
        ),
        evidence={"count": len(invalid), "examples": invalid[:3]},
    )
    return [_apply_field_confidence(alert, _field_confidence(candidate, "careers"))]


def check_future_dates(candidate: Candidate) -> list[dict]:
    future_items = []
    for record in _career_records(candidate):
        career = record["career"]
        if record["future_start"]:
            future_items.append(
                {
                    "company": career.company,
                    "date_field": "start_date",
                    "value": career.start_date,
                    "months_ahead": record["future_start_months"],
                    "is_current": career.is_current,
                }
            )
        if record["future_end"]:
            future_items.append(
                {
                    "company": career.company,
                    "date_field": "end_date",
                    "value": career.end_date,
                    "months_ahead": record["future_end_months"],
                    "is_current": career.is_current,
                }
            )

    if not future_items:
        return []

    first = future_items[0]
    max_months_ahead = max(item["months_ahead"] for item in future_items)
    exception_reason = "near_future_date"
    severity = "BLUE"
    if max_months_ahead >= 6:
        severity = "YELLOW"
        exception_reason = "significant_future_date"
    elif any(
        item["date_field"] == "end_date"
        and item["is_current"]
        and item["months_ahead"] <= 6
        for item in future_items
    ):
        severity = "BLUE"
        exception_reason = "planned_end_date_for_current_role"
    alert = _build_alert(
        alert_type="FUTURE_DATE",
        severity=severity,
        field="careers",
        detail=(
            f"{first['company']} 경력의 {first['date_field']} 값({first['value']})이 "
            f"현재 기준 약 {first['months_ahead']}개월 미래입니다."
        ),
        evidence={
            "count": len(future_items),
            "examples": future_items[:3],
            "applied_exception": exception_reason,
            "considered_exceptions": [
                "near_future_date",
                "planned_end_date_for_current_role",
            ],
        },
    )
    return [_apply_field_confidence(alert, _field_confidence(candidate, "careers"))]


def check_experience_total(candidate: Candidate) -> list[dict]:
    discrepancy = candidate.experience_discrepancy_months
    if discrepancy is None or discrepancy < 12:
        return []

    severity = "RED" if discrepancy >= 36 else "YELLOW"
    applied_exception = None
    if (
        candidate.effective_resume_reference_date_display
        and candidate.reference_total_experience_display
    ):
        reference_label = candidate.effective_resume_reference_date_display
        if (
            candidate.effective_resume_reference_source
            == candidate.ResumeReferenceDateSource.INFERRED
        ):
            reference_label = f"추정 {reference_label}"
        detail = (
            f"이력서 표기 {candidate.extracted_total_experience_display}과 "
            f"{reference_label} 기준 경력 합산 "
            f"{candidate.reference_total_experience_display}의 차이가 큽니다."
        )
        computed_display = candidate.reference_total_experience_display
    else:
        detail = (
            f"이력서 표기 {candidate.extracted_total_experience_display}과 "
            f"경력 합산 {candidate.computed_total_experience_display}의 차이가 큽니다."
        )
        computed_display = candidate.computed_total_experience_display

    latest_missing_end = _latest_career_missing_end_date_exception(candidate)
    if latest_missing_end:
        severity = _downgrade_severity(severity)
        applied_exception = latest_missing_end["reason"]
        detail = (
            f"이력서 표기 {candidate.extracted_total_experience_display}과 "
            f"경력 합산 {computed_display}의 차이가 큽니다. "
            f"다만 최근 경력으로 보이는 {latest_missing_end['company']}의 종료일이 비어 있어 "
            "총 경력이 작게 계산됐을 수 있습니다."
        )
    elif candidate.ignored_career_count:
        severity = _downgrade_severity(severity)
        applied_exception = "ignored_career_in_total_experience"
        detail = (
            f"이력서 표기 {candidate.extracted_total_experience_display}과 "
            f"경력 합산 {computed_display}의 차이가 큽니다. "
            f"다만 날짜가 불완전한 경력 {candidate.ignored_career_count}건이 계산에서 제외되어 "
            "차이가 커졌을 수 있습니다."
        )

    alert = _build_alert(
        alert_type="EXPERIENCE_MISMATCH",
        severity=severity,
        field="total_experience_years",
        detail=detail,
        evidence={
            "extracted": candidate.extracted_total_experience_display,
            "computed": computed_display,
            "difference_months": discrepancy,
            "reference_date": candidate.effective_resume_reference_date_display,
            "applied_exception": applied_exception,
            "exception_context": latest_missing_end,
        },
    )
    field_confidence = (candidate.field_confidences or {}).get("total_experience_years")
    return [_apply_field_confidence(alert, field_confidence)]


def check_education_age(candidate: Candidate) -> list[dict]:
    if candidate.birth_year is None:
        return []

    mismatches = []
    for education in candidate.educations.all():
        if education.start_year is None:
            continue
        age = education.start_year - candidate.birth_year
        context = _education_stage_context(education)
        if age >= context["min_age"]:
            continue

        gap = context["min_age"] - age
        severity = "YELLOW" if gap >= 2 else "BLUE"
        if education.is_abroad and severity == "YELLOW":
            severity = "BLUE"

        if context["stage"] == "high_school":
            detail = (
                f"{education.institution} 시작 시점 추정 나이 {age}세로 "
                "일반적인 고등학교 입학 시점보다 이릅니다."
            )
        elif context["stage"] == "undergraduate":
            detail = (
                f"{education.institution} 시작 시점 추정 나이 {age}세로 "
                "일반적인 대학교 입학 시점보다 이릅니다."
            )
        elif context["stage"] == "graduate":
            detail = (
                f"{education.institution} 시작 시점 추정 나이 {age}세로 "
                "일반적인 대학원 진학 시점보다 이릅니다."
            )
        else:
            detail = (
                f"{education.institution} 시작 시점 추정 나이 {age}세가 "
                "일반적인 학력 시작 시점보다 이른 편입니다."
            )

        mismatches.append(
            {
                "institution": education.institution,
                "start_year": education.start_year,
                "age": age,
                "severity": severity,
                "detail": detail,
                "stage": context["stage"],
                "expected_min_age": context["min_age"],
                "is_abroad": education.is_abroad,
            }
        )

    if not mismatches:
        return []

    first = min(
        mismatches, key=lambda item: (_severity_rank(item["severity"]), item["age"])
    )
    alert = _build_alert(
        alert_type="AGE_MISMATCH",
        severity=first["severity"],
        field="educations",
        detail=first["detail"],
        evidence={
            "count": len(mismatches),
            "examples": mismatches[:3],
            "considered_exceptions": [
                "school_type_specific_min_age",
                "early_admission",
                "foreign_school_system",
            ],
        },
    )
    return [_apply_field_confidence(alert, _field_confidence(candidate, "educations"))]


def check_education_completeness(candidate: Candidate) -> list[dict]:
    alerts = []

    degrees = []
    for education in candidate.educations.all():
        degree = (education.degree or "").strip()
        if degree:
            degrees.append(degree)

    if degrees:
        normalized = [degree.lower() for degree in degrees]
        has_undergrad = any(
            token in degree
            for degree in normalized
            for token in ("학사", "학부", "bachelor")
        )
        has_grad_only = all(
            any(token in degree for token in ("석사", "박사", "mba", "master", "phd"))
            for degree in normalized
        )
        if has_grad_only and not has_undergrad:
            degree_counts = Counter(degrees)
            top_degree = degree_counts.most_common(1)[0][0]
            alerts.append(
                _apply_field_confidence(
                    _build_alert(
                        alert_type="MISSING_UNDERGRAD",
                        severity="BLUE",
                        field="educations",
                        detail=(
                            f"학력 정보가 {top_degree} 이상만 있고 학부 정보가 보이지 않습니다."
                        ),
                        evidence={"degrees": degrees},
                    ),
                    _field_confidence(candidate, "educations"),
                )
            )

    return alerts


def _build_summary(alerts: list[dict]) -> str:
    if not alerts:
        return "내부 일관성 기준으로 특이사항이 없습니다."

    counts = Counter(alert["severity"] for alert in alerts)
    parts = []
    for severity in ("RED", "YELLOW", "BLUE"):
        if counts.get(severity):
            label = {"RED": "중요", "YELLOW": "주의", "BLUE": "참고"}[severity]
            parts.append(f"{label} {counts[severity]}건")

    summary = ", ".join(parts)
    first_detail = alerts[0].get("detail")
    if first_detail:
        return f"{summary}. {first_detail}"
    return summary


def compute_integrity_score(alerts: list[dict]) -> float:
    score = 1.0
    for alert in alerts:
        score -= SEVERITY_PENALTIES.get(alert.get("severity"), 0.0)
    return round(max(0.0, min(1.0, score)), 3)


def scan_candidate_discrepancies(
    candidate: Candidate,
    *,
    source_resume=None,
    save: bool = True,
    scan_version: str = "v3",
) -> DiscrepancyReport | dict:
    alerts = []
    alerts.extend(check_career_overlaps(candidate))
    alerts.extend(check_career_date_order(candidate))
    alerts.extend(check_future_dates(candidate))
    alerts.extend(check_experience_total(candidate))
    alerts.extend(check_education_age(candidate))
    alerts.extend(check_education_completeness(candidate))
    alerts.sort(key=lambda alert: (_severity_rank(alert["severity"]), alert["type"]))

    integrity_score = compute_integrity_score(alerts)
    summary = _build_summary(alerts)

    if not save:
        return {
            "candidate": candidate,
            "report_type": DiscrepancyReport.ReportType.SELF_CONSISTENCY,
            "integrity_score": integrity_score,
            "summary": summary,
            "alerts": alerts,
            "scan_version": scan_version,
        }

    return DiscrepancyReport.objects.create(
        candidate=candidate,
        source_resume=source_resume,
        report_type=DiscrepancyReport.ReportType.SELF_CONSISTENCY,
        integrity_score=integrity_score,
        summary=summary,
        alerts=alerts,
        scan_version=scan_version,
    )
