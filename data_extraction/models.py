"""data_extraction models — batch job tracking."""

from django.db import models

from common.mixins import BaseModel


class ResumeExtractionState(BaseModel):
    """Per-resume extraction state and attempt tracking.

    Resume remains the file/version record. This model tracks extraction lifecycle
    so batch/resume import can distinguish discovered, attempted, completed,
    failed, and skipped files without adding more operational fields to Resume.
    """

    class Status(models.TextChoices):
        DISCOVERED = "discovered", "Discovered"
        DOWNLOADING = "downloading", "Downloading"
        DOWNLOADED = "downloaded", "Downloaded"
        TEXT_EXTRACTED = "text_extracted", "Text extracted"
        EXTRACTING = "extracting", "Extracting"
        STRUCTURED = "structured", "Structured"
        TEXT_ONLY = "text_only", "Text only"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    resume = models.OneToOneField(
        "candidates.Resume",
        on_delete=models.CASCADE,
        related_name="extraction_state",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DISCOVERED,
    )
    discovered_at = models.DateTimeField(null=True, blank=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)
    text_extracted_at = models.DateTimeField(null=True, blank=True)
    extraction_started_at = models.DateTimeField(null=True, blank=True)
    extraction_completed_at = models.DateTimeField(null=True, blank=True)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    provider = models.CharField(max_length=50, blank=True)
    pipeline = models.CharField(max_length=50, blank=True)
    last_error = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "resume_extraction_states"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.resume.file_name} ({self.get_status_display()})"


class GeminiBatchJob(BaseModel):
    class Status(models.TextChoices):
        PREPARING = "preparing", "Preparing"
        PREPARED = "prepared", "Prepared"
        SUBMITTED = "submitted", "Submitted"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        INGESTED = "ingested", "Ingested"

    display_name = models.CharField(max_length=200)
    source = models.CharField(max_length=50, default="drive_resume_import")
    model_name = models.CharField(
        max_length=100,
        default="gemini-3.1-flash-lite-preview",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PREPARING,
    )
    category_filter = models.CharField(max_length=100, blank=True)
    parent_folder_id = models.CharField(max_length=100, blank=True)
    request_file_path = models.CharField(max_length=500, blank=True)
    result_file_path = models.CharField(max_length=500, blank=True)
    gemini_file_name = models.CharField(max_length=200, blank=True)
    gemini_batch_name = models.CharField(max_length=200, blank=True)
    total_requests = models.PositiveIntegerField(default=0)
    successful_requests = models.PositiveIntegerField(default=0)
    failed_requests = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "gemini_batch_jobs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.display_name} ({self.get_status_display()})"


class GeminiBatchItem(BaseModel):
    class Status(models.TextChoices):
        FAILED = "failed", "Failed"
        PREPARED = "prepared", "Prepared"
        SUBMITTED = "submitted", "Submitted"
        SUCCEEDED = "succeeded", "Succeeded"
        INGESTED = "ingested", "Ingested"

    job = models.ForeignKey(
        GeminiBatchJob,
        on_delete=models.CASCADE,
        related_name="items",
    )
    request_key = models.CharField(max_length=100)
    drive_file_id = models.CharField(max_length=100)
    file_name = models.CharField(max_length=300)
    category_name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PREPARED,
    )
    raw_text_path = models.CharField(max_length=500, blank=True)
    primary_file = models.JSONField(default=dict, blank=True)
    other_files = models.JSONField(default=list, blank=True)
    filename_meta = models.JSONField(default=dict, blank=True)
    response_json = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    candidate = models.ForeignKey(
        "candidates.Candidate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gemini_batch_items",
    )

    class Meta:
        db_table = "gemini_batch_items"
        ordering = ["created_at"]
        unique_together = [("job", "request_key")]

    def __str__(self):
        return f"{self.file_name} ({self.get_status_display()})"
