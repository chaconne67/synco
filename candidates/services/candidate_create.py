from __future__ import annotations

import logging
import os
import tempfile
import uuid as _uuid

from django.db import transaction

from candidates.models import Candidate, Resume

MANUAL_UPLOAD_FOLDER_NAME = "수동등록"
DRIVE_PARENT_ID = "1k_VtpvJo8P8ynGTvVWS8DtYtK4gZDF_Y"
MAX_RESUME_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_RESUME_EXTS = {"pdf", "doc", "docx"}

logger = logging.getLogger(__name__)


def find_duplicate(email: str | None, phone: str | None) -> Candidate | None:
    """Return existing candidate matching email or phone, else None.

    Mirrors `identify_candidate()`'s matching rules:
      1. email exact (case-insensitive)
      2. phone_normalized exact (requires >= 10 digits after normalization)
    """
    from candidates.services.candidate_identity import normalize_phone_for_matching

    if email:
        hit = Candidate.objects.filter(email__iexact=email.strip()).first()
        if hit:
            return hit
    if phone:
        normalized = normalize_phone_for_matching(phone)
        if len(normalized) >= 10:
            hit = Candidate.objects.filter(phone_normalized=normalized).first()
            if hit:
                return hit
    return None


@transaction.atomic
def create_candidate(data: dict, user=None) -> Candidate:
    """Create a Candidate. Caller is responsible for duplicate check."""
    field_whitelist = {
        "name", "email", "phone", "current_company", "current_position",
        "birth_year", "source", "address",
    }
    kwargs = {k: v for k, v in data.items() if k in field_whitelist and v not in (None, "")}
    if "birth_year" in kwargs:
        try:
            kwargs["birth_year"] = int(kwargs["birth_year"])
        except (ValueError, TypeError):
            kwargs.pop("birth_year")
    primary_category = data.get("primary_category")
    if primary_category:
        kwargs["primary_category"] = primary_category
    candidate = Candidate.objects.create(**kwargs)
    return candidate


def _upload_to_drive(local_path: str, filename: str) -> str | None:
    """Upload file to the manual-upload folder. Returns Drive file ID on success, None on failure."""
    try:
        from data_extraction.services.drive import (
            find_category_folder,
            get_drive_service,
        )
        from googleapiclient.http import MediaFileUpload

        svc = get_drive_service()
        folder_id = find_category_folder(svc, DRIVE_PARENT_ID, MANUAL_UPLOAD_FOLDER_NAME)
        if not folder_id:
            logger.warning("Drive manual-upload folder not found")
            return None
        media = MediaFileUpload(local_path, resumable=False)
        result = (
            svc.files()
            .create(
                body={"name": filename, "parents": [folder_id]},
                media_body=media,
                fields="id",
            )
            .execute()
        )
        return result.get("id")
    except Exception as e:
        logger.warning("Drive upload failed: %s", e)
        return None


def attach_resume(candidate: Candidate, uploaded_file) -> Resume:
    """Save uploaded resume to Drive (if available) and create a Resume record.

    Raises ValueError on validation failures (size / extension).
    Drive failure is tolerated — a placeholder drive_file_id is generated.
    """
    if uploaded_file.size > MAX_RESUME_SIZE:
        raise ValueError("파일 크기는 10MB 이하여야 합니다.")
    ext = os.path.splitext(uploaded_file.name)[1].lower().lstrip(".")
    if ext not in ALLOWED_RESUME_EXTS:
        raise ValueError("pdf/doc/docx만 업로드 가능합니다.")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        drive_id = _upload_to_drive(tmp_path, uploaded_file.name)
        if not drive_id:
            drive_id = f"manual-{_uuid.uuid4().hex}"

        resume = Resume.objects.create(
            candidate=candidate,
            file_name=uploaded_file.name,
            drive_file_id=drive_id,
            drive_folder=MANUAL_UPLOAD_FOLDER_NAME,
            mime_type=uploaded_file.content_type or "",
            file_size=uploaded_file.size,
            is_primary=False,
            processing_status=Resume.ProcessingStatus.PENDING,
        )
        candidate.current_resume = resume
        candidate.save(update_fields=["current_resume"])
        return resume
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
