# P18: Email & Resume Processing — Confirmed Implementation Plan

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

Add after existing models. Inherit `BaseModel`. All FKs use explicit `on_delete`:

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
        null=True, blank=True,
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
        null=True, blank=True,
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
        null=True, blank=True,
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

**File:** `projects/admin.py` — Add `ResumeUpload` admin with list_display, list_filter, search_fields.
**File:** `accounts/admin.py` — Add `EmailMonitorConfig` admin.

---

## Phase 2: Core Services (Resume Processing)

### Step 2.1: Crypto utility (HKDF, not SHA-256)

**File:** `projects/services/email/__init__.py` (empty)
**File:** `projects/services/email/crypto.py`

```python
"""Fernet encryption for Gmail OAuth tokens using HKDF key derivation."""
import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings


def _get_fernet() -> Fernet:
    """Derive Fernet key from Django SECRET_KEY using HKDF."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"synco-gmail-credentials",
        info=b"fernet-key",
    )
    key = hkdf.derive(settings.SECRET_KEY.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_data(data: bytes) -> bytes:
    """Encrypt data using Fernet with HKDF-derived key."""
    return _get_fernet().encrypt(data)


def decrypt_data(data: bytes) -> bytes:
    """Decrypt data using Fernet with HKDF-derived key."""
    return _get_fernet().decrypt(data)
```

### Step 2.2: State transition service

**File:** `projects/services/resume/__init__.py` (empty)
**File:** `projects/services/resume/transitions.py`

```python
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
```

### Step 2.3: Org-aware identity matching wrapper

**File:** `projects/services/resume/identity.py`

```python
"""Org-scoped candidate identity matching for resume uploads."""
from accounts.models import Organization
from candidates.models import Candidate
from candidates.services.candidate_identity import (
    CandidateComparisonContext,
    _normalize_phone,
    _latest_parsed_resume,
    normalize_phone_for_matching,
)


def identify_candidate_for_org(
    extracted: dict,
    organization: Organization,
) -> CandidateComparisonContext | None:
    """Find existing candidate within organization scope only.

    Same matching logic as candidate_identity.py but filtered by owned_by.
    Prevents cross-tenant candidate leakage.
    """
    # 1. Email match (org-scoped)
    email = (extracted.get("email") or "").strip().lower()
    if email:
        candidate = (
            Candidate.objects.filter(
                email__iexact=email,
                owned_by=organization,
            )
            .order_by("-created_at")
            .first()
        )
        if candidate:
            compared_resume = _latest_parsed_resume(candidate)
            previous_data = _build_previous_data(candidate, compared_resume)
            return CandidateComparisonContext(
                candidate=candidate,
                compared_resume=compared_resume,
                match_reason="email",
                previous_data=previous_data,
            )

    # 2. Phone match (org-scoped)
    phone = extracted.get("phone") or ""
    normalized = normalize_phone_for_matching(phone)
    if len(normalized) >= 10:
        candidate = (
            Candidate.objects.filter(
                phone_normalized=normalized,
                owned_by=organization,
            )
            .order_by("-created_at")
            .first()
        )
        if candidate:
            compared_resume = _latest_parsed_resume(candidate)
            previous_data = _build_previous_data(candidate, compared_resume)
            return CandidateComparisonContext(
                candidate=candidate,
                compared_resume=compared_resume,
                match_reason="phone",
                previous_data=previous_data,
            )

    return None


def _build_previous_data(candidate, compared_resume) -> dict:
    """Build previous_data dict for cross-version comparison."""
    if not compared_resume or not compared_resume.raw_text:
        return {}
    return candidate.raw_extracted_json or {}
```

### Step 2.4: Uploader service

**File:** `projects/services/resume/uploader.py`

Responsibilities:
1. Validate file (size <= 20MB, extension in [pdf, docx, doc], MIME check)
2. Create ResumeUpload(status=pending)
3. Process pending: extract_text -> preprocess -> run_extraction_with_retry -> update status
4. Two-step duplicate: extracting -> extracted first, then extracted -> duplicate if match found

