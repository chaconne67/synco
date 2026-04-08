from django.db import models

from common.mixins import BaseModel


class Client(BaseModel):
    """고객사 (의뢰 기업)."""

    class Size(models.TextChoices):
        LARGE = "대기업", "대기업"
        MID = "중견", "중견"
        SMALL = "중소", "중소"
        FOREIGN = "외국계", "외국계"
        STARTUP = "스타트업", "스타트업"

    name = models.CharField(max_length=200)
    industry = models.CharField(max_length=100, blank=True)
    size = models.CharField(max_length=20, choices=Size.choices, blank=True)
    region = models.CharField(max_length=100, blank=True)
    contact_persons = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="clients",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class Contract(BaseModel):
    """고객사 계약 이력."""

    class Status(models.TextChoices):
        NEGOTIATING = "협의중", "협의중"
        ACTIVE = "체결", "체결"
        EXPIRED = "만료", "만료"
        TERMINATED = "해지", "해지"

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="contracts",
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    terms = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEGOTIATING,
    )

    class Meta:
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return f"{self.client.name} ({self.start_date})"


class UniversityTier(BaseModel):
    """대학 랭킹 마스터 데이터."""

    class Tier(models.TextChoices):
        S = "S", "S"
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"
        D = "D", "D"
        E = "E", "E"
        F = "F", "F"
        OVERSEAS_TOP = "해외최상위", "해외최상위"
        OVERSEAS_HIGH = "해외상위", "해외상위"
        OVERSEAS_GOOD = "해외우수", "해외우수"

    name = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200, blank=True)
    country = models.CharField(max_length=10, default="KR")
    tier = models.CharField(max_length=20, choices=Tier.choices)
    ranking = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["tier", "ranking"]

    def __str__(self) -> str:
        return f"{self.name} ({self.tier})"


class CompanyProfile(BaseModel):
    """기업 분류 DB."""

    name = models.CharField(max_length=200)
    industry = models.CharField(max_length=100, blank=True)
    size_category = models.CharField(max_length=50, blank=True)
    revenue_range = models.CharField(max_length=50, blank=True)
    preference_tier = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class PreferredCert(BaseModel):
    """선호 자격증 마스터."""

    class Category(models.TextChoices):
        ACCOUNTING = "회계", "회계"
        LAW = "법률", "법률"
        TECH = "기술", "기술"
        LANGUAGE = "어학", "어학"
        OTHER = "기타", "기타"

    name = models.CharField(max_length=200, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.category})"
