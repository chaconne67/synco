# P18: Email & Resume Processing — Implementation Plan

> Source: `design-spec-agreed.md`
> Strategy: Bottom-up (models → services → views → templates → tests)

---

## Phase 1: Foundation (Models + Migrations)

### Step 1.1: Add `cryptography` dependency

```bash
uv add cryptography
```

Verify in `pyproject.toml` and `uv.lock`.

### Step 1.2: ResumeUpload model

**File:** `projects/models.py`

Add after existing models:

```python
class ResumeUpload(BaseModel):
    """이력서 업로드 및 추출 추적."""

    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        DOCX = "docx", "Word (DOCX)"
        DOC = "doc", "Word (DOC)"

    class Source(models.TextChoices):
        MANUAL = "manual", "수동 업로드"
        EMAIL = "email", "이메일"

    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        EXTRACTING = "extracting", "추출중"
        EXTRACTED = "extracted", "추출완료"
        LINKED = "linked", "후보자 연결됨"
        DUPLICATE = "duplicate", "중복"
        FAILED = "failed", "실패"
        DISCARDED = "discarded", "폐기"

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="resume_uploads",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resume_uploads",
    )
    file = models.FileField(upload_to="resumes/uploads/")
    file_name = models.CharField(max_length=500)
    file_type = models.CharField(max_length=10, choices=FileType.choices)
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.MANUAL
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    candidate = models.ForeignKey(
        "candidates.Candidate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resume_uploads",
    )
    extraction_result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    last_attempted_at = models.DateTimeField(null=True, blank=True)

    # Email source fields
    email_subject = models.CharField(max_length=500, blank=True)
    email_from = models.EmailField(blank=True)
    email_message_id = models.CharField(max_length=255, blank=True)
    email_attachment_id = models.CharField(max_length=255, blank=True)

    # Upload batch tracking
    upload_batch = models.UUIDField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resume_uploads",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "email_message_id", "email_attachment_id"],
                condition=models.Q(source="email"),
                name="unique_email_attachment_per_org",
            ),
        ]

    def __str__(self) -> str:
        return f"ResumeUpload: {self.file_name} ({self.get_status_display()})"
```

### Step 1.3: EmailMonitorConfig model

**File:** `accounts/models.py`

```python
class EmailMonitorConfig(BaseModel):
    """Gmail 모니터링 설정."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="email_monitor_config",
    )
    gmail_credentials = models.BinaryField()
    is_active = models.BooleanField(default=True)
    filter_labels = models.JSONField(default=list, blank=True)
    filter_from = models.JSONField(default=list, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_history_id = models.CharField(max_length=255, blank=True)

    def __str__(self) -> str:
        return f"EmailMonitor: {self.user} (active={self.is_active})"

    def set_credentials(self, credentials_dict: dict) -> None:
        """Encrypt and store OAuth2 credentials."""
        import json
        from projects.services.email.crypto import encrypt_data
        self.gmail_credentials = encrypt_data(json.dumps(credentials_dict).encode())

    def get_credentials(self) -> dict:
        """Decrypt and return OAuth2 credentials."""
        import json
        from projects.services.email.crypto import decrypt_data
        return json.loads(decrypt_data(bytes(self.gmail_credentials)))
```

### Step 1.4: Run migrations

```bash
uv run python manage.py makemigrations projects accounts
uv run python manage.py migrate
```

### Step 1.5: Register in admin

**File:** `projects/admin.py` — Add `ResumeUpload` admin.
**File:** `accounts/admin.py` — Add `EmailMonitorConfig` admin.

---

## Phase 2: Core Services (Resume Processing)

### Step 2.1: Crypto utility

**File:** `projects/services/email/crypto.py`

```python
"""Fernet encryption for Gmail OAuth tokens."""
import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _get_fernet() -> Fernet:
    """Derive Fernet key from Django SECRET_KEY."""
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_data(data: bytes) -> bytes:
    return _get_fernet().encrypt(data)


def decrypt_data(data: bytes) -> bytes:
    return _get_fernet().decrypt(data)
```

