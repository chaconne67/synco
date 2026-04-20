from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin

from .models import (
    EmailMonitorConfig,
    NotificationPreference,
    TelegramBinding,
    User,
)


@admin.register(User)
class UserAdmin(DefaultUserAdmin):
    list_display = ("username", "email", "level", "is_superuser", "date_joined")
    list_filter = ("level", "is_superuser")
    fieldsets = DefaultUserAdmin.fieldsets + (
        ("synco", {"fields": ("level", "phone")}),
    )


@admin.register(TelegramBinding)
class TelegramBindingAdmin(admin.ModelAdmin):
    list_display = ("user", "chat_id", "is_active")
    list_filter = ("is_active",)
    search_fields = ("user__username", "chat_id")


@admin.register(EmailMonitorConfig)
class EmailMonitorConfigAdmin(admin.ModelAdmin):
    list_display = ("user", "is_active", "last_checked_at")
    list_filter = ("is_active",)
    search_fields = ("user__username",)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user",)
    search_fields = ("user__username",)
