from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import EmailMonitorConfig, InviteCode, Membership, Organization, TelegramBinding, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    pass


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "plan", "db_share_enabled")
    list_filter = ("plan", "db_share_enabled")
    search_fields = ("name",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "status")
    list_filter = ("role", "status")
    search_fields = ("user__username", "organization__name")


@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "organization", "role", "used_count", "max_uses", "is_active", "expires_at")
    list_filter = ("role", "is_active", "organization")
    search_fields = ("code", "organization__name")
    readonly_fields = ("code", "used_count")


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