```python
"""Resume upload processing service."""
import logging
import os
import tempfile
import uuid

from django.utils import timezone

from data_extraction.services.pipeline import run_extraction_with_retry
from data_extraction.services.text import extract_text, preprocess_resume_text
from data_extraction.services.filename import parse_filename
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
        # Write uploaded file to temp location for text extraction
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
            # Step 1: Always transition to EXTRACTED first
            transition_status(upload, ResumeUpload.Status.EXTRACTED)

            # Step 2: Then check for duplicate (org-scoped)
            context = identify_candidate_for_org(
                result["extracted"],
                upload.organization,
            )
            if context and context.candidate:
                # Step 3: Transition EXTRACTED -> DUPLICATE
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
```

### Step 2.5: Linker service

**File:** `projects/services/resume/linker.py`

Uses `save_pipeline_result()` for both new and existing candidates (not private `_update_candidate()`).
Sets `owned_by` on newly created candidates.

```python
"""Link extracted resume to candidate + create Contact."""
import logging

from django.db import transaction

from candidates.models import Category
from data_extraction.services.save import save_pipeline_result
from projects.models import Contact, ResumeUpload
from projects.services.resume.identity import identify_candidate_for_org
from projects.services.resume.transitions import transition_status

logger = logging.getLogger(__name__)


def link_resume_to_candidate(
    upload: ResumeUpload,
    *,
    user,
    force_new: bool = False,
) -> ResumeUpload:
    """Link extracted resume to existing or new candidate.

    Uses save_pipeline_result() for full persistence (Resume version,
    ExtractionLog, ValidationDiagnosis, DiscrepancyReport).
    Sets candidate.owned_by for org scoping.
    Creates Contact record for project search tab visibility.
    """
    if upload.status not in (
        ResumeUpload.Status.EXTRACTED,
        ResumeUpload.Status.DUPLICATE,
    ):
        raise ValueError(f"Cannot link upload in status {upload.status}")

    pipeline_result = upload.extraction_result
    if not pipeline_result or not pipeline_result.get("extracted"):
        raise ValueError("No extraction result to link")

    with transaction.atomic():
        # Get or create upload category
        category, _ = Category.objects.get_or_create(
            name="upload",
            defaults={"name_ko": "업로드"},
        )

        # Org-scoped identity matching (unless force_new)
        comparison_context = None
        if not force_new:
            comparison_context = identify_candidate_for_org(
                pipeline_result["extracted"],
                upload.organization,
            )

        # Use save_pipeline_result for full persistence path
        # (handles both new and existing candidates)
        candidate = save_pipeline_result(
            pipeline_result=pipeline_result,
            raw_text=pipeline_result.get("raw_text_used", ""),
            category=category,
            primary_file={
                "file_id": str(upload.pk),  # use upload PK as file_id
                "file_name": upload.file_name,
                "mime_type": "",
            },
            comparison_context=comparison_context,
            filename_meta={},
        )

        if candidate is None:
            raise ValueError("Failed to create candidate from extraction")

        # Ensure org ownership (save_pipeline_result doesn't set this)
        if not candidate.owned_by_id:
            candidate.owned_by = upload.organization
            candidate.save(update_fields=["owned_by", "updated_at"])

        # Update upload record
        upload.candidate = candidate
        upload.save(update_fields=["candidate", "updated_at"])
        transition_status(upload, ResumeUpload.Status.LINKED)

        # Create Contact for project search tab visibility
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

---

## Phase 3: Views + URLs (Stage 1 — Manual Upload)

### Step 3.1: Resume upload views

**File:** `projects/views.py`

All views enforce org authorization: `project.organization == request.user.membership.organization`.

```python
import uuid
from django.http import HttpResponseBadRequest, JsonResponse
from projects.services.resume.uploader import (
    create_upload, process_pending_upload, FileValidationError, validate_file,
)
from projects.services.resume.linker import link_resume_to_candidate
from projects.services.resume.transitions import transition_status