### Step 2.2: State transition service

**File:** `projects/services/resume/transitions.py`

```python
"""ResumeUpload state machine."""
from django.db import transaction
from projects.models import ResumeUpload

Status = ResumeUpload.Status

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    Status.PENDING: {Status.EXTRACTING},
    Status.EXTRACTING: {Status.EXTRACTED, Status.FAILED},
    Status.EXTRACTED: {Status.LINKED, Status.DISCARDED, Status.DUPLICATE},
    Status.FAILED: {Status.PENDING},
    Status.DUPLICATE: {Status.LINKED, Status.DISCARDED},
    Status.LINKED: set(),
    Status.DISCARDED: set(),
}


def transition_status(
    upload: ResumeUpload,
    new_status: str,
    *,
    error_message: str = "",
) -> ResumeUpload:
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
```

### Step 2.3: Uploader service

**File:** `projects/services/resume/uploader.py`

Responsibilities:
1. Validate file (size <= 20MB, extension in [pdf, docx, doc], MIME check)
2. Create ResumeUpload(status=pending)
3. Process pending: extract_text → run_extraction_with_retry → update status

```python
"""Resume upload processing service."""
import logging
import os
import tempfile
import uuid

from django.db import transaction
from django.utils import timezone

from data_extraction.services.pipeline import run_extraction_with_retry
from data_extraction.services.text import extract_text, preprocess_resume_text
from data_extraction.services.filename import parse_filename
from projects.models import ResumeUpload
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
    """Validate uploaded file. Returns (extension, file_type)."""
    if file.size > MAX_FILE_SIZE:
        raise FileValidationError("파일 크기가 20MB를 초과합니다.")

    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(f"지원하지 않는 파일 형식입니다: {ext}")

    content_type = file.content_type
    if content_type not in ALLOWED_MIMES:
        raise FileValidationError(f"잘못된 파일 형식입니다: {content_type}")

    file_type = EXTENSION_TO_FILE_TYPE[ext]
    return ext, file_type


def create_upload(
    *,
    file,
    project,
    organization,
    user,
    upload_batch: uuid.UUID,
    source: str = ResumeUpload.Source.MANUAL,
) -> ResumeUpload:
    """Create a ResumeUpload record (status=pending)."""
    ext, file_type = validate_file(file)

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
    """Process a single pending upload: extract text → run pipeline."""
    transition_status(upload, ResumeUpload.Status.EXTRACTING)
    upload.last_attempted_at = timezone.now()
    upload.save(update_fields=["last_attempted_at", "updated_at"])

    try:
        # Write file to temp location for text extraction
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
            # Check for duplicate candidate
            from candidates.services.candidate_identity import (
                build_candidate_comparison_context,
            )

            context = build_candidate_comparison_context(result["extracted"])
            if context and context.candidate:
                transition_status(upload, ResumeUpload.Status.DUPLICATE)
            else:
                transition_status(upload, ResumeUpload.Status.EXTRACTED)
        else:
            transition_status(
                upload,
                ResumeUpload.Status.FAILED,
                error_message=f"Extraction failed: {result.get('diagnosis', {}).get('verdict', 'unknown')}",
            )

    except Exception as e:
        logger.exception("Resume processing failed for upload %s", upload.pk)
        transition_status(
            upload,
            ResumeUpload.Status.FAILED,
            error_message=str(e)[:1000],
        )

    return upload
```

### Step 2.4: Linker service

**File:** `projects/services/resume/linker.py`

