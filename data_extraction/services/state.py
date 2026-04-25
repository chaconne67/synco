"""Helpers for file-level resume extraction state tracking."""

from __future__ import annotations

from django.utils import timezone

from candidates.models import Resume
from data_extraction.models import ResumeExtractionState


def ensure_resume_for_drive_file(file_info: dict, folder_name: str) -> Resume:
    """Create or update a lightweight Resume record for a discovered Drive file."""
    resume, _created = Resume.objects.update_or_create(
        drive_file_id=file_info["file_id"],
        defaults={
            "file_name": file_info["file_name"],
            "drive_folder": folder_name,
            "mime_type": file_info.get("mime_type", ""),
            "file_size": file_info.get("file_size"),
        },
    )
    mark_discovered(resume, file_info=file_info, folder_name=folder_name)
    return resume


def ensure_state(resume: Resume) -> ResumeExtractionState:
    state, _created = ResumeExtractionState.objects.get_or_create(resume=resume)
    return state


def mark_discovered(
    resume: Resume,
    *,
    file_info: dict | None = None,
    folder_name: str = "",
) -> ResumeExtractionState:
    state = ensure_state(resume)
    if state.discovered_at is None:
        state.discovered_at = timezone.now()
    state.status = ResumeExtractionState.Status.DISCOVERED
    metadata = dict(state.metadata or {})
    if folder_name:
        metadata["drive_folder"] = folder_name
    if file_info:
        metadata["drive_file"] = {
            "file_id": file_info.get("file_id"),
            "file_name": file_info.get("file_name"),
            "mime_type": file_info.get("mime_type", ""),
            "file_size": file_info.get("file_size"),
            "modified_time": file_info.get("modified_time", ""),
        }
    state.metadata = metadata
    state.save(update_fields=["discovered_at", "status", "metadata", "updated_at"])
    return state


def mark_attempt_started(
    resume: Resume,
    *,
    status: str,
    provider: str = "",
    pipeline: str = "",
) -> ResumeExtractionState:
    now = timezone.now()
    state = ensure_state(resume)
    state.status = status
    state.last_attempted_at = now
    state.attempt_count += 1
    if provider:
        state.provider = provider
    if pipeline:
        state.pipeline = pipeline
    state.last_error = ""
    state.save(
        update_fields=[
            "status",
            "last_attempted_at",
            "attempt_count",
            "provider",
            "pipeline",
            "last_error",
            "updated_at",
        ]
    )
    return state


def mark_downloaded(resume: Resume) -> ResumeExtractionState:
    state = ensure_state(resume)
    state.status = ResumeExtractionState.Status.DOWNLOADED
    state.downloaded_at = timezone.now()
    state.save(update_fields=["status", "downloaded_at", "updated_at"])
    return state


def mark_text_extracted(resume: Resume) -> ResumeExtractionState:
    state = ensure_state(resume)
    state.status = ResumeExtractionState.Status.TEXT_EXTRACTED
    state.text_extracted_at = timezone.now()
    state.save(update_fields=["status", "text_extracted_at", "updated_at"])
    return state


def mark_extracting(
    resume: Resume,
    *,
    provider: str = "",
    pipeline: str = "",
) -> ResumeExtractionState:
    now = timezone.now()
    state = ensure_state(resume)
    state.status = ResumeExtractionState.Status.EXTRACTING
    state.extraction_started_at = now
    if provider:
        state.provider = provider
    if pipeline:
        state.pipeline = pipeline
    state.save(
        update_fields=[
            "status",
            "extraction_started_at",
            "provider",
            "pipeline",
            "updated_at",
        ]
    )
    return state


def mark_completed(
    resume: Resume,
    *,
    status: str,
    error: str = "",
    provider: str = "",
    pipeline: str = "",
    metadata: dict | None = None,
) -> ResumeExtractionState:
    state = ensure_state(resume)
    state.status = status
    state.extraction_completed_at = timezone.now()
    state.last_error = error
    if provider:
        state.provider = provider
    if pipeline:
        state.pipeline = pipeline
    if metadata:
        state.metadata = {**(state.metadata or {}), **metadata}
    state.save(
        update_fields=[
            "status",
            "extraction_completed_at",
            "last_error",
            "provider",
            "pipeline",
            "metadata",
            "updated_at",
        ]
    )
    return state