@login_required
def resume_upload(request, pk):
    """POST: Upload resume files → create ResumeUpload(pending) per file."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if request.method != "POST":
        return HttpResponseBadRequest()

    batch_id = uuid.uuid4()
    uploads = []
    errors = []

    for f in request.FILES.getlist("files"):
        try:
            upload = create_upload(
                file=f,
                project=project,
                organization=org,
                user=request.user,
                upload_batch=batch_id,
            )
            uploads.append(upload)
        except FileValidationError as e:
            errors.append({"file": f.name, "error": str(e)})

    return render(request, "projects/partials/resume_status.html", {
        "uploads": uploads,
        "errors": errors,
        "batch_id": str(batch_id),
        "project": project,
    })


@login_required
def resume_process_pending(request, pk):
    """POST: Process all pending uploads for batch. Runs extraction synchronously."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    batch_id = request.POST.get("batch_id")
    if not batch_id:
        return HttpResponseBadRequest("batch_id required")

    pending = ResumeUpload.objects.filter(
        project=project,
        upload_batch=batch_id,
        status=ResumeUpload.Status.PENDING,
    )
    for upload in pending:
        process_pending_upload(upload)

    # Return updated status
    uploads = ResumeUpload.objects.filter(
        project=project,
        upload_batch=batch_id,
    )
    return render(request, "projects/partials/resume_status.html", {
        "uploads": uploads,
        "project": project,
    })


@login_required
def resume_upload_status(request, pk):
    """GET: HTMX polling endpoint for upload status."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    batch_id = request.GET.get("batch")
    uploads = ResumeUpload.objects.filter(
        project=project,
        created_by=request.user,
    )
    if batch_id:
        uploads = uploads.filter(upload_batch=batch_id)

    return render(request, "projects/partials/resume_status.html", {
        "uploads": uploads,
        "project": project,
    })


@login_required
def resume_link_candidate(request, pk, resume_pk):
    """POST: Link extracted resume to candidate."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    upload = get_object_or_404(
        ResumeUpload.objects.filter(project=project), pk=resume_pk,
    )
    force_new = request.POST.get("force_new") == "true"

    try:
        link_resume_to_candidate(upload, user=request.user, force_new=force_new)
    except ValueError as e:
        return HttpResponseBadRequest(str(e))

    # Return updated status row
    return render(request, "projects/partials/resume_status.html", {
        "uploads": [upload],
        "project": project,
    })


@login_required
def resume_discard(request, pk, resume_pk):
    """POST: Discard resume upload + delete physical file."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    upload = get_object_or_404(
        ResumeUpload.objects.filter(project=project), pk=resume_pk,
    )

    transition_status(upload, ResumeUpload.Status.DISCARDED)
    if upload.file:
        upload.file.delete(save=False)

    return render(request, "projects/partials/resume_status.html", {
        "uploads": [upload],
        "project": project,
    })


@login_required
def resume_retry(request, pk, resume_pk):
    """POST: Retry failed extraction (max 3 retries)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    upload = get_object_or_404(
        ResumeUpload.objects.filter(project=project), pk=resume_pk,
    )

    if upload.retry_count >= 3:
        return HttpResponseBadRequest("재시도 횟수를 초과했습니다.")

    upload.retry_count += 1
    upload.save(update_fields=["retry_count", "updated_at"])
    transition_status(upload, ResumeUpload.Status.PENDING)
    process_pending_upload(upload)

    return render(request, "projects/partials/resume_status.html", {
        "uploads": [upload],
        "project": project,
    })
```

### Step 3.2: Unassigned resumes views (for orphaned email uploads)

**File:** `projects/views.py`

```python
@login_required
def resume_unassigned(request):
    """GET: Org-scoped list of unassigned resume uploads (project=null)."""
    org = _get_org(request)
    uploads = ResumeUpload.objects.filter(
        organization=org,
        project__isnull=True,
    ).exclude(status=ResumeUpload.Status.DISCARDED)

    return render(request, "projects/resume_unassigned.html", {
        "uploads": uploads,
    })


