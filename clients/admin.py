from django.contrib import admin

from .models import Client, CompanyProfile, Contract, PreferredCert, UniversityTier


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "industry", "size", "region")
    list_filter = ("size",)
    search_fields = ("name", "industry", "region")


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("client", "start_date", "end_date", "status")
    list_filter = ("status",)
    search_fields = ("client__name",)


@admin.register(UniversityTier)
class UniversityTierAdmin(admin.ModelAdmin):
    list_display = ("name", "name_en", "country", "tier", "ranking")
    list_filter = ("tier", "country")
    search_fields = ("name", "name_en")


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "name_en", "industry", "size_category", "listed", "region")
    list_filter = ("size_category", "listed")
    search_fields = ("name", "name_en", "industry")


@admin.register(PreferredCert)
class PreferredCertAdmin(admin.ModelAdmin):
    list_display = ("name", "full_name", "category", "level")
    list_filter = ("category", "level")
    search_fields = ("name", "full_name")
