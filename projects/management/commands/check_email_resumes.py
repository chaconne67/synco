"""Check Gmail for resume attachments. Run via cron every 30 minutes."""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import EmailMonitorConfig
from projects.models import ResumeUpload
from projects.services.email.monitor import process_email_config
from projects.services.resume.uploader import process_pending_upload

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Check Gmail for resume attachments and process them"

    def handle(self, *args, **options):
        # Phase 1: Collect new attachments from all active configs
        with transaction.atomic():
            configs = EmailMonitorConfig.objects.filter(
                is_active=True
            ).select_for_update(skip_locked=True)
            for config in configs:
                try:
                    count = process_email_config(config)
                    if count:
                        self.stdout.write(f"User {config.user}: {count} new uploads")
                except Exception:
                    logger.exception("Email check failed for user %s", config.user_id)
                    continue

        # Phase 2: Process all pending email uploads
        pending = ResumeUpload.objects.filter(
            source=ResumeUpload.Source.EMAIL,
            status=ResumeUpload.Status.PENDING,
        )
        for upload in pending:
            try:
                process_pending_upload(upload)
                _notify_if_needed(upload)
            except Exception:
                logger.exception("Failed processing upload %s", upload.pk)

        self.stdout.write(self.style.SUCCESS("Email resume check complete"))


def _notify_if_needed(upload: ResumeUpload) -> None:
    """Send telegram notification for processed email resume (best-effort)."""
    if upload.status not in (
        ResumeUpload.Status.EXTRACTED,
        ResumeUpload.Status.DUPLICATE,
    ):
        return
    try:
        from accounts.models import TelegramBinding

        user = upload.created_by
        if not user:
            return
        binding = TelegramBinding.objects.filter(user=user, is_active=True).first()
        if not binding:
            return
        from projects.services.notification import _send_telegram_message

        text = f"새 이력서 수신: {upload.file_name}"
        if upload.email_from:
            text += f"\n발신자: {upload.email_from}"
        if upload.project:
            text += f"\n프로젝트: {upload.project.title}"
        _send_telegram_message(binding.chat_id, text)
    except Exception:
        logger.exception("Telegram notification failed for upload %s", upload.pk)
