from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from common.mixins import BaseModel


class ContactEmbedding(BaseModel):
    contact = models.OneToOneField(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="embedding",
    )
    vector = VectorField(dimensions=3072)
    source_text = models.TextField()
    source_hash = models.CharField(max_length=64)
    model_version = models.CharField(max_length=50, default="gemini-embedding-001")

    class Meta:
        db_table = "contact_embeddings"

    def __str__(self):
        return f"Embedding: {self.contact.name}"


class ImportBatch(BaseModel):
    fc = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="import_batches",
    )
    contact_count = models.PositiveIntegerField()
    interaction_count = models.PositiveIntegerField()
    embedding_done = models.BooleanField(default=False)
    sentiment_done = models.BooleanField(default=False)
    task_done = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        db_table = "import_batches"
        ordering = ["-created_at"]

    def __str__(self):
        return f"ImportBatch: {self.contact_count} contacts ({self.fc})"

    @property
    def is_complete(self) -> bool:
        return self.embedding_done and self.sentiment_done and self.task_done


class Brief(BaseModel):
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="briefs",
    )
    fc = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    company_analysis = models.TextField()
    action_suggestion = models.TextField()
    insights = models.JSONField(default=dict)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "briefs"
        ordering = ["-generated_at"]

    def __str__(self):
        return f"Brief: {self.contact.name} ({self.generated_at:%m/%d})"


class AnalysisJob(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        RUNNING = "running", "진행 중"
        COMPLETED = "completed", "완료"
        FAILED = "failed", "실패"

    fc = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="analysis_jobs",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    total_contacts = models.IntegerField(default=0)
    processed_contacts = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "analysis_jobs"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Analysis {self.status} ({self.processed_contacts}/{self.total_contacts})"
        )


class RelationshipAnalysis(BaseModel):
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="analyses",
    )
    fc = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    business_signals = models.JSONField(default=dict)
    relationship_signals = models.JSONField(default=dict)
    ai_summary = models.TextField(blank=True)
    extracted_tasks = models.JSONField(default=list)
    fortunate_insights = models.JSONField(default=list)

    class Meta:
        db_table = "relationship_analyses"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Analysis: {self.contact.name}"


class FortunateInsight(BaseModel):
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="fortunate_insights",
    )
    fc = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    reason = models.TextField()
    signal_type = models.CharField(max_length=30, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_dismissed = models.BooleanField(default=False)

    class Meta:
        db_table = "fortunate_insights"
        ordering = ["-created_at"]
        unique_together = [["fc", "contact"]]

    def __str__(self):
        return f"Insight: {self.contact.name} - {self.reason[:30]}"


class Match(BaseModel):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "제안"
        VIEWED = "viewed", "열람"
        ACCEPTED = "accepted", "수락"
        REJECTED = "rejected", "거절"

    contact_a = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="matches_as_a",
    )
    contact_b = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="matches_as_b",
    )
    fc = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    score = models.IntegerField()
    industry_fit = models.IntegerField()
    region_proximity = models.IntegerField()
    size_balance = models.IntegerField()
    synergy_description = models.TextField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PROPOSED,
    )

    class Meta:
        db_table = "matches"
        ordering = ["-score"]

    def __str__(self):
        return f"Match: {self.contact_a.name} <-> {self.contact_b.name} ({self.score})"