```python
"""Link extracted resume to candidate + create Contact."""
import logging

from django.db import transaction

from candidates.services.candidate_identity import build_candidate_comparison_context
from data_extraction.services.save import save_pipeline_result
from projects.models import Contact, ResumeUpload
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

    extracted = upload.extraction_result
    if not extracted or not extracted.get("extracted"):
        raise ValueError("No extraction result to link")

    with transaction.atomic():
        # Use existing candidate_identity for matching
        comparison_context = build_candidate_comparison_context(
            extracted["extracted"]
        )

        if comparison_context and comparison_context.candidate and not force_new:
            candidate = comparison_context.candidate
            # Update existing candidate with new data
            from data_extraction.services.save import _update_candidate, _rebuild_sub_records
            from candidates.models import Category

            category, _ = Category.objects.get_or_create(
                name="upload",
                defaults={"name_ko": "업로드"},
            )
            candidate = _update_candidate(
                candidate, extracted["extracted"],
                upload.extraction_result.get("raw_text_used", ""),
                {"confidence_score": extracted.get("diagnosis", {}).get("overall_score", 0.0),
                 "validation_status": "needs_review",
                 "field_confidences": {}},
                category,
            )
            _rebuild_sub_records(candidate, extracted["extracted"])
            candidate.save()
        else:
            # Create new candidate via save_pipeline_result
            from candidates.models import Category

            category, _ = Category.objects.get_or_create(
                name="upload",
                defaults={"name_ko": "업로드"},
            )
            candidate = save_pipeline_result(
                pipeline_result=extracted,
                raw_text=extracted.get("raw_text_used", ""),
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

        # Create Contact to place candidate in project search tab
        if upload.project:
            Contact.objects.get_or_create(
                project=upload.project,
                candidate=candidate,
                defaults={
                    "consultant": user,
                    "result": Contact.Result.INTERESTED,
                    "notes": f"이력서 업로드로 추가 ({upload.file_name})",
                },
            )

    return upload
```

### Step 2.5: `__init__.py` files

Create empty `__init__.py` for new service directories:
- `projects/services/resume/__init__.py`
- `projects/services/email/__init__.py`

---

## Phase 3: Views + URLs (Stage 1 — Manual Upload)

### Step 3.1: Views

**File:** `projects/views.py` — Add resume upload views.

```python
@login_required
def resume_upload(request, pk):
    """POST: Upload resume files, create ResumeUpload(pending) records."""
    project = get_object_or_404(
        Project.objects.filter(organization=request.user.membership.organization),
        pk=pk,
    )
    batch_id = uuid.uuid4()
    uploads = []
    errors = []

    for f in request.FILES.getlist("files"):
        try:
            upload = create_upload(
                file=f,
                project=project,
                organization=project.organization,
                user=request.user,
                upload_batch=batch_id,
            )
            uploads.append(upload)
        except FileValidationError as e:
            errors.append({"file": f.name, "error": str(e)})

    # Return partial HTML with batch_id for polling
    ...


@login_required
def resume_process_pending(request, pk):
    """POST: Process all pending uploads for this project/batch."""
    project = get_object_or_404(
        Project.objects.filter(organization=request.user.membership.organization),
        pk=pk,
    )
    batch_id = request.POST.get("batch_id")
    pending = ResumeUpload.objects.filter(
        project=project,
        upload_batch=batch_id,
        status=ResumeUpload.Status.PENDING,
    )
    for upload in pending:
        process_pending_upload(upload)
    # Return status partial
    ...


@login_required
def resume_upload_status(request, pk):
    """GET: Return status partial for HTMX polling."""
    project = get_object_or_404(
        Project.objects.filter(organization=request.user.membership.organization),
        pk=pk,
    )
    batch_id = request.GET.get("batch")
    uploads = ResumeUpload.objects.filter(
        project=project,
        created_by=request.user,
    )
    if batch_id:
        uploads = uploads.filter(upload_batch=batch_id)
    # Render partial
    ...


@login_required
def resume_link_candidate(request, pk, resume_pk):
    """POST: Link extracted resume to candidate."""
    project = get_object_or_404(
        Project.objects.filter(organization=request.user.membership.organization),
        pk=pk,
    )
    upload = get_object_or_404(
        ResumeUpload.objects.filter(project=project),
        pk=resume_pk,
    )
    link_resume_to_candidate(upload, user=request.user)
    ...


@login_required
def resume_discard(request, pk, resume_pk):
    """POST: Discard resume upload + delete file."""
    project = get_object_or_404(
        Project.objects.filter(organization=request.user.membership.organization),
        pk=pk,
    )
    upload = get_object_or_404(
        ResumeUpload.objects.filter(project=project),
        pk=resume_pk,
    )
    transition_status(upload, ResumeUpload.Status.DISCARDED)
    if upload.file:
        upload.file.delete(save=False)
    ...


@login_required
def resume_retry(request, pk, resume_pk):
    """POST: Retry failed extraction."""
    project = get_object_or_404(
        Project.objects.filter(organization=request.user.membership.organization),
        pk=pk,
    )
    upload = get_object_or_404(
        ResumeUpload.objects.filter(project=project),
        pk=resume_pk,
    )
    if upload.retry_count >= 3:
        return HttpResponseBadRequest("재시도 횟수를 초과했습니다.")
    upload.retry_count += 1
    upload.save(update_fields=["retry_count", "updated_at"])
    transition_status(upload, ResumeUpload.Status.PENDING)
    process_pending_upload(upload)
    ...
```

