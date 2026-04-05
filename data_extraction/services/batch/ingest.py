from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from django.db import close_old_connections
from django.db import transaction

from data_extraction.models import GeminiBatchItem, GeminiBatchJob
from data_extraction.services.batch.request_builder import extract_text_response
from candidates.models import Category, Resume
from data_extraction.services.filters import apply_regex_field_filters
from data_extraction.services.save import save_pipeline_result
from data_extraction.services.validation import validate_extraction


def ingest_job_results(job: GeminiBatchJob, *, workers: int = 1) -> dict:
    result_path = Path(job.result_file_path)
    if not result_path.exists():
        raise RuntimeError(f"Result file not found: {result_path}")

    entries = []
    items_by_key = {
        item.request_key: item
        for item in job.items.all()
    }

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


def _handle_result_payload(*, key_to_item: dict[str, GeminiBatchItem], parsed: dict) -> str:
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
            item.save(
                update_fields=["response_json", "status", "error_message", "updated_at"]
            )
            return "failed"

        response_text = extract_text_response(parsed)
        if not response_text:
            item.status = GeminiBatchItem.Status.FAILED
            item.error_message = "Missing text response in batch output"
            item.save(
                update_fields=["response_json", "status", "error_message", "updated_at"]
            )
            return "failed"

        candidate = _ingest_item_response(item, response_text)
        if candidate is None:
            return "failed"
        return "ingested"
    finally:
        close_old_connections()


def _ingest_item_response(item: GeminiBatchItem, response_text: str):
    extracted = _load_extracted_json(response_text)
    if not extracted:
        item.status = GeminiBatchItem.Status.FAILED
        item.error_message = "Failed to parse JSON extraction output"
        item.save(update_fields=["status", "error_message", "updated_at"])
        return None
    extracted = apply_regex_field_filters(extracted)

    rule_result = validate_extraction(extracted, item.filename_meta or {})
    diagnosis = {
        "verdict": "pass" if rule_result["validation_status"] == "auto_confirmed" else "fail",
        "issues": rule_result["issues"],
        "field_scores": rule_result["field_confidences"],
        "overall_score": rule_result["confidence_score"],
    }
    retry_action = "none" if diagnosis["verdict"] == "pass" else "human_review"
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

    pipeline_result = {
        "extracted": extracted,
        "diagnosis": diagnosis,
        "attempts": 1,
        "retry_action": retry_action,
        "raw_text_used": raw_text,
        "integrity_flags": [],
    }

    with transaction.atomic():
        candidate = save_pipeline_result(
            pipeline_result=pipeline_result,
            raw_text=raw_text,
            category=category,
            primary_file=item.primary_file,
            other_files=item.other_files or [],
            existing_ids=existing_ids,
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
        item.error_message = ""
        item.save(
            update_fields=[
                "status",
                "candidate",
                "response_json",
                "error_message",
                "updated_at",
            ]
        )
        return candidate


def _load_extracted_json(response_text: str) -> dict | None:
    raw = response_text.strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try parsing first JSON object (Gemini sometimes appends extra data)
        try:
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(raw)
        except (json.JSONDecodeError, ValueError):
            # Fallback for pre-structured-output fenced code block results
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                try:
                    data = json.loads(raw.strip())
                except json.JSONDecodeError:
                    return None
            else:
                return None
    # Gemini sometimes wraps response in a list: [{...}]
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        data = data[0]
    return data if isinstance(data, dict) else None