@login_required
def resume_assign_project(request, resume_pk, project_pk):
    """POST: Assign an unassigned resume upload to a project."""
    org = _get_org(request)
    upload = get_object_or_404(
        ResumeUpload.objects.filter(organization=org, project__isnull=True),
        pk=resume_pk,
    )
    project = get_object_or_404(Project, pk=project_pk, organization=org)

    upload.project = project
    upload.save(update_fields=["project", "updated_at"])

    # Redirect back to unassigned list or project detail
    ...
```

### Step 3.3: URLs

**File:** `projects/urls.py`

```python
# P18: Resume upload (project-scoped)
path("<uuid:pk>/resumes/upload/", views.resume_upload, name="resume_upload"),
path("<uuid:pk>/resumes/process/", views.resume_process_pending, name="resume_process_pending"),
path("<uuid:pk>/resumes/status/", views.resume_upload_status, name="resume_upload_status"),
path("<uuid:pk>/resumes/<uuid:resume_pk>/link/", views.resume_link_candidate, name="resume_link_candidate"),
path("<uuid:pk>/resumes/<uuid:resume_pk>/discard/", views.resume_discard, name="resume_discard"),
path("<uuid:pk>/resumes/<uuid:resume_pk>/retry/", views.resume_retry, name="resume_retry"),

