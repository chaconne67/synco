"""ResumeUpload state machine with enforced transitions."""
from django.db import transaction

from projects.models import ResumeUpload

Status = ResumeUpload.Status

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    Status.PENDING: {Status.EXTRACTING},
    Status.EXTRACTING: {Status.EXTRACTED, Status.FAILED},
    Status.EXTRACTED: {Status.LINKED, Status.DISCARDED, Status.DUPLICATE},
    Status.FAILED: {Status.PENDING},  # retry only
    Status.DUPLICATE: {Status.LINKED, Status.DISCARDED},
    Status.LINKED: set(),  # terminal
    Status.DISCARDED: set(),  # terminal
}


def transition_status(
    upload: ResumeUpload,
    new_status: str,
    *,
    error_message: str = "",
) -> ResumeUpload:
    """Enforce valid state transition under transaction + select_for_update."""
    with transaction.atomic():
        upload = ResumeUpload.objects.select_for_update().get(pk=upload.pk)
        allowed = ALLOWED_TRANSITIONS.get(upload.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {upload.status} -> {new_status}"
            )
        upload.status = new_status
        if error_message:
            upload.error_message = error_message
        upload.save(update_fields=["status", "error_message", "updated_at"])
    return upload
