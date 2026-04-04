from django.contrib import admin

from .models import (
    Candidate,
    Career,
    Category,
    Certification,
    DiscrepancyReport,
    Education,
    ExtractionLog,
    LanguageSkill,
    Resume,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "name_ko", "candidate_count"]
    search_fields = ["name", "name_ko"]


class ResumeInline(admin.TabularInline):
    model = Resume
    extra = 0
    fields = ["file_name", "drive_file_id", "is_primary", "processing_status"]


class CareerInline(admin.TabularInline):
    model = Career
    extra = 0
    fields = ["company", "position", "start_date", "end_date", "is_current", "order"]


class EducationInline(admin.TabularInline):
    model = Education
    extra = 0
    fields = ["institution", "degree", "major", "start_year", "end_year"]


class CertificationInline(admin.TabularInline):
    model = Certification
    extra = 0
    fields = ["name", "issuer", "acquired_date"]


class LanguageSkillInline(admin.TabularInline):
    model = LanguageSkill
    extra = 0
    fields = ["language", "test_name", "score", "level"]


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "current_company",
        "current_position",
        "status",
        "validation_status",
        "primary_category",
    ]
    list_filter = ["status", "validation_status", "source"]
    search_fields = ["name", "name_en", "current_company", "email", "phone", "phone_normalized"]
    inlines = [
        ResumeInline,
        CareerInline,
        EducationInline,
        CertificationInline,
        LanguageSkillInline,
    ]
    filter_horizontal = ["categories"]


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = [
        "file_name",
        "candidate",
        "processing_status",
        "is_primary",
        "version",
    ]
    list_filter = ["processing_status", "is_primary"]
    search_fields = ["file_name", "drive_file_id"]


@admin.register(ExtractionLog)
class ExtractionLogAdmin(admin.ModelAdmin):
    list_display = [
        "candidate",
        "action",
        "field_name",
        "confidence",
        "created_at",
    ]
    list_filter = ["action"]
    search_fields = ["candidate__name", "field_name"]


@admin.register(DiscrepancyReport)
class DiscrepancyReportAdmin(admin.ModelAdmin):
    list_display = [
        "candidate",
        "report_type",
        "integrity_score",
        "created_at",
    ]
    list_filter = ["report_type"]
    search_fields = ["candidate__name", "summary"]