# P18: Unassigned resumes (org-scoped)
path("resumes/unassigned/", views.resume_unassigned, name="resume_unassigned"),
path("resumes/<uuid:resume_pk>/assign/<uuid:project_pk>/", views.resume_assign_project, name="resume_assign_project"),
```

---

## Phase 4: Frontend (Stage 1)

### Step 4.1: Upload template

**File:** `projects/templates/projects/partials/resume_upload.html`

Drag & drop zone with file input fallback. Accepts PDF, DOCX, DOC.
On file selection:
1. POST to `/projects/<pk>/resumes/upload/` with FormData (multiple files)
2. Response includes batch_id and initial status
3. Immediately POST to `/projects/<pk>/resumes/process/` with batch_id
4. Start HTMX polling on status URL

### Step 4.2: Status template

**File:** `projects/templates/projects/partials/resume_status.html`

Lists ResumeUpload records for the batch with appropriate status indicators:
- pending/extracting: spinner + "추출중..."
- extracted: [연결] [폐기] buttons
- duplicate: warning + [연결(병합)] [새로 생성] [폐기] buttons
- failed: error message + [재시도] button (if retry_count < 3)
- linked: success with candidate name
- discarded: strikethrough

HTMX attributes: `hx-get="/projects/<pk>/resumes/status/?batch=<id>"` `hx-trigger="every 2s"` `hx-swap="innerHTML"`.
Stop polling when all uploads are in terminal state.

### Step 4.3: JavaScript

**File:** `static/js/resume-upload.js`

```javascript
// 1. dragover/drop event handling on drop zone
// 2. File input change handler
// 3. POST /upload/ with FormData (files)
// 4. Extract batch_id from response
// 5. POST /process/ with batch_id (let HTMX polling handle status)
// 6. HTMX polling starts automatically via template attributes
```

### Step 4.4: Integrate into search tab

**File:** `projects/templates/projects/partials/tab_search.html`

Add [이력서 업로드] toggle button and upload section.

**ALSO:** Add "업로드된 이력서" section showing ResumeUpload records for this project
(extracted/linked/duplicate status), separate from JD matching results.
This ensures linked candidates are visible even when they don't match JD criteria.

### Step 4.5: Unassigned resumes page

**File:** `projects/templates/projects/resume_unassigned.html`

Org-scoped list of project-null uploads with project assignment dropdown.

---

## Phase 5: Gmail API Integration (Stage 2)

### Step 5.1: Gmail client with error handling

**File:** `projects/services/email/gmail_client.py`

```python
"""Gmail API wrapper with auth, refresh, message/attachment handling, and error recovery."""
import json
import logging
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
                logger.error("Gmail token refresh failed for user %s: %s",
                             self.config.user_id, e)
                # Deactivate config — user must reconnect
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
                # history_id expired — fallback to search
                logger.warning("History ID expired for user %s, falling back to search",
                               self.config.user_id)
                return self._poll_via_search()
            elif e.resp.status == 401:
                self.config.is_active = False
                self.config.save(update_fields=["is_active", "updated_at"])
                raise
            elif e.resp.status == 429:
                return self._retry_with_backoff(self._poll_via_history)
            elif e.resp.status >= 500:
                logger.error("Gmail server error for user %s: %s",
                             self.config.user_id, e)
                return []  # skip, retry next run
            else:
                raise

    def _poll_via_history(self) -> list[dict]:
        """Incremental poll via history API."""
        # ... history.list(userId="me", startHistoryId=...) ...
        # Update last_history_id from response
        ...

    def _poll_via_search(self) -> list[dict]:
        """Full search fallback when history is unavailable."""
        # Use last_checked_at to search: after:{epoch}
        # Return message list
        ...

    def _retry_with_backoff(self, fn, max_retries=MAX_RETRIES):
        """Exponential backoff for rate-limited requests."""
        for attempt in range(max_retries):
            try:
                return fn()
            except HttpError as e:
                if e.resp.status == 429 and attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning("Rate limited, waiting %ds", wait)
                    time.sleep(wait)
                else:
                    raise
        return []

    def get_resume_attachments(self, message_id: str) -> list[dict]:
        """Get resume attachments from a message. Filters by type and size."""
        # ... Get message parts, filter by filename extension and size ...
        # Return [{"id": attachment_id, "filename": ..., "size": ...}]
        ...

    def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download attachment content with timeout."""
        # ... attachments.get(userId="me", messageId=..., id=...)
        # ... base64 decode data
        ...
```

### Step 5.2: Email monitor service

**File:** `projects/services/email/monitor.py`

```python
"""Email monitoring: poll -> filter -> create ResumeUpload -> process."""
import logging
import os
import re
import tempfile

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import EmailMonitorConfig
from projects.models import Project, ResumeUpload
from projects.services.email.gmail_client import GmailClient
from projects.services.resume.uploader import process_pending_upload

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

        # Project matching via [REF-{uuid}] in subject (org-scoped)
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
                # Duplicate: already imported this attachment
                logger.debug("Duplicate attachment skipped: msg=%s att=%s",
                             msg["id"], att["id"])
                continue
            except Exception:
                logger.exception("Failed to process attachment %s from message %s",
                                 att.get("id"), msg["id"])
                continue

    # Update checkpoint
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
    *, config, client, org, msg, att, subject, sender, project,
) -> ResumeUpload:
    """Download attachment and create ResumeUpload. Raises IntegrityError on duplicate."""
    data = client.download_attachment(msg["id"], att["id"])

    with tempfile.NamedTemporaryFile(
        suffix=os.path.splitext(att["filename"])[1],
        delete=False,
    ) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    from django.core.files import File

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
        upload.save()  # IntegrityError if duplicate

    os.unlink(tmp_path)
    return upload


def _get_file_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return {
        ".pdf": ResumeUpload.FileType.PDF,
        ".docx": ResumeUpload.FileType.DOCX,
        ".doc": ResumeUpload.FileType.DOC,
    }.get(ext, ResumeUpload.FileType.PDF)
```

### Step 5.3: Management commands

**File:** `projects/management/commands/check_email_resumes.py`

```python
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
        # select_for_update(skip_locked=True) prevents concurrent cron overlap
        with transaction.atomic():
            configs = (
                EmailMonitorConfig.objects
                .filter(is_active=True)
                .select_for_update(skip_locked=True)
            )
            for config in configs:
                try:
                    count = process_email_config(config)
                    if count:
                        self.stdout.write(
                            f"User {config.user}: {count} new uploads"
                        )
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
                # Best-effort telegram notification
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
        binding = TelegramBinding.objects.filter(
            user=user, is_active=True
        ).first()
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
```

**File:** `projects/management/commands/cleanup_failed_uploads.py`

```python
"""Clean up failed resume uploads older than 30 days."""
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
        self.stdout.write(
            self.style.SUCCESS(f"Cleaned up {count} failed uploads")
        )
```

### Step 5.4: Gmail OAuth views

**File:** `accounts/views.py`

```python
from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse

@login_required
def email_connect(request):
    """Start Gmail OAuth flow with offline access."""
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
    """Handle Gmail OAuth callback → create/update EmailMonitorConfig."""
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_OAUTH_SECRETS_FILE,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        redirect_uri=request.build_absolute_uri(reverse("accounts:email_callback")),
        state=request.session.get("gmail_oauth_state"),
    )
    flow.fetch_token(authorization_response=request.build_absolute_uri())

    credentials = flow.credentials
    creds_dict = json.loads(credentials.to_json())

    config, _created = EmailMonitorConfig.objects.get_or_create(
        user=request.user,
        defaults={"gmail_credentials": b""},  # placeholder
    )
    config.set_credentials(creds_dict)
    config.is_active = True
    config.save()

    return redirect(reverse("accounts:email_settings"))


@login_required
def email_settings(request):
    """Gmail monitoring settings page."""
    config = EmailMonitorConfig.objects.filter(user=request.user).first()

    if request.method == "POST" and config:
        # Update filter settings
        config.filter_labels = request.POST.getlist("filter_labels")
        config.filter_from = [
            e.strip() for e in request.POST.get("filter_from", "").split(",") if e.strip()
        ]
        config.is_active = request.POST.get("is_active") == "on"
        config.save(update_fields=[
            "filter_labels", "filter_from", "is_active", "updated_at"
        ])

    return render(request, "accounts/email_settings.html", {
        "config": config,
    })


@login_required
def email_disconnect(request):
    """Disconnect Gmail: revoke tokens + deactivate. Preserve imported resumes."""
    config = EmailMonitorConfig.objects.filter(user=request.user).first()
    if config:
        # Attempt to revoke token
        try:
            import httpx
            creds = config.get_credentials()
            token = creds.get("token", "")
            if token:
                httpx.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": token},
                    timeout=10,
                )
        except Exception:
            pass  # Best-effort revocation

        config.delete()

    return redirect(reverse("accounts:email_settings"))
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

Connection status, filter configuration, disconnect button.

---

## Phase 6: Tests

### Step 6.1: Model + crypto tests

**File:** `tests/test_p18_models.py`

- ResumeUpload creation with all fields
- ResumeUpload unique constraint (email dedup)
- EmailMonitorConfig credential encryption roundtrip
- BaseModel inheritance (UUID PK, timestamps)
- State transition validation (valid + invalid)

### Step 6.2: Service tests

**File:** `tests/test_p18_uploader.py`

- `validate_file()`: valid PDF/DOCX/DOC accepted
- `validate_file()`: oversized file rejected (>20MB)
- `validate_file()`: wrong extension rejected
- `validate_file()`: wrong MIME type rejected
- `create_upload()`: creates ResumeUpload(pending)
- `process_pending_upload()`: mock extraction → status=extracted
- `process_pending_upload()`: extraction failure → status=failed
- `process_pending_upload()`: duplicate detected → extracted then duplicate (two-step)

**File:** `tests/test_p18_linker.py`

- `link_resume_to_candidate()`: new candidate created with owned_by set
- `link_resume_to_candidate()`: existing candidate matched (via org-scoped identity)
- `link_resume_to_candidate()`: Contact created for project
- `link_resume_to_candidate()`: force_new=True creates new even with match
- `link_resume_to_candidate()`: invalid status raises ValueError
- `link_resume_to_candidate()`: atomic — concurrent link doesn't create duplicates

**File:** `tests/test_p18_identity.py`

- Cross-org collision: org A candidate with same email, org B upload → no match
- Same org match: email match within org → returns candidate
- Phone normalization match within org
- No name-based matching (policy enforcement)

### Step 6.3: View tests

**File:** `tests/test_p18_views.py`

- Upload POST with valid file → 200 + ResumeUpload(pending) created
- Upload POST with oversized file → error message
- Upload POST with wrong type → error message
- Process POST → pending uploads processed
- Status GET scoped to user + project + batch
- Link POST → candidate created + Contact created + status=linked
- Discard POST → file deleted + status=discarded
- Retry POST → retry_count incremented + reprocessed
- Retry POST with retry_count >= 3 → 400 error
- **Authorization: wrong org → 403**
- **Unassigned resumes: org-scoped list of project=null uploads**
- **Assign to project: updates upload.project**

### Step 6.4: Gmail integration tests

**File:** `tests/test_p18_email.py`

- `check_email_resumes` command with mocked Gmail API
- Email dedup: `IntegrityError` caught and skipped (concurrent dedup)
- History ID fallback: 404 → messages.list called
- Token refresh on expired access token → credentials updated
- Refresh failure → `is_active=False`
- `select_for_update(skip_locked=True)` concurrency: second cron skips locked
- Rate limit (429) → exponential backoff
- Server error (5xx) → skip and continue
- Oversized attachment → skip with log
- Project matching: `[REF-{uuid}]` → correct project
- Project matching: no match → project=null
- **Best-effort telegram notification: binding exists → sent, no binding → skipped, error → logged**

---

## Implementation Order Summary

| Phase | Files | Depends On |
|-------|-------|-----------|
| 1. Foundation | models, migrations, admin | -- |
| 2. Core Services | crypto, transitions, identity, uploader, linker | Phase 1 |
| 3. Views + URLs | views.py, urls.py (resume + unassigned) | Phase 2 |
| 4. Frontend | templates, JS, tab integration | Phase 3 |
| 5. Gmail Integration | gmail_client, monitor, commands, OAuth views, URLs, template | Phase 2 |
| 6. Tests | all test files | Phase 1-5 |

**Total:** ~22 new files + modifications to ~8 existing files.

**New files:**
- `projects/services/resume/__init__.py`
- `projects/services/resume/transitions.py`
- `projects/services/resume/identity.py`
- `projects/services/resume/uploader.py`
- `projects/services/resume/linker.py`
- `projects/services/email/__init__.py`
- `projects/services/email/crypto.py`
- `projects/services/email/gmail_client.py`
- `projects/services/email/monitor.py`
- `projects/management/commands/check_email_resumes.py`
- `projects/management/commands/cleanup_failed_uploads.py`
- `static/js/resume-upload.js`
- `projects/templates/projects/partials/resume_upload.html`
- `projects/templates/projects/partials/resume_status.html`
- `projects/templates/projects/resume_unassigned.html`
- `accounts/templates/accounts/email_settings.html`
- `tests/test_p18_models.py`
- `tests/test_p18_uploader.py`
- `tests/test_p18_linker.py`
- `tests/test_p18_identity.py`
- `tests/test_p18_views.py`
- `tests/test_p18_email.py`

**Modified files:**
- `projects/models.py` — add ResumeUpload
- `accounts/models.py` — add EmailMonitorConfig
- `projects/views.py` — add resume views
- `projects/urls.py` — add resume URLs
- `accounts/views.py` — add email OAuth views
- `accounts/urls.py` — add email URLs
- `projects/admin.py` — register ResumeUpload
- `accounts/admin.py` — register EmailMonitorConfig
- `projects/templates/projects/partials/tab_search.html` — add upload section
- `pyproject.toml` — add cryptography

<!-- forge:p18-email-resume-processing:구현담금질:complete:2026-04-10T16:00:00Z -->
