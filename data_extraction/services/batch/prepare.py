from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from data_extraction.models import GeminiBatchItem, GeminiBatchJob
from data_extraction.services.extraction.routing import route_error
from data_extraction.services.state import mark_completed
from data_extraction.services.batch.integrity_request_builder import (
    build_step1_request_line,
)
from data_extraction.services.batch.artifacts import raw_text_path, request_file_path
from data_extraction.services.batch.request_builder import build_request_line
from candidates.models import Resume
from data_extraction.models import ResumeExtractionState
from data_extraction.services.drive import (
    discover_folders,
    download_file,
    get_drive_service,
    list_files_in_folder,
)
from data_extraction.services.filename import group_by_person
from data_extraction.services.text import (
    classify_text_quality,
    extract_text,
    passes_birth_year_filter,
    preprocess_resume_text,
)


def prepare_drive_job(
    *,
    job: GeminiBatchJob,
    folder_name: str | None = None,
    limit: int = 0,
    parent_folder_id: str = "root",
    workers: int = 4,
    force: bool = False,
    retry_failed: bool = False,
    failed_only: bool = False,
    shuffle: bool = False,
    integrity: bool = False,
    birth_year_filter: bool = False,
    birth_year_value: int | None = None,
) -> GeminiBatchJob:
    service = get_drive_service()
    discovered = discover_folders(service, parent_folder_id)

    if folder_name:
        discovered = [f for f in discovered if f["name"] == folder_name]

    candidates = []
    prepare_failures = []
    skipped_existing = 0
    skipped_active_batch = 0
    total_groups = 0
    total_files = 0
    skipped_birth_year_filter = 0

    for folder_info in discovered:
        current_folder = folder_info["name"]
        folder_id = folder_info["id"]

        normalized_files = _list_normalized_files(service, folder_id)
        if shuffle:
            import random

            random.shuffle(normalized_files)
        total_files += len(normalized_files)
        groups = group_by_person(normalized_files)
        total_groups += len(groups)
        all_ids = {
            file_info["file_id"]
            for group in groups
            for file_info in [group["primary"], *group["others"]]
        }
        resume_statuses = dict(
            Resume.objects.filter(drive_file_id__in=all_ids).values_list(
                "drive_file_id",
                "processing_status",
            )
        )
        retryable_routing_ids = set(
            ResumeExtractionState.objects.filter(resume__drive_file_id__in=all_ids)
            .filter(metadata__quality_routing__next_action="retry_batch")
            .values_list("resume__drive_file_id", flat=True)
        )
        active_batch_ids = set(
            GeminiBatchItem.objects.filter(drive_file_id__in=all_ids)
            .exclude(status=GeminiBatchItem.Status.FAILED)
            .values_list("drive_file_id", flat=True)
        )

        for group in groups:
            primary_id = group["primary"]["file_id"]
            is_existing = primary_id in resume_statuses
            is_retryable_failed = (retry_failed or failed_only) and (
                resume_statuses.get(primary_id) == Resume.ProcessingStatus.FAILED
                or primary_id in retryable_routing_ids
            )
            is_active_batch = primary_id in active_batch_ids

            if failed_only and not is_retryable_failed:
                if is_existing:
                    skipped_existing += 1
                elif is_active_batch:
                    skipped_active_batch += 1
                continue
            if is_active_batch and not force and not is_retryable_failed:
                skipped_active_batch += 1
                continue
            if is_existing and not force and not is_retryable_failed:
                skipped_existing += 1
                continue

            candidates.append((current_folder, group))

    if limit:
        candidates = candidates[:limit]

    collected = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _prepare_group_payload,
                job.id,
                current_folder,
                group,
                integrity,
                birth_year_filter,
                birth_year_value,
            ): (current_folder, group)
            for current_folder, group in candidates
        }
        for future in as_completed(futures):
            current_folder, group = futures[future]
            try:
                payload = future.result()
                if payload.get("skipped"):
                    skipped_birth_year_filter += 1
                    _save_birth_filter_skip(payload)
                    continue
                collected.append(payload)
            except Exception as exc:
                primary = group["primary"]
                routing = route_error(str(exc), has_raw_text=False)
                prepare_failures.append(
                    {
                        "category": current_folder,
                        "file_id": primary["file_id"],
                        "file_name": primary["file_name"],
                        "error": str(exc),
                        "quality_routing": routing,
                    }
                )
                GeminiBatchItem.objects.create(
                    job=job,
                    request_key=primary["file_id"],
                    drive_file_id=primary["file_id"],
                    file_name=primary["file_name"],
                    category_name=current_folder,
                    status=GeminiBatchItem.Status.FAILED,
                    primary_file=primary,
                    other_files=group["others"],
                    filename_meta=group["parsed"],
                    error_message=str(exc),
                    metadata={"quality_routing": routing},
                )
                # Track the failed file without surfacing it as a Candidate.
                from data_extraction.services.save import save_failed_resume

                try:
                    save_failed_resume(
                        primary,
                        current_folder,
                        f"Batch prepare failed: {exc}",
                        filename_meta=group["parsed"],
                    )
                except Exception:
                    pass

    request_path = request_file_path(str(job.id))
    prepared_count = 0
    with request_path.open("w", encoding="utf-8") as handle:
        for payload in collected:
            handle.write(payload["request_line"])
            handle.write("\n")
            GeminiBatchItem.objects.create(
                job=job,
                request_key=payload["request_key"],
                drive_file_id=payload["drive_file_id"],
                file_name=payload["file_name"],
                category_name=payload["category_name"],
                status=GeminiBatchItem.Status.PREPARED,
                raw_text_path=payload["raw_text_path"],
                primary_file=payload["primary_file"],
                other_files=payload["other_files"],
                filename_meta=payload["filename_meta"],
            )
            prepared_count += 1

    job.status = GeminiBatchJob.Status.PREPARED
    job.category_filter = folder_name or ""
    job.parent_folder_id = parent_folder_id
    job.request_file_path = str(request_path)
    job.total_requests = prepared_count
    job.failed_requests = len(prepare_failures)
    job.metadata = {
        **(job.metadata or {}),
        "prepare_failures": prepare_failures,
        "workers": workers,
        "limit": limit,
        "force": force,
        "retry_failed": retry_failed,
        "failed_only": failed_only,
        "shuffle": shuffle,
        "pipeline": "integrity" if integrity else "legacy",
        "stage": "step1" if integrity else "legacy",
        "total_files": total_files,
        "total_groups": total_groups,
        "selected_groups": len(candidates),
        "skipped_existing": skipped_existing,
        "skipped_active_batch": skipped_active_batch,
        "skipped_birth_year_filter": skipped_birth_year_filter,
        "folders": [f["name"] for f in discovered],
    }
    job.save(
        update_fields=[
            "status",
            "category_filter",
            "parent_folder_id",
            "request_file_path",
            "total_requests",
            "failed_requests",
            "metadata",
            "updated_at",
        ]
    )
    return job