### Step 3.2: URLs

**File:** `projects/urls.py` — Add resume upload URLs.

```python
# P18: Resume upload
path(
    "<uuid:pk>/resumes/upload/",
    views.resume_upload,
    name="resume_upload",
),
path(
    "<uuid:pk>/resumes/process/",
    views.resume_process_pending,
    name="resume_process_pending",
),
path(
    "<uuid:pk>/resumes/status/",
    views.resume_upload_status,
    name="resume_upload_status",
),
path(
    "<uuid:pk>/resumes/<uuid:resume_pk>/link/",
    views.resume_link_candidate,
    name="resume_link_candidate",
),
path(
    "<uuid:pk>/resumes/<uuid:resume_pk>/discard/",
    views.resume_discard,
    name="resume_discard",
),
path(
    "<uuid:pk>/resumes/<uuid:resume_pk>/retry/",
    views.resume_retry,
    name="resume_retry",
),
```

---

## Phase 4: Frontend (Stage 1)

### Step 4.1: Upload template

**File:** `projects/templates/projects/partials/resume_upload.html`

Drag & drop zone with file input fallback. Accepts PDF, DOCX, DOC.
On file selection: POST to upload URL with FormData, then POST to process URL.
Start HTMX polling on status URL.

### Step 4.2: Status template

**File:** `projects/templates/projects/partials/resume_status.html`

Lists ResumeUpload records for the batch:
- pending/extracting: spinner
- extracted: [연결] [폐기] buttons
- duplicate: warning + [연결(병합)] [새로 생성] [폐기] buttons
- failed: error message + [재시도] button (if retry_count < 3)
- linked: success indicator
- discarded: strikethrough

HTMX: `hx-get` to status URL, `hx-trigger="every 2s"`, `hx-swap="innerHTML"`.
Stop polling when all uploads are terminal (linked/discarded/failed with no retry).

### Step 4.3: JavaScript

**File:** `static/js/resume-upload.js`

```javascript
// Drag & drop + file input handling
// POST /upload/ with FormData (multiple files)
// On success: extract batch_id from response
// POST /process/ with batch_id (fire and observe via polling)
// HTMX auto-handles polling via template attributes
```

### Step 4.4: Integrate into search tab

**File:** `projects/templates/projects/partials/tab_search.html`

Add [이력서 업로드] button/section that toggles the upload area.

---

## Phase 5: Gmail API Integration (Stage 2)

### Step 5.1: Gmail client

**File:** `projects/services/email/gmail_client.py`

