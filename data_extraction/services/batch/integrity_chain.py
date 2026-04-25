from __future__ import annotations

import json
from pathlib import Path

from django.db import transaction

from candidates.models import Category, Resume
from data_extraction.models import GeminiBatchItem, GeminiBatchJob
from data_extraction.services.batch.artifacts import request_file_path
from data_extraction.services.batch.integrity_request_builder import (
    build_step1_request_line,
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
from data_extraction.services.extraction.validators import (
    validate_step1,
    validate_step2,
    validation_issues_to_flags,
)
from data_extraction.services.extraction.routing import (
    route_error,
    route_step1_validation,
    route_step2_validation,
)


def prepare_next_integrity_job(parent_job: GeminiBatchJob) -> GeminiBatchJob | None:
    stage = _job_stage(parent_job)
    if stage == "step1":
        retry_job = _prepare_step1_retry_job(parent_job)
        if retry_job is not None:
            return retry_job
        return _prepare_step2_job(parent_job)
    if stage == "step1_retry":
        return _prepare_step2_job(parent_job)
    if stage == "step2":
        retry_job = _prepare_step2_retry_job(parent_job)
        if retry_job is not None:
            return retry_job
        _finalize_step2_job(parent_job)
        return None
    if stage == "step2_retry":
        # Finalize the parent step2 job after merging retry results.
        parent_job_id = (parent_job.metadata or {}).get("parent_job_id")
        parent_step2_job = (
            GeminiBatchJob.objects.filter(id=parent_job_id).first()
            if parent_job_id
            else None
        )
        if parent_step2_job is None:
            raise RuntimeError("Step 2 retry job has no parent step2 job")
        _finalize_step2_job(parent_step2_job)
        return None
    raise RuntimeError(f"Unsupported integrity batch stage: {stage or '(missing)'}")


def ingest_integrity_job_results(job: GeminiBatchJob, *, workers: int = 1) -> dict:
    stage = _job_stage(job)
    if stage not in {"step1", "step1_retry", "step2", "step2_retry"}:
        raise RuntimeError(f"Unsupported integrity batch stage: {stage or '(missing)'}")

    result_path = Path(job.result_file_path)
    if not result_path.exists():
        raise RuntimeError(f"Result file not found: {result_path}")

    items_by_key = {item.request_key: item for item in job.items.all()}
    processed = 0
    ingested = 0
    failed = 0

    from data_extraction.services.extraction import telemetry

    with result_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            processed += 1
            parsed = json.loads(line)
            telemetry.add_from_batch_result_line(parsed)
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


def _prepare_step1_retry_job(parent_job: GeminiBatchJob) -> GeminiBatchJob | None:
    retry_candidates = []
    for item in parent_job.items.filter(status=GeminiBatchItem.Status.SUCCEEDED):
        metadata = item.metadata or {}
        routing = metadata.get("quality_routing") or route_step1_validation(
            metadata.get("step1_validation_issues", []),
            retry_count=0,
        )
        if routing.get("next_action") == "retry_batch":
            retry_candidates.append(item)
    if not retry_candidates:
        return None

    child = GeminiBatchJob.objects.create(
        display_name=f"{parent_job.display_name}-step1-retry",
        parent_folder_id=parent_job.parent_folder_id,
        category_filter=parent_job.category_filter,
        model_name=parent_job.model_name,
        metadata={
            "pipeline": "integrity",
            "stage": "step1_retry",
            "parent_job_id": str(parent_job.id),
        },
    )
    request_path = request_file_path(str(child.id))

    with request_path.open("w", encoding="utf-8") as handle:
        for parent_item in retry_candidates:
            issues = (parent_item.metadata or {}).get("step1_validation_issues", [])
            feedback = ". ".join(
                issue.get("message", "")
                for issue in issues
                if issue.get("severity") == "warning"
            )
            raw_text = Path(parent_item.raw_text_path).read_text(encoding="utf-8")
            handle.write(
                build_step1_request_line(
                    request_key=parent_item.drive_file_id,
                    resume_text=raw_text,
                    file_name=parent_item.file_name,
                    feedback=feedback,
                )
            )
            handle.write("\n")
            GeminiBatchItem.objects.create(
                job=child,
                request_key=parent_item.drive_file_id,
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
                    "stage": "step1_retry",
                    "parent_job_id": str(parent_job.id),
                    "parent_item_id": str(parent_item.id),
                    "step1_retry_feedback": feedback,
                },
            )

    child.status = GeminiBatchJob.Status.PREPARED
    child.request_file_path = str(request_path)
    child.total_requests = len(retry_candidates)
    child.save(
        update_fields=[
            "status",
            "request_file_path",
            "total_requests",
            "updated_at",
        ]
    )
    return child


