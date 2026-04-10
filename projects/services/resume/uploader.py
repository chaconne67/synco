"""Resume upload processing service."""
import logging
import os
import tempfile
import uuid

from django.utils import timezone

from data_extraction.services.filename import parse_filename
from data_extraction.services.pipeline import run_extraction_with_retry
from data_extraction.services.text import extract_text, preprocess_resume_text
from projects.models import ResumeUpload
from projects.services.resume.identity import identify_candidate_for_org
from projects.services.resume.transitions import transition_status

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}
ALLOWED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}
EXTENSION_TO_FILE_TYPE = {
    ".pdf": ResumeUpload.FileType.PDF,
    ".docx": ResumeUpload.FileType.DOCX,
    ".doc": ResumeUpload.FileType.DOC,
}


class FileValidationError(Exception):
    pass


def validate_file(file) -> tuple[str, str]:
    """Validate uploaded file. Returns (extension, file_type).
    Raises FileValidationError on invalid file."""
    if file.size > MAX_FILE_SIZE:
        raise FileValidationError("파일 크기가 20MB를 초과합니다.")
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(f"지원하지 않는 파일 형식입니다: {ext}")
    content_type = file.content_type
    if content_type not in ALLOWED_MIMES:
        raise FileValidationError(f"잘못된 파일 형식입니다: {content_type}")
    return ext, EXTENSION_TO_FILE_TYPE[ext]


def create_upload(
    *,
    file,
    project,
    organization,
    user,
    upload_batch: uuid.UUID,
    source: str = ResumeUpload.Source.MANUAL,
) -> ResumeUpload:
    """Create a ResumeUpload record (status=pending). No extraction here."""
    _ext, file_type = validate_file(file)
    return ResumeUpload.objects.create(
        organization=organization,
        project=project,
        file=file,
        file_name=file.name,
        file_type=file_type,
        source=source,
        status=ResumeUpload.Status.PENDING,
        upload_batch=upload_batch,
        created_by=user,
    )


def process_pending_upload(upload: ResumeUpload) -> ResumeUpload:
    """Process a single pending upload through the extraction pipeline.

    State flow: pending -> extracting -> extracted (-> duplicate if match)
                pending -> extracting -> failed (on error)
    """
    transition_status(upload, ResumeUpload.Status.EXTRACTING)
    upload.last_attempted_at = timezone.now()
    upload.save(update_fields=["last_attempted_at", "updated_at"])

    try:
        with tempfile.NamedTemporaryFile(
            suffix=os.path.splitext(upload.file_name)[1],
            delete=False,
        ) as tmp:
            for chunk in upload.file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            raw_text = extract_text(tmp_path)
            raw_text = preprocess_resume_text(raw_text)
            filename_meta = parse_filename(upload.file_name)

            result = run_extraction_with_retry(
                raw_text=raw_text,
                file_path=tmp_path,
                category="upload",
                filename_meta=filename_meta,
                use_integrity_pipeline=True,
                provider="gemini",
            )
        finally:
            os.unlink(tmp_path)

        upload.extraction_result = result
        upload.save(update_fields=["extraction_result", "updated_at"])

        if result.get("extracted"):
            transition_status(upload, ResumeUpload.Status.EXTRACTED)
            context = identify_candidate_for_org(
                result["extracted"],
                upload.organization,
            )
            if context and context.candidate:
                transition_status(upload, ResumeUpload.Status.DUPLICATE)
        else:
            transition_status(
                upload,
                ResumeUpload.Status.FAILED,
                error_message=(
                    f"Extraction failed: "
                    f"{result.get('diagnosis', {}).get('verdict', 'unknown')}"
                ),
            )

    except Exception as e:
        logger.exception("Resume processing failed for upload %s", upload.pk)
        transition_status(
            upload,
            ResumeUpload.Status.FAILED,
            error_message=str(e)[:1000],
        )

    return upload