```python
"""Gmail API wrapper with auth, token refresh, message/attachment handling."""

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
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            # Save refreshed credentials
            self.config.set_credentials(json.loads(creds.to_json()))
            self.config.save(update_fields=["gmail_credentials", "updated_at"])

        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def get_new_messages(self) -> list[dict]:
        """Poll for new messages using history_id or fallback."""
        ...

    def get_attachments(self, message_id: str) -> list[dict]:
        """Get resume attachments from a message (PDF/DOCX/DOC, <= 20MB)."""
        ...

    def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download attachment content."""
        ...
```

### Step 5.2: Email monitor service

**File:** `projects/services/email/monitor.py`

```python
"""Email monitoring: poll → filter → create ResumeUpload → process."""

def process_email_config(config: EmailMonitorConfig) -> int:
    """Process one email config. Returns number of new uploads created."""
    client = GmailClient(config)
    org = config.user.membership.organization
    count = 0

    messages = client.get_new_messages()
    for msg in messages:
        attachments = client.get_attachments(msg["id"])
        for att in attachments:
            # Check dedup constraint
            if ResumeUpload.objects.filter(
                organization=org,
                email_message_id=msg["id"],
                email_attachment_id=att["id"],
            ).exists():
                continue

            # Download and create upload
            data = client.download_attachment(msg["id"], att["id"])
            # ... save to temp file, create ResumeUpload(source=email)
            # ... match project via [REF-{uuid}] in subject
            count += 1

    # Update last_checked_at and history_id
    config.last_checked_at = timezone.now()
    config.save(update_fields=["last_checked_at", "last_history_id", "updated_at"])

    return count
```

### Step 5.3: Management commands

**File:** `projects/management/commands/check_email_resumes.py`

```python
"""Check email for resume attachments."""
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import EmailMonitorConfig
from projects.services.email.monitor import process_email_config
from projects.services.resume.uploader import process_pending_upload


class Command(BaseCommand):
    help = "Check Gmail for resume attachments"

    def handle(self, *args, **options):
        configs = EmailMonitorConfig.objects.filter(
            is_active=True,
        ).select_for_update(skip_locked=True)

        with transaction.atomic():
            for config in configs:
                try:
                    count = process_email_config(config)
                    self.stdout.write(f"User {config.user}: {count} new uploads")
                except Exception:
                    logger.exception("Failed for user %s", config.user_id)
                    continue

        # Process all pending email uploads
        pending = ResumeUpload.objects.filter(
            source=ResumeUpload.Source.EMAIL,
            status=ResumeUpload.Status.PENDING,
        )
        for upload in pending:
            try:
                process_pending_upload(upload)
                # Send telegram notification if linked
                if upload.status == ResumeUpload.Status.EXTRACTED:
                    _notify_telegram(upload)
            except Exception:
                logger.exception("Failed processing upload %s", upload.pk)
```

**File:** `projects/management/commands/cleanup_failed_uploads.py`

```python
"""Clean up failed uploads older than 30 days."""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from projects.models import ResumeUpload


class Command(BaseCommand):
    help = "Delete failed resume uploads older than 30 days"

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=30)
        old_failed = ResumeUpload.objects.filter(
            status=ResumeUpload.Status.FAILED,
            created_at__lt=cutoff,
        )
        count = 0
        for upload in old_failed:
            if upload.file:
                upload.file.delete(save=False)
            upload.delete()
            count += 1
        self.stdout.write(f"Cleaned up {count} failed uploads")
```

### Step 5.4: Gmail OAuth views

**File:** `accounts/views.py` — Add email OAuth views.

