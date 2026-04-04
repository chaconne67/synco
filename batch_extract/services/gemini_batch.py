from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from google import genai
from google.genai import types

from batch_extract.models import GeminiBatchJob
from batch_extract.services.artifacts import result_file_path


def get_client() -> genai.Client:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in settings")
    return genai.Client(api_key=api_key)


def upload_request_file(local_path: str | Path, display_name: str):
    client = get_client()
    return client.files.upload(
        file=str(local_path),
        config=types.UploadFileConfig(
            display_name=display_name,
            mime_type="jsonl",
        ),
    )


def create_batch_job(model_name: str, file_name: str, display_name: str):
    client = get_client()
    return client.batches.create(
        model=model_name,
        src=file_name,
        config=types.CreateBatchJobConfig(display_name=display_name),
    )


def get_batch_job(batch_name: str):
    client = get_client()
    return client.batches.get(name=batch_name)


def download_result_file(file_name: str) -> bytes:
    client = get_client()
    return client.files.download(file=file_name)


def download_results_for_job(job: GeminiBatchJob, remote=None) -> str | None:
    remote = remote or get_batch_job(job.gemini_batch_name)
    if not remote.dest or not remote.dest.file_name:
        return None

    output_bytes = download_result_file(remote.dest.file_name)
    local_path = result_file_path(str(job.id))
    Path(local_path).write_bytes(output_bytes)
    job.result_file_path = str(local_path)
    job.metadata = {
        **(job.metadata or {}),
        "result_file_name": remote.dest.file_name,
    }
    job.save(update_fields=["result_file_path", "metadata", "updated_at"])
    return str(local_path)


def sync_job_from_remote(job: GeminiBatchJob):
    remote = get_batch_job(job.gemini_batch_name)
    remote_state = _state_name(remote.state)
    status = _map_remote_state(remote_state)
    completion = remote.completion_stats
    job.status = status
    job.successful_requests = getattr(completion, "successful_count", 0) or 0
    job.failed_requests = getattr(completion, "failed_count", 0) or 0
    job.metadata = {
        **(job.metadata or {}),
        "remote_job": _model_dump(remote),
    }
    if remote_state == "JOB_STATE_FAILED" and remote.error:
        job.error_message = getattr(remote.error, "message", "") or json.dumps(
            _model_dump(remote.error),
            ensure_ascii=False,
        )
    job.save(
        update_fields=[
            "status",
            "successful_requests",
            "failed_requests",
            "metadata",
            "error_message",
            "updated_at",
        ]
    )
    return remote


def _map_remote_state(remote_state: str) -> str:
    if remote_state in {"JOB_STATE_SUCCEEDED"}:
        return GeminiBatchJob.Status.SUCCEEDED
    if remote_state in {"JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}:
        return GeminiBatchJob.Status.FAILED
    if remote_state in {"JOB_STATE_PENDING", "JOB_STATE_QUEUED", "JOB_STATE_RUNNING"}:
        return GeminiBatchJob.Status.RUNNING
    return GeminiBatchJob.Status.SUBMITTED


def _state_name(value) -> str:
    if hasattr(value, "name"):
        return value.name
    return str(value or "")


def _model_dump(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value
