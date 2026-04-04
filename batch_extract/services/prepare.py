from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from batch_extract.models import GeminiBatchItem, GeminiBatchJob
from batch_extract.services.artifacts import raw_text_path, request_file_path
from batch_extract.services.request_builder import build_request_line
from candidates.models import Resume
from candidates.services.drive_sync import (
    CATEGORY_FOLDERS,
    download_file,
    find_category_folder,
    get_drive_service,
    list_files_in_folder,
)
from candidates.services.filename_parser import group_by_person
from candidates.services.text_extraction import extract_text, preprocess_resume_text


def prepare_drive_job(
    *,
    job: GeminiBatchJob,
    folder_name: str | None = None,
    limit: int = 0,
    parent_folder_id: str = "root",
    workers: int = 4,
) -> GeminiBatchJob:
    service = get_drive_service()
    folders = [folder_name] if folder_name else list(CATEGORY_FOLDERS)
    collected = []
    prepare_failures = []

    for current_folder in folders:
        folder_id = find_category_folder(service, parent_folder_id, current_folder)
        if not folder_id:
            prepare_failures.append(
                {"category": current_folder, "error": "Folder not found on Drive"}
            )
            continue

        normalized_files = _list_normalized_files(service, folder_id, limit=limit)
        groups = group_by_person(normalized_files)
        all_ids = {
            file_info["file_id"]
            for group in groups
            for file_info in [group["primary"], *group["others"]]
        }
        existing_ids = set(
            Resume.objects.filter(drive_file_id__in=all_ids).values_list(
                "drive_file_id",
                flat=True,
            )
        )
        pending_groups = [
            group for group in groups if group["primary"]["file_id"] not in existing_ids
        ]

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _prepare_group_payload,
                    job.id,
                    current_folder,
                    group,
                ): group
                for group in pending_groups
            }
            for future in as_completed(futures):
                group = futures[future]
                try:
                    payload = future.result()
                    collected.append(payload)
                except Exception as exc:
                    primary = group["primary"]
                    prepare_failures.append(
                        {
                            "category": current_folder,
                            "file_id": primary["file_id"],
                            "file_name": primary["file_name"],
                            "error": str(exc),
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
                    )

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
        "folders": folders,
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


def _list_normalized_files(service, folder_id: str, *, limit: int) -> list[dict]:
    files = list_files_in_folder(service, folder_id)
    normalized = [
        {
            "file_name": file_info["name"],
            "file_id": file_info["id"],
            "mime_type": file_info.get("mimeType", ""),
            "file_size": int(file_info.get("size", 0)) if file_info.get("size") else 0,
            "modified_time": file_info.get("modifiedTime", ""),
        }
        for file_info in files
    ]
    if limit:
        return normalized[:limit]
    return normalized


def _prepare_group_payload(job_id, category_name: str, group: dict) -> dict:
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
        if not raw_text.strip():
            raise RuntimeError("Empty text extraction")

    text_path = raw_text_path(str(job_id), primary["file_id"])
    text_path.write_text(raw_text, encoding="utf-8")

    return {
        "request_key": primary["file_id"],
        "drive_file_id": primary["file_id"],
        "file_name": primary["file_name"],
        "category_name": category_name,
        "raw_text_path": str(text_path),
        "primary_file": primary,
        "other_files": group["others"],
        "filename_meta": group["parsed"],
        "request_line": build_request_line(
            request_key=primary["file_id"],
            resume_text=raw_text,
            file_reference_date=primary.get("modified_time"),
        ),
    }