def _collect_step1_items(job: GeminiBatchJob) -> list[GeminiBatchItem]:
    if _job_stage(job) != "step1_retry":
        return list(job.items.filter(status=GeminiBatchItem.Status.SUCCEEDED))

    parent_job_id = (job.metadata or {}).get("parent_job_id")
    if not parent_job_id:
        return list(job.items.filter(status=GeminiBatchItem.Status.SUCCEEDED))

    selected = {
        item.drive_file_id: item
        for item in GeminiBatchItem.objects.filter(
            job_id=parent_job_id,
            status=GeminiBatchItem.Status.SUCCEEDED,
        )
    }
    for retry_item in job.items.filter(status=GeminiBatchItem.Status.SUCCEEDED):
        selected[retry_item.drive_file_id] = retry_item
    return list(selected.values())


def _prepare_step2_job(parent_job: GeminiBatchJob) -> GeminiBatchJob | None:
    parent_items = _collect_step1_items(parent_job)
    if not parent_items:
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


def _prepare_step2_retry_job(parent_job: GeminiBatchJob) -> GeminiBatchJob | None:
    """Build a step2_retry job for career task items whose validate_step2 found errors.

    Education tasks are not retried — validate_step2 only checks careers, and
    education normalization rarely produces machine-checkable errors that
    feedback could fix. Career retries carry the failed items only; clean
    careers and the original education task results are reused at finalize.
    """
    retry_candidates = []
    for item in parent_job.items.filter(status=GeminiBatchItem.Status.SUCCEEDED):
        metadata = item.metadata or {}
        if metadata.get("task") != "career":
            continue
        routing = metadata.get("quality_routing")
        if not routing:
            issues = metadata.get("step2_validation_issues", [])
            routing = route_step2_validation(issues, retry_count=0)
        if routing.get("next_action") == "retry_batch":
            retry_candidates.append(item)
    if not retry_candidates:
        return None

    child = GeminiBatchJob.objects.create(
        display_name=f"{parent_job.display_name}-step2-retry",
        parent_folder_id=parent_job.parent_folder_id,
        category_filter=parent_job.category_filter,
        model_name=parent_job.model_name,
        metadata={
            "pipeline": "integrity",
            "stage": "step2_retry",
            "parent_job_id": str(parent_job.id),
        },
    )
    request_path = request_file_path(str(child.id))

    with request_path.open("w", encoding="utf-8") as handle:
        for parent_item in retry_candidates:
            issues = (parent_item.metadata or {}).get("step2_validation_issues", [])
            feedback = ". ".join(
                issue.get("message", "")
                for issue in issues
                if issue.get("severity") == "error"
            )
            grandparent_item_id = (parent_item.metadata or {}).get("parent_item_id")
            grandparent_item = (
                GeminiBatchItem.objects.filter(id=grandparent_item_id).first()
                if grandparent_item_id
                else None
            )
            careers_raw = (
                ((grandparent_item.metadata or {}).get("step1_raw_data") or {}).get(
                    "careers", []
                )
                if grandparent_item
                else []
            )
            handle.write(
                build_step2_career_request_line(
                    request_key=parent_item.request_key,
                    careers=careers_raw,
                    feedback=feedback,
                )
            )
            handle.write("\n")
            GeminiBatchItem.objects.create(
                job=child,
                request_key=parent_item.request_key,
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
                    "stage": "step2_retry",
                    "task": "career",
                    "parent_job_id": str(parent_job.id),
                    "parent_item_id": grandparent_item_id,
                    "step2_retry_parent_item_id": str(parent_item.id),
                    "step2_retry_feedback": feedback,
                },
            )

    child.status = GeminiBatchJob.Status.PREPARED
    child.request_file_path = str(request_path)
    child.total_requests = len(retry_candidates)
    child.save(
        update_fields=[
            "status",
            "request_file_path",
            "total_requests",
            "updated_at",
        ]
    )
    return child


