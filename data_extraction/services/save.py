"""DB persistence for integrity pipeline results."""

from __future__ import annotations

import logging
import re

from django.db import models, transaction

from candidates.models import (
    Candidate,
    Career,
    Certification,
    Category,
    DiscrepancyReport,
    Education,
    ExtractionLog,
    LanguageSkill,
    Resume,
    ValidationDiagnosis,
)
from candidates.services.discrepancy import (
    compute_integrity_score,
    scan_candidate_discrepancies,
    _build_summary,
)

logger = logging.getLogger(__name__)


def _t(value: str | None, max_len: int = 200) -> str:
    s = value or ""
    return s[:max_len]


def _sanitize_phone(value: str | None) -> str:
    from candidates.services.candidate_identity import select_primary_phone

    return _t(select_primary_phone(value or ""), 255)



def _sanitize_reference_date(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""

    if re.fullmatch(r"\d{4}(?:[-./]\d{1,2}(?:[-./]\d{1,2})?)?", text):
        return text[:255]

    return _t(text, 255)


def save_pipeline_result(
    pipeline_result: dict,
    raw_text: str,
    category: Category,
    primary_file: dict,
    other_files: list[dict] | None = None,
    existing_ids: set | None = None,
    comparison_context=None,
) -> Candidate | None:
    """Save integrity pipeline result to DB.

    Storage policy:
    - Candidate = person (reused if email/phone matches existing)
    - Resume = version (always created new)
    - On update: sub-records (Career, Education, etc.) are rebuilt from latest extraction
    - current_resume tracks which Resume the current profile is based on
    """
    extracted = pipeline_result.get("extracted")
    if not extracted:
        if raw_text and raw_text.strip():
            _save_text_only_resume(
                primary_file,
                category.name,
                raw_text=raw_text,
                error_msg="Structured extraction unavailable; stored raw text only",
            )
        else:
            _save_failed_resume(primary_file, category.name, "Extraction failed")
        return None

    diagnosis = pipeline_result["diagnosis"]
    field_confidences = extracted.get("field_confidences", {})
    overall_score = diagnosis.get("overall_score", 0.0)
    validation = {
        "confidence_score": overall_score,
        "validation_status": (
            "auto_confirmed"
            if diagnosis["verdict"] == "pass" and overall_score >= 0.85
            else "needs_review"
            if overall_score >= 0.6
            else "failed"
        ),
        "field_confidences": {
            **field_confidences,
            **diagnosis.get("field_scores", {}),
        },
        "issues": diagnosis.get("issues", []),
    }

    other_files = other_files or []
    existing_ids = existing_ids or set()

    from candidates.services.candidate_identity import build_candidate_comparison_context

    comparison_context = comparison_context or build_candidate_comparison_context(extracted)
    matched_candidate = comparison_context.candidate if comparison_context else None
    compared_resume = comparison_context.compared_resume if comparison_context else None

    if matched_candidate:
        logger.info(
            "Matched existing candidate %s via %s",
            matched_candidate.id, comparison_context.match_reason,
        )

    with transaction.atomic():
        if matched_candidate:
            candidate = _update_candidate(
                matched_candidate, extracted, raw_text, validation, category, primary_file,
            )
        else:
            candidate = _create_candidate(
                extracted, raw_text, validation, category, primary_file,
            )

        _rebuild_sub_records(candidate, extracted)
        candidate.resumes.update(is_primary=False)

        max_version = candidate.resumes.aggregate(
            max_v=models.Max("version"),
        )["max_v"] or 0
        next_version = max_version + 1

        primary_resume = Resume.objects.create(
            candidate=candidate,
            file_name=primary_file["file_name"],
            drive_file_id=primary_file["file_id"],
            drive_folder=category.name,
            mime_type=primary_file.get("mime_type", ""),
            file_size=primary_file.get("file_size"),
            raw_text=raw_text,
            is_primary=True,
            version=next_version,
            processing_status=Resume.ProcessingStatus.STRUCTURED,
        )

        candidate.current_resume = primary_resume
        candidate.save()

        for idx, other in enumerate(other_files):
            if other["file_id"] not in existing_ids:
                Resume.objects.create(
                    candidate=candidate,
                    file_name=other["file_name"],
                    drive_file_id=other["file_id"],
                    drive_folder=category.name,
                    mime_type=other.get("mime_type", ""),
                    file_size=other.get("file_size"),
                    is_primary=False,
                    version=next_version + idx + 1,
                    processing_status=Resume.ProcessingStatus.PENDING,
                )

        ExtractionLog.objects.create(
            candidate=candidate,
            resume=primary_resume,
            action=ExtractionLog.Action.AUTO_EXTRACT,
            field_name="full_extraction",
            new_value=str(extracted),
            confidence=validation["confidence_score"],
            note=f"Imported from Drive folder: {category.name}",
        )

        ValidationDiagnosis.objects.create(
            candidate=candidate,
            resume=primary_resume,
            attempt_number=pipeline_result["attempts"],
            verdict=diagnosis["verdict"],
            overall_score=diagnosis.get("overall_score", 0.0),
            issues=diagnosis.get("issues", []),
            field_scores=diagnosis.get("field_scores", {}),
            retry_action=pipeline_result["retry_action"],
        )

        candidate.categories.add(category)

        # Combined discrepancy report: integrity flags + rule-based scan
        # Merge into a single report to avoid UI collision
        integrity_flags = pipeline_result.get("integrity_flags", [])
        integrity_alerts = _convert_flags_to_alerts(integrity_flags)

        rule_report = scan_candidate_discrepancies(
            candidate, source_resume=primary_resume, save=False,
        )
        rule_alerts = rule_report.get("alerts", []) if isinstance(rule_report, dict) else []

        # Normalize type names for dedup (integrity vs rule-based use different names)
        type_aliases = {
            "PERIOD_OVERLAP": "OVERLAP",
            "DATE_CONFLICT": "DATE_ORDER",
        }

        def _dedup_key(alert: dict) -> tuple:
            atype = alert.get("type", "")
            normalized_type = type_aliases.get(atype, atype)
            return (normalized_type, alert.get("field", ""))

        # Deduplicate: if same semantic type+field exists in both, keep integrity version
        seen_keys = set()
        combined_alerts = []
        for alert in integrity_alerts:
            key = _dedup_key(alert)
            seen_keys.add(key)
            combined_alerts.append(alert)
        for alert in rule_alerts:
            key = _dedup_key(alert)
            if key not in seen_keys:
                combined_alerts.append(alert)

        combined_alerts.sort(
            key=lambda a: {"RED": 0, "YELLOW": 1, "BLUE": 2}.get(a.get("severity", ""), 3)
        )

        DiscrepancyReport.objects.create(
            candidate=candidate,
            source_resume=primary_resume,
            compared_resume=compared_resume,
            report_type=DiscrepancyReport.ReportType.SELF_CONSISTENCY,
            integrity_score=compute_integrity_score(combined_alerts),
            summary=_build_summary(combined_alerts),
            alerts=combined_alerts,
            scan_version="v4",
        )

    return candidate


def _convert_flags_to_alerts(flags: list[dict]) -> list[dict]:
    alerts = []
    for flag in flags:
        alerts.append({
            "type": flag.get("type", ""),
            "severity": flag.get("severity", "BLUE"),
            "field": flag.get("field", ""),
            "layer": "integrity_pipeline",
            "detail": flag.get("detail", ""),
            "evidence": {
                "chosen": flag.get("chosen"),
                "alternative": flag.get("alternative"),
            },
            "reasoning": flag.get("reasoning", ""),
        })
    return alerts


def _save_failed_resume(file_info: dict, folder_name: str, error_msg: str):
    Resume.objects.create(
        file_name=file_info["file_name"],
        drive_file_id=file_info["file_id"],
        drive_folder=folder_name,
        mime_type=file_info.get("mime_type", ""),
        file_size=file_info.get("file_size"),
        processing_status=Resume.ProcessingStatus.FAILED,
        error_message=error_msg,
    )


def _save_text_only_resume(
    file_info: dict,
    folder_name: str,
    *,
    raw_text: str,
    error_msg: str,
):
    Resume.objects.create(
        file_name=file_info["file_name"],
        drive_file_id=file_info["file_id"],
        drive_folder=folder_name,
        mime_type=file_info.get("mime_type", ""),
        file_size=file_info.get("file_size"),
        raw_text=raw_text,
        processing_status=Resume.ProcessingStatus.TEXT_ONLY,
        error_message=error_msg,
    )


def _update_candidate(
    candidate: Candidate,
    extracted: dict,
    raw_text: str,
    validation: dict,
    category: Category,
    primary_file: dict | None = None,
) -> Candidate:
    """Update an existing Candidate with new extraction data."""
    from candidates.services.detail_normalizers import (
        normalize_awards,
        normalize_family,
        normalize_military,
        normalize_overseas,
        normalize_patents,
        normalize_projects,
        normalize_self_intro,
        normalize_trainings,
    )
    from candidates.services.salary_parser import normalize_salary

    salary_result = normalize_salary(extracted)
    military = extracted.get("military_service") or extracted.get("military") or {}

    resume_reference_date = extracted.get("resume_reference_date") or ""
    resume_reference_source = extracted.get("resume_reference_date_source") or ""
    resume_reference_evidence = extracted.get("resume_reference_date_evidence") or ""

    if not resume_reference_date and primary_file and primary_file.get("modified_time"):
        resume_reference_date = primary_file["modified_time"]
        resume_reference_source = "file_modified_time"
        resume_reference_evidence = "Drive modifiedTime fallback"

    sanitized_phone = _sanitize_phone(extracted.get("phone"))
    sanitized_reference_date = _sanitize_reference_date(resume_reference_date)

    candidate.name = extracted.get("name") or candidate.name
    candidate.name_en = extracted.get("name_en") or candidate.name_en
    candidate.birth_year = extracted.get("birth_year") or candidate.birth_year
    candidate.gender = extracted.get("gender") or candidate.gender
    candidate.email = extracted.get("email") or candidate.email
    candidate.phone = sanitized_phone or candidate.phone
    candidate.address = extracted.get("address") or candidate.address
    candidate.current_company = extracted.get("current_company") or candidate.current_company
    candidate.current_position = extracted.get("current_position") or candidate.current_position
    candidate.total_experience_years = (
        extracted.get("total_experience_years") or candidate.total_experience_years
    )
    candidate.resume_reference_date = (
        sanitized_reference_date or candidate.resume_reference_date
    )
    candidate.resume_reference_date_source = (
        resume_reference_source or candidate.resume_reference_date_source
    )
    candidate.resume_reference_date_evidence = (
        resume_reference_evidence or candidate.resume_reference_date_evidence
    )
    candidate.core_competencies = extracted.get("core_competencies") or candidate.core_competencies
    candidate.summary = extracted.get("summary") or candidate.summary
    candidate.raw_text = raw_text
    candidate.validation_status = validation["validation_status"]
    candidate.raw_extracted_json = extracted
    candidate.confidence_score = validation["confidence_score"]
    candidate.field_confidences = validation.get("field_confidences", {})
    candidate.primary_category = category
    candidate.current_salary = salary_result["current_salary_int"] or candidate.current_salary
    candidate.desired_salary = salary_result["desired_salary_int"] or candidate.desired_salary
    candidate.salary_detail = salary_result["salary_detail"] or candidate.salary_detail
    candidate.military_service = (
        normalize_military(military) if military else candidate.military_service
    )
    candidate.awards = normalize_awards(
        extracted.get("awards") or extracted.get("honors") or []
    ) or candidate.awards
    candidate.self_introduction = normalize_self_intro(
        extracted.get("self_introduction")
        or extracted.get("personal_statement")
        or extracted.get("cover_letter")
        or extracted.get("objective")
        or ""
    ) or candidate.self_introduction
    candidate.family_info = normalize_family(
        extracted.get("family_info")
        or extracted.get("family_background")
        or extracted.get("marital_status")
        or {}
    ) or candidate.family_info
    candidate.overseas_experience = normalize_overseas(
        extracted.get("overseas_experience")
        or extracted.get("international_experience")
        or extracted.get("residence_abroad")
        or []
    ) or candidate.overseas_experience
    candidate.trainings = normalize_trainings(
        extracted.get("trainings")
        or extracted.get("training_courses")
        or extracted.get("training_programs")
        or extracted.get("education_history")
        or []
    ) or candidate.trainings
    candidate.patents = normalize_patents(
        extracted.get("patents_registered")
        or extracted.get("patents_applications")
        or extracted.get("patents")
        or []
    ) or candidate.patents
    candidate.projects = normalize_projects(
        extracted.get("projects") or []
    ) or candidate.projects

    # Don't save here — caller sets current_resume then saves once
    return candidate


def _rebuild_sub_records(candidate: Candidate, extracted: dict):
    """Delete and recreate normalized sub-records from latest extraction."""
    candidate.educations.all().delete()
    candidate.careers.all().delete()
    candidate.certifications.all().delete()
    candidate.language_skills.all().delete()

    _create_educations(candidate, extracted.get("educations", []))
    _create_careers(candidate, extracted.get("careers", []))
    _create_certifications(candidate, extracted.get("certifications", []))
    _create_language_skills(candidate, extracted.get("language_skills", []))


def _create_candidate(
    extracted: dict,
    raw_text: str,
    validation: dict,
    category: Category,
    primary_file: dict | None = None,
) -> Candidate:
    from candidates.services.detail_normalizers import (
        normalize_awards,
        normalize_family,
        normalize_military,
        normalize_overseas,
        normalize_patents,
        normalize_projects,
        normalize_self_intro,
        normalize_trainings,
    )
    from candidates.services.salary_parser import normalize_salary

    salary_result = normalize_salary(extracted)
    military = extracted.get("military_service") or extracted.get("military") or {}

    resume_reference_date = extracted.get("resume_reference_date") or ""
    resume_reference_source = extracted.get("resume_reference_date_source") or ""
    resume_reference_evidence = extracted.get("resume_reference_date_evidence") or ""

    if not resume_reference_date and primary_file and primary_file.get("modified_time"):
        resume_reference_date = primary_file["modified_time"]
        resume_reference_source = "file_modified_time"
        resume_reference_evidence = "Drive modifiedTime fallback"

    sanitized_phone = _sanitize_phone(extracted.get("phone"))
    sanitized_reference_date = _sanitize_reference_date(resume_reference_date)

    return Candidate.objects.create(
        name=extracted.get("name") or "",
        name_en=extracted.get("name_en") or "",
        birth_year=extracted.get("birth_year"),
        gender=extracted.get("gender") or "",
        email=extracted.get("email") or "",
        phone=sanitized_phone,
        address=extracted.get("address") or "",
        current_company=extracted.get("current_company") or "",
        current_position=extracted.get("current_position") or "",
        total_experience_years=extracted.get("total_experience_years"),
        resume_reference_date=sanitized_reference_date,
        resume_reference_date_source=resume_reference_source,
        resume_reference_date_evidence=resume_reference_evidence,
        core_competencies=extracted.get("core_competencies", []),
        summary=extracted.get("summary") or "",
        status=Candidate.Status.ACTIVE,
        source=Candidate.Source.DRIVE_IMPORT,
        raw_text=raw_text,
        validation_status=validation["validation_status"],
        raw_extracted_json=extracted,
        confidence_score=validation["confidence_score"],
        field_confidences=validation.get("field_confidences", {}),
        primary_category=category,
        current_salary=salary_result["current_salary_int"],
        desired_salary=salary_result["desired_salary_int"],
        salary_detail=salary_result["salary_detail"],
        military_service=normalize_military(military) if military else {},
        awards=normalize_awards(
            extracted.get("awards") or extracted.get("honors") or []
        ),
        self_introduction=normalize_self_intro(
            extracted.get("self_introduction")
            or extracted.get("personal_statement")
            or extracted.get("cover_letter")
            or extracted.get("objective")
            or ""
        ),
        family_info=normalize_family(
            extracted.get("family_info")
            or extracted.get("family_background")
            or extracted.get("marital_status")
            or {}
        ),
        overseas_experience=normalize_overseas(
            extracted.get("overseas_experience")
            or extracted.get("international_experience")
            or extracted.get("residence_abroad")
            or []
        ),
        trainings=normalize_trainings(
            extracted.get("trainings")
            or extracted.get("training_courses")
            or extracted.get("training_programs")
            or extracted.get("education_history")
            or []
        ),
        patents=normalize_patents(
            extracted.get("patents_registered")
            or extracted.get("patents_applications")
            or extracted.get("patents")
            or []
        ),
        projects=normalize_projects(extracted.get("projects") or []),
    )


def _create_educations(candidate: Candidate, educations: list[dict]):
    for edu in educations:
        Education.objects.create(
            candidate=candidate,
            institution=_t(edu.get("institution"), 255),
            degree=_t(edu.get("degree"), 100),
            major=_t(edu.get("major"), 255),
            gpa=_t(str(edu.get("gpa") or ""), 100),
            start_year=edu.get("start_year"),
            end_year=edu.get("end_year"),
            is_abroad=edu.get("is_abroad", False),
        )


def _create_careers(candidate: Candidate, careers: list[dict]):
    for career in careers:
        Career.objects.create(
            candidate=candidate,
            company=_t(career.get("company"), 255),
            company_en=_t(career.get("company_en"), 255),
            position=_t(career.get("position"), 255),
            department=_t(career.get("department"), 255),
            start_date=_t(career.get("start_date"), 255),
            end_date=_t(career.get("end_date"), 255),
            duration_text=_t(career.get("duration_text"), 255),
            end_date_inferred=_t(career.get("end_date_inferred"), 255),
            date_evidence=career.get("date_evidence") or "",
            date_confidence=career.get("date_confidence"),
            is_current=career.get("is_current", False),
            duties=career.get("duties") or "",
            inferred_capabilities=career.get("inferred_capabilities") or "",
            achievements=career.get("achievements") or "",
            reason_left=_t(career.get("reason_left"), 500),
            salary=career.get("salary"),
            order=career.get("order", 0),
        )


def _create_certifications(candidate: Candidate, certifications: list[dict]):
    for cert in certifications:
        Certification.objects.create(
            candidate=candidate,
            name=_t(cert.get("name"), 255),
            issuer=_t(cert.get("issuer"), 255),
            acquired_date=_t(cert.get("acquired_date"), 255),
        )


def _create_language_skills(candidate: Candidate, language_skills: list[dict]):
    for lang in language_skills:
        LanguageSkill.objects.create(
            candidate=candidate,
            language=_t(lang.get("language"), 100),
            test_name=_t(lang.get("test_name"), 100),
            score=_t(lang.get("score"), 255),
            level=_t(lang.get("level"), 255),
        )
