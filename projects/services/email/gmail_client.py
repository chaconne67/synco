"""Gmail API wrapper with auth, refresh, message/attachment handling, and error recovery."""

import base64
import json
import logging
import os
import time

from googleapiclient.errors import HttpError

from accounts.models import EmailMonitorConfig

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024  # 20MB
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}
MAX_RETRIES = 5


class GmailClient:
    def __init__(self, config: EmailMonitorConfig):
        self.config = config
        self._service = None

    def _build_service(self):
        """Build Gmail API service with auto-refresh."""
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds_dict = self.config.get_credentials()
        creds = Credentials.from_authorized_user_info(creds_dict)

        if creds.expired and creds.refresh_token:
            try:
                from google.auth.transport.requests import Request

                creds.refresh(Request())
                # Persist refreshed credentials
                self.config.set_credentials(json.loads(creds.to_json()))
                self.config.save(update_fields=["gmail_credentials", "updated_at"])
            except Exception as e:
                logger.error(
                    "Gmail token refresh failed for user %s: %s",
                    self.config.user_id,
                    e,
                )
                self.config.is_active = False
                self.config.save(update_fields=["is_active", "updated_at"])
                raise

        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    @property
    def service(self):
        if self._service is None:
            self._build_service()
        return self._service

    def get_new_messages(self) -> list[dict]:
        """Poll for new messages using history_id or fallback to messages.list."""
        try:
            if self.config.last_history_id:
                return self._poll_via_history()
            else:
                return self._poll_via_search()
        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(
                    "History ID expired for user %s, falling back to search",
                    self.config.user_id,
                )
                return self._poll_via_search()
            elif e.resp.status == 401:
                self.config.is_active = False
                self.config.save(update_fields=["is_active", "updated_at"])
                raise
            elif e.resp.status == 429:
                return self._retry_with_backoff(self._poll_via_history)
            elif e.resp.status >= 500:
                logger.error(
                    "Gmail server error for user %s: %s",
                    self.config.user_id,
                    e,
                )
                return []
            else:
                raise

    def _poll_via_history(self) -> list[dict]:
        """Incremental poll via history API."""
        results = (
            self.service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=self.config.last_history_id,
                historyTypes=["messageAdded"],
            )
            .execute()
        )

        history = results.get("history", [])
        # Update history ID for next poll
        if "historyId" in results:
            self.config.last_history_id = results["historyId"]

        message_ids = set()
        for record in history:
            for msg_added in record.get("messagesAdded", []):
                message_ids.add(msg_added["message"]["id"])

        messages = []
        for msg_id in message_ids:
            try:
                msg = (
                    self.service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["Subject", "From"],
                    )
                    .execute()
                )
                messages.append(self._parse_message_metadata(msg))
            except HttpError:
                logger.exception("Failed to fetch message %s", msg_id)
                continue

        return messages

    def _poll_via_search(self) -> list[dict]:
        """Full search fallback when history is unavailable."""
        query = "has:attachment"
        if self.config.last_checked_at:
            epoch = int(self.config.last_checked_at.timestamp())
            query += f" after:{epoch}"

        # Apply sender filters if configured
        if self.config.filter_from:
            from_query = " OR ".join(f"from:{addr}" for addr in self.config.filter_from)
            query += f" ({from_query})"

        results = (
            self.service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=50,
            )
            .execute()
        )

        message_list = results.get("messages", [])
        # Update history ID from profile for next poll
        profile = self.service.users().getProfile(userId="me").execute()
        self.config.last_history_id = str(profile.get("historyId", ""))

        messages = []
        for msg_ref in message_list:
            try:
                msg = (
                    self.service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_ref["id"],
                        format="metadata",
                        metadataHeaders=["Subject", "From"],
                    )
                    .execute()
                )
                messages.append(self._parse_message_metadata(msg))
            except HttpError:
                logger.exception("Failed to fetch message %s", msg_ref["id"])
                continue

        return messages

    def _parse_message_metadata(self, msg: dict) -> dict:
        """Extract subject and from from message metadata."""
        headers = {
            h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])
        }
        return {
            "id": msg["id"],
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
        }

    def _retry_with_backoff(self, fn, max_retries=MAX_RETRIES):
        """Exponential backoff for rate-limited requests."""
        for attempt in range(max_retries):
            try:
                return fn()
            except HttpError as e:
                if e.resp.status == 429 and attempt < max_retries - 1:
                    wait = 2**attempt
                    logger.warning("Rate limited, waiting %ds", wait)
                    time.sleep(wait)
                else:
                    raise
        return []

    def get_resume_attachments(self, message_id: str) -> list[dict]:
        """Get resume attachments from a message. Filters by type and size."""
        msg = (
            self.service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full",
            )
            .execute()
        )

        attachments = []
        for part in msg.get("payload", {}).get("parts", []):
            filename = part.get("filename", "")
            if not filename:
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue
            body = part.get("body", {})
            size = body.get("size", 0)
            if size > MAX_ATTACHMENT_SIZE:
                logger.warning("Attachment too large: %s (%d bytes)", filename, size)
                continue
            att_id = body.get("attachmentId")
            if att_id:
                attachments.append(
                    {
                        "id": att_id,
                        "filename": filename,
                        "size": size,
                    }
                )
        return attachments

    def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download attachment content."""
        att = (
            self.service.users()
            .messages()
            .attachments()
            .get(
                userId="me",
                messageId=message_id,
                id=attachment_id,
            )
            .execute()
        )
        data = att.get("data", "")
        return base64.urlsafe_b64decode(data)