def _collect_step2_items(job: GeminiBatchJob) -> list[GeminiBatchItem]:
    """Return the effective step2 items for finalize, merging step2_retry results.

    Key is (drive_file_id, task). step2_retry SUCCEEDED items override the
    parent step2 entry for the same key; non-retried tasks (e.g., education)
    pass through from the parent step2 job.
    """
    items_by_key: dict[tuple[str, str], GeminiBatchItem] = {}
    for item in job.items.all():
        task = (item.metadata or {}).get("task") or ""
        items_by_key[(item.drive_file_id, task)] = item

    retry_jobs = GeminiBatchJob.objects.filter(
        metadata__stage="step2_retry",
        metadata__parent_job_id=str(job.id),
    )
    for retry_job in retry_jobs:
        for retry_item in retry_job.items.filter(
            status=GeminiBatchItem.Status.SUCCEEDED
        ):
            task = (retry_item.metadata or {}).get("task") or ""
            items_by_key[(retry_item.drive_file_id, task)] = retry_item

    return list(items_by_key.values())


def _finalize_step2_job(job: GeminiBatchJob) -> dict:
    parent_job_id = (job.metadata or {}).get("parent_job_id")
    if not parent_job_id:
        raise RuntimeError("Step 2 job has no parent_job_id")

    # Group step2 items (parent + retry override) by drive_file_id so we can
    # emit placeholder records when career/education tasks are missing.
    step2_items: dict[str, dict[str, GeminiBatchItem]] = {}
    for item in _collect_step2_items(job):
        task = (item.metadata or {}).get("task")
        step2_items.setdefault(item.drive_file_id, {})[task] = item

    saved = 0
    failed = 0
    for drive_file_id, task_items in step2_items.items():
        career_item = task_items.get("career")
        edu_item = task_items.get("education")
        # parent_item_id can be recovered from any sibling task, not only career.
        any_item = career_item or edu_item
        parent_item_id = (any_item.metadata or {}).get("parent_item_id") if any_item else None
        parent_item = (
            GeminiBatchItem.objects.filter(id=parent_item_id).first()
            if parent_item_id
            else None
        )
        career_ok = (
            career_item is not None
            and career_item.status == GeminiBatchItem.Status.SUCCEEDED
        )
        edu_ok = (
            edu_item is not None
            and edu_item.status == GeminiBatchItem.Status.SUCCEEDED
        )
        if not parent_item or not career_ok or not edu_ok:
            failed += 1
            if parent_item is not None:
                _mark_integrity_item_failed(
                    parent_item,
                    error="Step2 inputs incomplete (career or education missing)",
                )
            continue
        try:
            _save_integrity_item(parent_item, career_item, edu_item)
            saved += 1
        except Exception as exc:
            failed += 1
            _mark_integrity_item_failed(
                parent_item,
                error=f"Integrity finalize failed: {exc}",
            )

    job.metadata = {
        **(job.metadata or {}),
        "finalized": True,
        "finalized_saved": saved,
        "finalized_failed": failed,
    }
    job.save(update_fields=["metadata", "updated_at"])
    return {"saved": saved, "failed": failed}


