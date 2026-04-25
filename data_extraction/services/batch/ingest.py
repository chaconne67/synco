from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from django.db import close_old_connections
from django.db import transaction

from data_extraction.models import GeminiBatchItem, GeminiBatchJob
from data_extraction.services.batch.request_builder import extract_text_response
from candidates.models import Category, Resume
from data_extraction.services.extraction.routing import route_error
from data_extraction.services.pipeline import build_legacy_pipeline_result
from data_extraction.services.save import save_pipeline_result


def ingest_job_results(job: GeminiBatchJob, *, workers: int = 1) -> dict:
    if (job.metadata or {}).get("pipeline") == "integrity":
        from data_extraction.services.batch.integrity_chain import (
            ingest_integrity_job_results,
        )

        return ingest_integrity_job_results(job, workers=workers)

    result_path = Path(job.result_file_path)
    if not result_path.exists():
        raise RuntimeError(f"Result file not found: {result_path}")

    entries = []
    items_by_key = {item.request_key: item for item in job.items.all()}

    with result_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            entries.append(json.loads(line))

    processed = len(entries)
    ingested = 0
    failed = 0

    if workers <= 1:
        for parsed in entries:
            outcome = _handle_result_payload(
                key_to_item=items_by_key,
                parsed=parsed,
            )
            if outcome == "ingested":
                ingested += 1
            else:
                failed += 1
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    _handle_result_payload,
                    key_to_item=items_by_key,
                    parsed=parsed,
                )
                for parsed in entries
            ]
            for future in as_completed(futures):
                outcome = future.result()
                if outcome == "ingested":
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
    return {
        "processed": processed,
        "ingested": ingested,
        "failed": failed,
    }


def _handle_result_payload(
    *, key_to_item: dict[str, GeminiBatchItem], parsed: dict
) -> str:
    close_old_connections()
    try:
        key = parsed.get("key")
        if not key:
            return "failed"

        base_item = key_to_item.get(key)
        if not base_item:
            return "failed"

        item = GeminiBatchItem.objects.get(pk=base_item.pk)
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
            _save_placeholder_for_item(item, item.error_message)
            return "failed"

        response_text = extract_text_response(parsed)
        if not response_text:
            item.status = GeminiBatchItem.Status.FAILED
            item.error_message = "Missing text response in batch output"
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
            _save_placeholder_for_item(item, item.error_message)
            return "failed"

        candidate = _ingest_item_response(item, response_text)
        if candidate is None:
            return "failed"
        return "ingested"
    finally:
        close_old_connections()


def _ingest_item_response(item: GeminiBatchItem, response_text: str):
    extracted = _load_extracted_json(response_text)
    if not isinstance(extracted, dict) or "name" not in extracted:
        item.status = GeminiBatchItem.Status.FAILED
        item.error_message = "Failed to parse JSON extraction output"
        item.metadata = {
            **(item.metadata or {}),
            "quality_routing": route_error(item.error_message, has_raw_text=True),
        }
        item.save(update_fields=["status", "error_message", "metadata", "updated_at"])
        _save_placeholder_for_item(
            item,
            item.error_message,
            include_raw_text=True,
        )
        return None
    raw_text = Path(item.raw_text_path).read_text(encoding="utf-8")
    category, _ = Category.objects.get_or_create(
        name=item.category_name,
        defaults={"name_ko": ""},
    )
    referenced_ids = {
        file_info["file_id"]
        for file_info in [item.primary_file, *(item.other_files or [])]
        if file_info.get("file_id")
    }
    existing_ids = set(
        Resume.objects.filter(drive_file_id__in=referenced_ids).values_list(
            "drive_file_id",
            flat=True,
        )
    )

    pipeline_result = build_legacy_pipeline_result(
        extracted,
        raw_text=raw_text,
        filename_meta=item.filename_meta,
    )

    with transaction.atomic():
        candidate = save_pipeline_result(
            pipeline_result=pipeline_result,
            raw_text=raw_text,
            category=category,
            primary_file=item.primary_file,
            other_files=item.other_files or [],
            existing_ids=existing_ids,
            filename_meta=item.filename_meta,
        )
        if not candidate:
            item.status = GeminiBatchItem.Status.FAILED
            item.error_message = "save_pipeline_result returned None"
            item.save(update_fields=["status", "error_message", "updated_at"])
            return None

        item.status = GeminiBatchItem.Status.INGESTED
        item.candidate = candidate
        item.response_json = {
            **(item.response_json or {}),
            "parsed_extracted": extracted,
        }
        item.metadata = {
            **(item.metadata or {}),
            "quality_routing": pipeline_result.get("quality_routing", {}),
        }
        item.error_message = ""
        item.save(
            update_fields=[
                "status",
                "candidate",
                "response_json",
                "metadata",
                "error_message",
                "updated_at",
            ]
        )
        return candidate


def _load_extracted_json(response_text: str) -> dict | None:
    from data_extraction.services.extraction.sanitizers import parse_llm_json

    return parse_llm_json(response_text)


def _save_placeholder_for_item(
    item: GeminiBatchItem,
    error_msg: str,
    *,
    include_raw_text: bool = False,
) -> None:
    """Persist failed/text-only batch state according to extraction quality."""
    from data_extraction.services.save import save_failed_resume, save_text_only_resume

    try:
        raw_text = ""
        if include_raw_text and item.raw_text_path:
            try:
                raw_text = Path(item.raw_text_path).read_text(encoding="utf-8")
            except Exception:
                pass

        if raw_text.strip():
            save_text_only_resume(
                item.primary_file,
                item.category_name,
                raw_text=raw_text,
                error_msg=error_msg,
                filename_meta=item.filename_meta,
            )
        else:
            save_failed_resume(
                item.primary_file,
                item.category_name,
                error_msg,
                filename_meta=item.filename_meta,
            )
    except Exception:
        pass
