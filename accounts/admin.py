from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Membership, Organization, TelegramBinding, User


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
    list_display = ("user", "organization", "role")
    list_filter = ("role",)
    search_fields = ("user__username", "organization__name")


@admin.register(TelegramBinding)
class TelegramBindingAdmin(admin.ModelAdmin):
    list_display = ("user", "chat_id", "is_active")
    list_filter = ("is_active",)
    search_fields = ("user__username", "chat_id")