def _mark_integrity_item_failed(parent_item: GeminiBatchItem, *, error: str) -> None:
    """Persist a failed integrity batch item and its placeholder Resume record.

    Without this, a Step 2 finalize failure would leave the GeminiBatchItem
    in an ambiguous state and the per-resume ResumeExtractionState stuck in
    EXTRACTING. We surface the failure as either a text_only review record
    (when raw text is available) or a failed Resume (no extraction artifact).
    """
    from data_extraction.services.save import save_failed_resume, save_text_only_resume

    parent_item.status = GeminiBatchItem.Status.FAILED
    parent_item.error_message = error
    parent_item.metadata = {
        **(parent_item.metadata or {}),
        "quality_routing": route_error(error, has_raw_text=bool(parent_item.raw_text_path)),
    }
    parent_item.save(
        update_fields=["status", "error_message", "metadata", "updated_at"]
    )

    raw_text = ""
    if parent_item.raw_text_path:
        try:
            raw_text = Path(parent_item.raw_text_path).read_text(encoding="utf-8")
        except Exception:
            raw_text = ""

    try:
        if raw_text.strip():
            save_text_only_resume(
                parent_item.primary_file,
                parent_item.category_name,
                raw_text=raw_text,
                error_msg=error,
                filename_meta=parent_item.filename_meta,
            )
        else:
            save_failed_resume(
                parent_item.primary_file,
                parent_item.category_name,
                error,
                filename_meta=parent_item.filename_meta,
            )
    except Exception:
        pass


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
        item.metadata = {
            **(item.metadata or {}),
            "quality_routing": route_error(item.error_message, has_raw_text=False),
        }
        item.save(
            update_fields=[
                "response_json",
                "status",
                "error_message",
                "metadata",
                "updated_at",
            ]
        )
        return False

    response_text = extract_text_response(parsed)
    extracted = parse_llm_json(response_text) if response_text else None
    if not extracted:
        item.status = GeminiBatchItem.Status.FAILED
        item.error_message = "Failed to parse JSON batch output"
        item.metadata = {
            **(item.metadata or {}),
            "quality_routing": route_error(item.error_message, has_raw_text=True),
        }
        item.save(
            update_fields=[
                "response_json",
                "status",
                "error_message",
                "metadata",
                "updated_at",
            ]
        )
        return False

    metadata = dict(item.metadata or {})
    if stage in {"step1", "step1_retry"}:
        metadata["step1_raw_data"] = extracted
        raw_text = Path(item.raw_text_path).read_text(encoding="utf-8")
        issues = validate_step1(extracted, raw_text)
        metadata["step1_validation_issues"] = issues
        metadata["quality_routing"] = route_step1_validation(
            issues,
            retry_count=1 if stage == "step1_retry" else 0,
        )
    else:
        # stage in {"step2", "step2_retry"}
        metadata["step2_result"] = extracted
        # Career task에 한해 ingest 시점 검증으로 retry 가치 판정.
        # carry_forward 후 finalize 시점에 다시 검증해 최종 RED 플래그를 만듦.
        task = metadata.get("task")
        if task == "career":
            careers_normalized = extracted.get("careers", []) or []
            if not careers_normalized and extracted.get("career"):
                careers_normalized = [extracted["career"]]
            issues = validate_step2(
                {
                    "careers": careers_normalized,
                    "flags": extracted.get("flags", []) or [],
                }
            )
            metadata["step2_validation_issues"] = issues
            metadata["quality_routing"] = route_step2_validation(
                issues,
                retry_count=1 if stage == "step2_retry" else 0,
            )
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
    career_validation_issues = validate_step2(
        {"careers": normalized_careers, "flags": career_result.get("flags", []) or []},
        raw_careers=careers_raw,
    )
    _carry_forward_career_fields(normalized_careers, careers_raw)
    _carry_forward_education_fields(normalized_educations, educations_raw)

    normalized_careers.sort(key=lambda c: c.get("start_date") or "", reverse=True)
    for idx, career in enumerate(normalized_careers):
        career["order"] = idx

    all_flags = [
        *(career_result.get("flags", []) or []),
        *(edu_result.get("flags", []) or []),
        *validation_issues_to_flags(
            (parent_item.metadata or {}).get("step1_validation_issues", []),
            stage="step1",
            default_severity="YELLOW",
        ),
        *validation_issues_to_flags(
            career_validation_issues,
            stage="step2",
            default_severity="RED",
        ),
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
    all_flags.extend(
        check_career_education_overlap(normalized_careers, normalized_educations)
    )
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
                "retries": 1
                if (parent_item.metadata or {}).get("stage") == "step1_retry"
                else 0,
                # Shared shape with integrity realtime so review tooling can
                # consume both modes uniformly.
                "step1_validation_issues": (
                    (parent_item.metadata or {}).get("step1_validation_issues", [])
                ),
                "step2_career_validation_issues": career_validation_issues,
                "step1_careers_raw": careers_raw,
                "step1_educations_raw": educations_raw,
                # Batch-only audit fields (no realtime equivalent).
                "batch_step1_retried": (
                    (parent_item.metadata or {}).get("stage") == "step1_retry"
                ),
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
    from data_extraction.services.pipeline import attach_quality_routing

    pipeline_result = attach_quality_routing(pipeline_result)
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
        parent_item.metadata = {
            **(parent_item.metadata or {}),
            "quality_routing": pipeline_result.get("quality_routing", {}),
        }
        parent_item.save(
            update_fields=["status", "candidate", "metadata", "updated_at"]
        )


def _job_stage(job: GeminiBatchJob) -> str:
    return (job.metadata or {}).get("stage", "")
