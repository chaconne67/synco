from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import (
    ActionType,
    Interview,
    Notification,
    Project,
    ProjectApproval,
    ProjectContext,
    ResumeUpload,
    Submission,
)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "client", "phase", "status", "created_by", "created_at")
    list_filter = ("phase", "status")
    search_fields = ("title", "client__name")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("action_item", "consultant", "submitted_at")
    search_fields = ("action_item__title",)


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ("action_item", "round", "type", "result", "scheduled_at")
    list_filter = ("type", "result")


@admin.register(ProjectApproval)
class ProjectApprovalAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "requested_by",
        "conflict_type",
        "conflict_score",
        "status",
        "decided_by",
        "decided_at",
    )
    list_filter = ("status", "conflict_type")


@admin.register(ProjectContext)
class ProjectContextAdmin(admin.ModelAdmin):
    list_display = ("project", "consultant", "last_step", "pending_action")
    search_fields = ("project__title",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "type", "status", "created_at")
    list_filter = ("type", "status")
    search_fields = ("title",)


@admin.register(ResumeUpload)
class ResumeUploadAdmin(admin.ModelAdmin):
    list_display = (
        "file_name",
        "project",
        "source",
        "status",
        "candidate",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "source", "file_type")
    search_fields = ("file_name", "email_from", "email_subject")
    raw_id_fields = ("candidate", "project", "created_by")


# T1.14 — ActionType admin registration
@admin.register(ActionType)
class ActionTypeAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "label_ko",
        "phase",
        "output_kind",
        "is_active",
        "is_protected",
        "sort_order",
    ]
    list_filter = ["phase", "output_kind", "is_active", "is_protected"]
    search_fields = ["code", "label_ko"]
    list_editable = ["is_active", "sort_order"]
    readonly_fields = ["is_protected"]

    def delete_model(self, request, obj):
        if obj.is_protected:
            raise ValidationError(
                f"ActionType '{obj.code}' is protected and cannot be deleted."
            )
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        protected = queryset.filter(is_protected=True)
        if protected.exists():
            codes = ", ".join(protected.values_list("code", flat=True))
            raise ValidationError(f"Cannot delete protected ActionTypes: {codes}")
        super().delete_queryset(request, queryset)
