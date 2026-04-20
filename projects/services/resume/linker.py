"""Link extracted resume to candidate."""

import logging

from django.db import transaction

from candidates.models import Category
from data_extraction.services.save import save_pipeline_result
from projects.models import ResumeUpload
from projects.services.resume.identity import identify_candidate_for_org
from projects.services.resume.transitions import transition_status

logger = logging.getLogger(__name__)


def link_resume_to_candidate(
    upload: ResumeUpload,
    *,
    user,
    force_new: bool = False,
) -> ResumeUpload:
    """Link extracted resume to existing or new candidate."""
    if upload.status not in (
        ResumeUpload.Status.EXTRACTED,
        ResumeUpload.Status.DUPLICATE,
    ):
        raise ValueError(f"Cannot link upload in status {upload.status}")

    pipeline_result = upload.extraction_result
    if not pipeline_result or not pipeline_result.get("extracted"):
        raise ValueError("No extraction result to link")

    with transaction.atomic():
        category, _ = Category.objects.get_or_create(
            name="upload",
            defaults={"name_ko": "업로드"},
        )

        comparison_context = None
        if not force_new:
            comparison_context = identify_candidate_for_org(
                pipeline_result["extracted"],
            )

        candidate = save_pipeline_result(
            pipeline_result=pipeline_result,
            raw_text=pipeline_result.get("raw_text_used", ""),
            category=category,
            primary_file={
                "file_id": str(upload.pk),
                "file_name": upload.file_name,
                "mime_type": "",
            },
            comparison_context=comparison_context,
            filename_meta={},
        )

        if candidate is None:
            raise ValueError("Failed to create candidate from extraction")

        upload.candidate = candidate
        upload.save(update_fields=["candidate", "updated_at"])
        transition_status(upload, ResumeUpload.Status.LINKED)

    return upload
