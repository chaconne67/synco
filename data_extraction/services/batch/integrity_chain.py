from __future__ import annotations

import json
from pathlib import Path

from django.db import transaction

from candidates.models import Category, Resume
from data_extraction.models import GeminiBatchItem, GeminiBatchJob
from data_extraction.services.batch.artifacts import request_file_path
from data_extraction.services.batch.integrity_request_builder import (
    build_step2_career_request_line,
    build_step2_education_request_line,
)
from data_extraction.services.batch.request_builder import extract_text_response
from data_extraction.services.extraction.integrity import (
    _carry_forward_career_fields,
    _carry_forward_education_fields,
    _is_current_end_date_flag,
    _normalize_company,
    check_campus_match,
    check_career_education_overlap,
    check_education_gaps,
    check_period_overlaps,
    normalize_skills,
)
from data_extraction.services.extraction.sanitizers import parse_llm_json
from data_extraction.services.filters import apply_regex_field_filters
from data_extraction.services.pipeline import (
    _build_integrity_diagnosis,
    apply_cross_version_comparison,
)
from data_extraction.services.save import save_pipeline_result
from data_extraction.services.validation import compute_field_confidences


def prepare_next_integrity_job(parent_job: GeminiBatchJob) -> GeminiBatchJob | None:
    stage = _job_stage(parent_job)
    if stage == "step1":
        return _prepare_step2_job(parent_job)
    if stage == "step2":
        _finalize_step2_job(parent_job)
        return None
    raise RuntimeError(f"Unsupported integrity batch stage: {stage or '(missing)'}")


def ingest_integrity_job_results(job: GeminiBatchJob, *, workers: int = 1) -> dict:
    stage = _job_stage(job)
    if stage not in {"step1", "step2"}:
        raise RuntimeError(f"Unsupported integrity batch stage: {stage or '(missing)'}")

    result_path = Path(job.result_file_path)
    if not result_path.exists():
        raise RuntimeError(f"Result file not found: {result_path}")

    items_by_key = {item.request_key: item for item in job.items.all()}
    processed = 0
    ingested = 0
    failed = 0

    with result_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            processed += 1
            parsed = json.loads(line)
            item = items_by_key.get(parsed.get("key"))
            if not item:
                failed += 1
                continue
            if _ingest_integrity_item(item, parsed, stage=stage):
                ingested += 1
            else:
                failed += 1

    job.successful_requests = ingested
    job.failed_requests = failed
    job.status = GeminiBatchJob.Status.INGESTED
    job.save(
        update_fields=[
            "successful_requests",
            "failed_requests",
            "status",
            "updated_at",
        ]
    )
    return {"processed": processed, "ingested": ingested, "failed": failed}


def _prepare_step2_job(parent_job: GeminiBatchJob) -> GeminiBatchJob | None:
    parent_items = parent_job.items.filter(status=GeminiBatchItem.Status.SUCCEEDED)
    if not parent_items.exists():
        return None

    child = GeminiBatchJob.objects.create(
        display_name=f"{parent_job.display_name}-step2",
        parent_folder_id=parent_job.parent_folder_id,
        category_filter=parent_job.category_filter,
        model_name=parent_job.model_name,
        metadata={
            "pipeline": "integrity",
            "stage": "step2",
            "parent_job_id": str(parent_job.id),
        },
    )
    request_path = request_file_path(str(child.id))
    total = 0

    with request_path.open("w", encoding="utf-8") as handle:
        for parent_item in parent_items:
            raw_data = (parent_item.metadata or {}).get("step1_raw_data") or {}
            tasks = [
                (
                    "career",
                    raw_data.get("careers", []),
                    build_step2_career_request_line,
                ),
                (
                    "education",
                    raw_data.get("educations", []),
                    build_step2_education_request_line,
                ),
            ]
            for task, entries, builder in tasks:
                request_key = f"{parent_item.drive_file_id}:{task}"
                handle.write(builder(request_key=request_key, **{f"{task}s": entries}))
                handle.write("\n")
                GeminiBatchItem.objects.create(
                    job=child,
                    request_key=request_key,
                    drive_file_id=parent_item.drive_file_id,
                    file_name=parent_item.file_name,
                    category_name=parent_item.category_name,
                    status=GeminiBatchItem.Status.PREPARED,
                    raw_text_path=parent_item.raw_text_path,
                    primary_file=parent_item.primary_file,
                    other_files=parent_item.other_files,
                    filename_meta=parent_item.filename_meta,
                    metadata={
                        "pipeline": "integrity",
                        "stage": "step2",
                        "task": task,
                        "parent_job_id": str(parent_job.id),
                        "parent_item_id": str(parent_item.id),
                    },
                )
                total += 1

    child.status = GeminiBatchJob.Status.PREPARED
    child.request_file_path = str(request_path)
    child.total_requests = total
    child.save(
        update_fields=[
            "status",
            "request_file_path",
            "total_requests",
            "updated_at",
        ]
    )
    return child