def _list_normalized_files(service, folder_id: str) -> list[dict]:
    files = list_files_in_folder(service, folder_id)
    return [
        {
            "file_name": file_info["name"],
            "file_id": file_info["id"],
            "mime_type": file_info.get("mimeType", ""),
            "file_size": int(file_info.get("size", 0)) if file_info.get("size") else 0,
            "modified_time": file_info.get("modifiedTime", ""),
        }
        for file_info in files
    ]


def _prepare_group_payload(
    job_id,
    category_name: str,
    group: dict,
    integrity: bool = False,
    birth_year_filter: bool = False,
    birth_year_value: int | None = None,
) -> dict:
    primary = group["primary"]
    # Drive API client objects are not safe to share across worker threads.
    service = get_drive_service()
    with tempfile.TemporaryDirectory() as tmpdir:
        download_path = tempfile.NamedTemporaryFile(
            dir=tmpdir,
            suffix=primary["file_name"],
            delete=False,
        )
        download_path.close()
        download_file(service, primary["file_id"], download_path.name)
        raw_text = preprocess_resume_text(extract_text(download_path.name))
        quality = classify_text_quality(raw_text)
        if quality != "ok":
            raise RuntimeError(f"Text quality: {quality}")

    if birth_year_filter:
        birth_filter = passes_birth_year_filter(
            raw_text,
            birth_year_value,
            enabled=True,
        )
        if not birth_filter.passed:
            return {
                "skipped": True,
                "skip_type": "birth_year_filter",
                "reason": birth_filter.reason,
                "request_key": primary["file_id"],
                "drive_file_id": primary["file_id"],
                "file_name": primary["file_name"],
                "category_name": category_name,
                "primary_file": primary,
                "filename_meta": group["parsed"],
                "integrity": integrity,
                "birth_year_filter": {
                    "cutoff_year": birth_filter.cutoff_year,
                    "detected_year": birth_filter.detected_year,
                    "source": birth_filter.source,
                    "evidence": birth_filter.evidence,
                    "reason": birth_filter.reason,
                },
            }

    text_path = raw_text_path(str(job_id), primary["file_id"])
    text_path.write_text(raw_text, encoding="utf-8")

    if integrity:
        request_line = build_step1_request_line(
            request_key=primary["file_id"],
            resume_text=raw_text,
            file_name=primary["file_name"],
        )
    else:
        request_line = build_request_line(
            request_key=primary["file_id"],
            resume_text=raw_text,
            file_reference_date=primary.get("modified_time"),
        )

    return {
        "request_key": primary["file_id"],
        "drive_file_id": primary["file_id"],
        "file_name": primary["file_name"],
        "category_name": category_name,
        "raw_text_path": str(text_path),
        "primary_file": primary,
        "other_files": group["others"],
        "filename_meta": group["parsed"],
        "request_line": request_line,
    }


def _save_birth_filter_skip(payload: dict) -> None:
    primary = payload["primary_file"]
    resume, _created = Resume.objects.update_or_create(
        drive_file_id=primary["file_id"],
        defaults={
            "file_name": primary["file_name"],
            "drive_folder": payload["category_name"],
            "mime_type": primary.get("mime_type", ""),
            "file_size": primary.get("file_size"),
            "processing_status": Resume.ProcessingStatus.PENDING,
            "error_message": f"Birth year filter: {payload['reason']}",
        },
    )
    mark_completed(
        resume,
        status=ResumeExtractionState.Status.SKIPPED,
        error=f"Birth year filter: {payload['reason']}",
        pipeline="integrity" if payload.get("integrity") else "legacy",
        metadata={
            "birth_year_filter": payload["birth_year_filter"],
            "quality_routing": {
                "reason_class": "permanent",
                "next_action": "skip",
                "review_priority": 0,
                "reason": "생년 필터 기준 미충족으로 배치 제외",
            },
        },
    )