```python
@login_required
def email_connect(request):
    """Start Gmail OAuth flow."""
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_OAUTH_SECRETS_FILE,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        redirect_uri=request.build_absolute_uri(reverse("accounts:email_callback")),
    )
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    request.session["gmail_oauth_state"] = state
    return redirect(authorization_url)


@login_required
def email_oauth_callback(request):
    """Handle Gmail OAuth callback."""
    ...
    # Exchange code for credentials
    # Create/update EmailMonitorConfig
    # Encrypt and store credentials
    ...


@login_required
def email_settings(request):
    """Gmail monitoring settings page."""
    ...


@login_required
def email_disconnect(request):
    """Disconnect Gmail: revoke token, deactivate config."""
    ...
```

### Step 5.5: Gmail URLs

**File:** `accounts/urls.py`

```python
# P18: Gmail integration
path("email/connect/", views.email_connect, name="email_connect"),
path("email/callback/", views.email_oauth_callback, name="email_callback"),
path("email/settings/", views.email_settings, name="email_settings"),
path("email/disconnect/", views.email_disconnect, name="email_disconnect"),
```

### Step 5.6: Email settings template

**File:** `accounts/templates/accounts/email_settings.html`

Gmail connection status, filter settings, disconnect button.

---

## Phase 6: Telegram Notification Integration

### Step 6.1: Best-effort notification

Add to `projects/services/resume/uploader.py` or `monitor.py`:

```python
def notify_resume_processed(upload: ResumeUpload) -> None:
    """Send telegram notification for processed resume (best-effort)."""
    try:
        user = upload.created_by or (
            upload.organization and
            upload.organization.memberships.first() and
            upload.organization.memberships.first().user
        )
        if not user:
            return

        from accounts.models import TelegramBinding
        binding = TelegramBinding.objects.filter(
            user=user, is_active=True
        ).first()
        if not binding:
            return

        from projects.services.notification import _send_telegram_message
        text = f"이력서 처리 완료: {upload.file_name}"
        if upload.candidate:
            text += f"\n후보자: {upload.candidate.name}"
        if upload.project:
            text += f"\n프로젝트: {upload.project.title}"

        _send_telegram_message(binding.chat_id, text)
    except Exception:
        logger.exception("Telegram notification failed for upload %s", upload.pk)
```

---

## Phase 7: Tests

### Step 7.1: Model tests

**File:** `tests/test_resume_upload_model.py`

- ResumeUpload creation with all fields
- Unique constraint on email dedup
- State transition validation
- EmailMonitorConfig credential encryption/decryption

### Step 7.2: Service tests

**File:** `tests/test_resume_uploader.py`

- File validation (size, extension, MIME)
- process_pending_upload with mock extraction pipeline
- Error handling (extraction failure → status=failed)

**File:** `tests/test_resume_linker.py`

- Link to new candidate
- Link to existing candidate (duplicate merge)
- Contact creation on link
- Atomic transaction behavior

### Step 7.3: View tests

**File:** `tests/test_resume_views.py`

- Upload POST with valid file → 200 + ResumeUpload created
- Upload POST with oversized file → 400
- Status GET scoped to user + project
- Link POST → candidate created + Contact created
- Discard POST → file deleted + status=discarded
- Retry POST → retry_count incremented
- Retry POST with retry_count >= 3 → 400
- Authorization: wrong org → 403

### Step 7.4: Gmail integration tests

**File:** `tests/test_email_monitor.py`

- check_email_resumes command with mocked Gmail API
- Dedup constraint prevents re-import
- history_id fallback
- Token refresh on expired access token
- select_for_update concurrency protection

---

## Implementation Order Summary

| Phase | Files | Depends On |
|-------|-------|-----------|
| 1. Foundation | models, migrations, admin | — |
| 2. Core Services | crypto, transitions, uploader, linker | Phase 1 |
| 3. Views + URLs | views.py, urls.py | Phase 2 |
| 4. Frontend | templates, JS | Phase 3 |
| 5. Gmail Integration | gmail_client, monitor, commands, OAuth views | Phase 2 |
| 6. Telegram | notification helper | Phase 5 |
| 7. Tests | all test files | Phase 1-6 |

Total estimated files: ~20 new files + modifications to ~6 existing files.
