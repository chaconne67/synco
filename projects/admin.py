from django.contrib import admin

from .models import (
    Contact,
    Interview,
    Notification,
    Offer,
    Project,
    ProjectApproval,
    ProjectContext,
    Submission,
)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "client", "status", "created_by", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "client__name")


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "candidate",
        "consultant",
        "channel",
        "result",
        "contacted_at",
    )
    list_filter = ("channel", "result")
    search_fields = ("project__title", "candidate__name")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("project", "candidate", "consultant", "status", "submitted_at")
    list_filter = ("status",)
    search_fields = ("project__title", "candidate__name")


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ("submission", "round", "type", "result", "scheduled_at")
    list_filter = ("type", "result")


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("submission", "salary", "position_title", "status", "start_date")
    list_filter = ("status",)


@admin.register(ProjectApproval)
class ProjectApprovalAdmin(admin.ModelAdmin):
    list_display = ("project", "requested_by", "status", "decided_by", "decided_at")
    list_filter = ("status",)


@admin.register(ProjectContext)
class ProjectContextAdmin(admin.ModelAdmin):
    list_display = ("project", "consultant", "last_step", "pending_action")
    search_fields = ("project__title",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "type", "status", "created_at")
    list_filter = ("type", "status")
    search_fields = ("title",)
