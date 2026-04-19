from django.db import models

from common.mixins import BaseModel


class IndustryCategory(models.TextChoices):
    BIO_PHARMA     = "바이오/제약",       "바이오 / 제약"
    HEALTHCARE     = "헬스케어/의료기기",  "헬스케어 / 의료기기"
    IT_SW          = "IT/SW",           "IT / SW"
    MATERIAL_PARTS = "소재/부품",        "소재 / 부품"
    FINANCE        = "금융/캐피탈",       "금융 / 캐피탈"
    CONSUMER       = "소비재/패션",       "소비재 / 패션"
    ENV_UTILITY    = "환경/유틸리티",     "환경 / 유틸리티"
    MOBILITY       = "모빌리티/제조",     "모빌리티 / 제조"
    MEDIA_ENTER    = "미디어/엔터",       "미디어 / 엔터"
    CONSTRUCTION   = "건설/부동산",       "건설 / 부동산"
    ETC            = "기타",             "기타"


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
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to="clients/logos/", blank=True, null=True)
    description = models.TextField(blank=True)
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
        SKY = "SKY", "SKY"
        SSG = "SSG", "서성한"
        JKOS = "JKOS", "중경외시"
        KDH = "KDH", "건동홍"
        INSEOUL = "INSEOUL", "인서울 기타"
        SCIENCE_ELITE = "SCIENCE_ELITE", "이공계 명문"
        REGIONAL = "REGIONAL", "지방 거점 국립"
        OVERSEAS_TOP = "OVERSEAS_TOP", "해외 최상위"
        OVERSEAS_HIGH = "OVERSEAS_HIGH", "해외 상위"
        OVERSEAS_GOOD = "OVERSEAS_GOOD", "해외 우수"

    name = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200, blank=True)
    country = models.CharField(max_length=10, default="KR")
    tier = models.CharField(max_length=20, choices=Tier.choices)
    ranking = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["tier", "ranking"]
        unique_together = [("name", "country")]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_tier_display()})"


class CompanyProfile(BaseModel):
    """기업 분류 DB."""

    class SizeCategory(models.TextChoices):
        LARGE = "대기업", "대기업"
        MID = "중견", "중견"
        SMALL = "중소", "중소"
        FOREIGN = "외국계", "외국계"
        STARTUP = "스타트업", "스타트업"

    class Listed(models.TextChoices):
        KOSPI = "KOSPI", "KOSPI"
        KOSDAQ = "KOSDAQ", "KOSDAQ"
        UNLISTED = "비상장", "비상장"
        OVERSEAS = "해외상장", "해외상장"

    name = models.CharField(max_length=200, unique=True)
    name_en = models.CharField(max_length=200, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    size_category = models.CharField(
        max_length=50, choices=SizeCategory.choices, blank=True
    )
    revenue_range = models.CharField(max_length=50, blank=True)
    employee_count_range = models.CharField(max_length=50, blank=True)
    listed = models.CharField(max_length=20, choices=Listed.choices, blank=True)
    region = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class PreferredCert(BaseModel):
    """선호 자격증 마스터."""

    class Category(models.TextChoices):
        ACCOUNTING = "회계/재무", "회계/재무"
        LAW = "법률", "법률"
        TECH = "기술/엔지니어링", "기술/엔지니어링"
        IT = "IT", "IT"
        MEDICAL = "의료/제약", "의료/제약"
        TRADE = "무역/물류", "무역/물류"
        CONSTRUCTION = "건설/부동산", "건설/부동산"
        FOOD_ENV = "식품/환경", "식품/환경"
        LANGUAGE = "어학", "어학"
        SAFETY = "안전/품질", "안전/품질"
        OTHER = "기타", "기타"

    class Level(models.TextChoices):
        HIGH = "상", "상"
        MID = "중", "중"
        LOW = "하", "하"

    name = models.CharField(max_length=200, unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=30, choices=Category.choices)
    level = models.CharField(max_length=10, choices=Level.choices, blank=True)
    aliases = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_category_display()})"
