"""Email monitoring: poll -> filter -> create ResumeUpload -> process."""

import logging
import os
import re
import tempfile

from django.core.files import File
from django.db import IntegrityError
from django.utils import timezone

from accounts.models import EmailMonitorConfig
from projects.models import Project, ResumeUpload
from projects.services.email.gmail_client import GmailClient

logger = logging.getLogger(__name__)

REF_PATTERN = re.compile(r"\[REF-([0-9a-f-]{36})\]", re.IGNORECASE)


def process_email_config(config: EmailMonitorConfig) -> int:
    """Process one email config. Returns number of new uploads created."""
    client = GmailClient(config)
    org = config.user.membership.organization
    count = 0

    messages = client.get_new_messages()
    for msg in messages:
        try:
            attachments = client.get_resume_attachments(msg["id"])
        except Exception:
            logger.exception("Failed to get attachments for message %s", msg["id"])
            continue

        subject = msg.get("subject", "")
        sender = msg.get("from", "")
        project = _match_project(subject, org)

        for att in attachments:
            try:
                _create_email_upload(
                    config=config,
                    client=client,
                    org=org,
                    msg=msg,
                    att=att,
                    subject=subject,
                    sender=sender,
                    project=project,
                )
                count += 1
            except IntegrityError:
                logger.debug(
                    "Duplicate attachment skipped: msg=%s att=%s",
                    msg["id"],
                    att["id"],
                )
                continue
            except Exception:
                logger.exception(
                    "Failed to process attachment %s from message %s",
                    att.get("id"),
                    msg["id"],
                )
                continue

    config.last_checked_at = timezone.now()
    config.save(update_fields=["last_checked_at", "last_history_id", "updated_at"])
    return count


def _match_project(subject: str, org) -> Project | None:
    """Match email subject to project via [REF-{uuid}] pattern. Org-scoped."""
    match = REF_PATTERN.search(subject)
    if not match:
        return None
    try:
        return Project.objects.get(pk=match.group(1), organization=org)
    except Project.DoesNotExist:
        return None


def _create_email_upload(
    *,
    config,
    client,
    org,
    msg,
    att,
    subject,
    sender,
    project,
) -> ResumeUpload:
    """Download attachment and create ResumeUpload.

    Raises IntegrityError on duplicate.
    """
    data = client.download_attachment(msg["id"], att["id"])

    with tempfile.NamedTemporaryFile(
        suffix=os.path.splitext(att["filename"])[1],
        delete=False,
    ) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            upload = ResumeUpload(
                organization=org,
                project=project,
                file_name=att["filename"],
                file_type=_get_file_type(att["filename"]),
                source=ResumeUpload.Source.EMAIL,
                status=ResumeUpload.Status.PENDING,
                email_subject=subject[:500],
                email_from=sender,
                email_message_id=msg["id"],
                email_attachment_id=att["id"],
                created_by=config.user,
            )
            upload.file.save(att["filename"], File(f), save=False)
            upload.save()
    finally:
        os.unlink(tmp_path)
    return upload


def _get_file_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return {
        ".pdf": ResumeUpload.FileType.PDF,
        ".docx": ResumeUpload.FileType.DOCX,
        ".doc": ResumeUpload.FileType.DOC,
    }.get(ext, ResumeUpload.FileType.PDF)