def _finalize_step2_job(job: GeminiBatchJob) -> dict:
    parent_job_id = (job.metadata or {}).get("parent_job_id")
    if not parent_job_id:
        raise RuntimeError("Step 2 job has no parent_job_id")

    parent_items = {
        item.drive_file_id: item
        for item in GeminiBatchItem.objects.filter(job_id=parent_job_id)
    }
    step2_items: dict[str, dict[str, GeminiBatchItem]] = {}
    for item in job.items.filter(status=GeminiBatchItem.Status.SUCCEEDED):
        task = (item.metadata or {}).get("task")
        step2_items.setdefault(item.drive_file_id, {})[task] = item

    saved = 0
    failed = 0
    for drive_file_id, task_items in step2_items.items():
        parent_item = parent_items.get(drive_file_id)
        career_item = task_items.get("career")
        edu_item = task_items.get("education")
        if not parent_item or not career_item or not edu_item:
            failed += 1
            continue
        try:
            _save_integrity_item(parent_item, career_item, edu_item)
            saved += 1
        except Exception as exc:
            failed += 1
            parent_item.status = GeminiBatchItem.Status.FAILED
            parent_item.error_message = f"Integrity finalize failed: {exc}"
            parent_item.save(update_fields=["status", "error_message", "updated_at"])

    job.metadata = {
        **(job.metadata or {}),
        "finalized": True,
        "finalized_saved": saved,
        "finalized_failed": failed,
    }
    job.save(update_fields=["metadata", "updated_at"])
    return {"saved": saved, "failed": failed}


def _ingest_integrity_item(
    item: GeminiBatchItem,
    parsed: dict,
    *,
    stage: str,
) -> bool:
    item.response_json = parsed
    if parsed.get("error"):
        item.status = GeminiBatchItem.Status.FAILED
        item.error_message = json.dumps(parsed["error"], ensure_ascii=False)
        item.save(update_fields=["response_json", "status", "error_message", "updated_at"])
        return False

    response_text = extract_text_response(parsed)
    extracted = parse_llm_json(response_text) if response_text else None
    if not extracted:
        item.status = GeminiBatchItem.Status.FAILED
        item.error_message = "Failed to parse JSON batch output"
        item.save(update_fields=["response_json", "status", "error_message", "updated_at"])
        return False

    metadata = dict(item.metadata or {})
    if stage == "step1":
        metadata["step1_raw_data"] = extracted
    else:
        metadata["step2_result"] = extracted
    item.metadata = metadata
    item.status = GeminiBatchItem.Status.SUCCEEDED
    item.error_message = ""
    item.response_json = {
        **(item.response_json or {}),
        "parsed_extracted": extracted,
    }
    item.save(
        update_fields=[
            "response_json",
            "metadata",
            "status",
            "error_message",
            "updated_at",
        ]
    )
    return True


