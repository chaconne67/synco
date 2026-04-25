from django.contrib import admin

from .models import GeminiBatchItem, GeminiBatchJob, ResumeExtractionState


@admin.register(ResumeExtractionState)
class ResumeExtractionStateAdmin(admin.ModelAdmin):
    list_display = (
        "resume",
        "status",
        "attempt_count",
        "provider",
        "pipeline",
        "last_attempted_at",
        "updated_at",
    )
    search_fields = (
        "resume__file_name",
        "resume__drive_file_id",
        "last_error",
    )
    list_filter = ("status", "provider", "pipeline")


@admin.register(GeminiBatchJob)
class GeminiBatchJobAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "status",
        "model_name",
        "total_requests",
        "successful_requests",
        "failed_requests",
        "created_at",
    )
    search_fields = ("display_name", "gemini_batch_name", "gemini_file_name")
    list_filter = ("status", "model_name", "source")


@admin.register(GeminiBatchItem)
class GeminiBatchItemAdmin(admin.ModelAdmin):
    list_display = (
        "file_name",
        "category_name",
        "status",
        "request_key",
        "candidate",
        "created_at",
    )
    search_fields = ("file_name", "drive_file_id", "request_key")
    list_filter = ("status", "category_name")