def _save_integrity_item(
    parent_item: GeminiBatchItem,
    career_item: GeminiBatchItem,
    edu_item: GeminiBatchItem,
) -> None:
    raw_data = (parent_item.metadata or {}).get("step1_raw_data") or {}
    career_result = (career_item.metadata or {}).get("step2_result") or {}
    edu_result = (edu_item.metadata or {}).get("step2_result") or {}

    normalized_careers = career_result.get("careers", []) or []
    if not normalized_careers and career_result.get("career"):
        normalized_careers = [career_result["career"]]
    normalized_educations = edu_result.get("educations", []) or []

    careers_raw = raw_data.get("careers", []) or []
    educations_raw = raw_data.get("educations", []) or []
    _carry_forward_career_fields(normalized_careers, careers_raw)
    _carry_forward_education_fields(normalized_educations, educations_raw)

    normalized_careers.sort(key=lambda c: c.get("start_date") or "", reverse=True)
    for idx, career in enumerate(normalized_careers):
        career["order"] = idx

    all_flags = [
        *(career_result.get("flags", []) or []),
        *(edu_result.get("flags", []) or []),
    ]
    autocorrected_companies = set()
    for career in normalized_careers:
        if career.get("end_date") and career.get("is_current"):
            career["is_current"] = False
            autocorrected_companies.add(_normalize_company(career.get("company", "")))
    if autocorrected_companies:
        all_flags = [
            flag
            for flag in all_flags
            if not _is_current_end_date_flag(flag, autocorrected_companies)
        ]

    skills = normalize_skills(raw_data)
    all_flags.extend(check_period_overlaps(normalized_careers))
    all_flags.extend(check_career_education_overlap(normalized_careers, normalized_educations))
    all_flags.extend(check_education_gaps(normalized_educations))
    all_flags.extend(check_campus_match(normalized_educations))

    extracted = apply_regex_field_filters(
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
            "pipeline_meta": {
                "step1_items": len(careers_raw) + len(educations_raw),
                "retries": 0,
                "step1_careers_raw": careers_raw,
                "step1_educations_raw": educations_raw,
                "batch_step1_item_id": str(parent_item.id),
                "batch_step2_career_item_id": str(career_item.id),
                "batch_step2_education_item_id": str(edu_item.id),
            },
        }
    )
    field_scores, _category_scores = compute_field_confidences(extracted, {})
    extracted["field_confidences"] = field_scores

    pipeline_result = {
        "extracted": extracted,
        "diagnosis": _build_integrity_diagnosis(all_flags, field_scores),
        "attempts": 1,
        "retry_action": (
            "human_review"
            if any(flag.get("severity") == "RED" for flag in all_flags)
            else "none"
        ),
        "raw_text_used": Path(parent_item.raw_text_path).read_text(encoding="utf-8"),
        "integrity_flags": all_flags,
    }
    from candidates.services.candidate_identity import (
        build_candidate_comparison_context,
    )

    comparison_context = build_candidate_comparison_context(extracted)
    if comparison_context and comparison_context.previous_data:
        pipeline_result = apply_cross_version_comparison(
            pipeline_result,
            comparison_context.previous_data,
        )

    category, _ = Category.objects.get_or_create(
        name=parent_item.category_name,
        defaults={"name_ko": ""},
    )
    referenced_ids = {
        file_info["file_id"]
        for file_info in [parent_item.primary_file, *(parent_item.other_files or [])]
        if file_info.get("file_id")
    }
    existing_ids = set(
        Resume.objects.filter(drive_file_id__in=referenced_ids).values_list(
            "drive_file_id",
            flat=True,
        )
    )
    with transaction.atomic():
        candidate = save_pipeline_result(
            pipeline_result=pipeline_result,
            raw_text=pipeline_result["raw_text_used"],
            category=category,
            primary_file=parent_item.primary_file,
            other_files=parent_item.other_files or [],
            existing_ids=existing_ids,
            comparison_context=comparison_context,
            filename_meta=parent_item.filename_meta,
        )
        parent_item.status = GeminiBatchItem.Status.INGESTED
        parent_item.candidate = candidate
        parent_item.save(update_fields=["status", "candidate", "updated_at"])


def _job_stage(job: GeminiBatchJob) -> str:
    return (job.metadata or {}).get("stage", "")
