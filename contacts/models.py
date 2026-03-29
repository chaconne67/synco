from django.conf import settings
from django.db import models

from common.mixins import BaseModel


class Contact(BaseModel):
    fc = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    ceo = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_profiles",
    )
    name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20, blank=True)
    company_name = models.CharField(max_length=100, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=50, blank=True)
    revenue_range = models.CharField(max_length=50, blank=True)
    employee_count = models.IntegerField(null=True, blank=True)
    memo = models.TextField(blank=True)
    last_interaction_at = models.DateTimeField(null=True, blank=True)

    # Relationship scoring
    relationship_score = models.FloatField(
        null=True, blank=True, help_text="0-100 가중평균 점수"
    )
    relationship_tier = models.CharField(
        max_length=10,
        blank=True,
        choices=[
            ("gold", "Gold Star"),
            ("green", "Green"),
            ("yellow", "Yellow"),
            ("red", "Red"),
            ("gray", "Gray"),
        ],
    )
    business_urgency_score = models.FloatField(
        null=True, blank=True, help_text="업무 긴급도 0-100"
    )
    closeness_score = models.FloatField(null=True, blank=True, help_text="친밀도 0-100")
    score_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "contacts"
        ordering = ["-last_interaction_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["fc", "phone"],
                name="unique_fc_contact_phone",
                condition=models.Q(phone__gt=""),
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.company_name})"

    @property
    def days_since_contact(self):
        if not self.last_interaction_at:
            return None
        from django.utils import timezone

        return (timezone.now() - self.last_interaction_at).days

    @property
    def last_sentiment(self):
        """Most recent interaction sentiment."""
        latest = (
            self.interactions.exclude(sentiment="")
            .values_list("sentiment", flat=True)
            .first()
        )
        return latest  # 'positive', 'neutral', 'negative', or None

    @property
    def tier_emoji(self):
        return {
            "gold": "⭐",
            "green": "🟢",
            "yellow": "🟡",
            "red": "🔴",
            "gray": "⚪",
        }.get(self.relationship_tier, "⚪")

    @property
    def tier_label(self):
        return {
            "gold": "골드",
            "green": "양호",
            "yellow": "주의",
            "red": "위험",
            "gray": "미분석",
        }.get(self.relationship_tier, "미분석")

    @property
    def health_level(self):
        """Relationship health. Uses relationship_tier if available, else time-decay fallback."""
        if self.relationship_tier:
            return {
                "gold": "good",
                "green": "good",
                "yellow": "caution",
                "red": "risk",
                "gray": "unknown",
            }.get(self.relationship_tier, "unknown")

        days = self.days_since_contact
        sentiment = self.last_sentiment

        if days is None:
            return "unknown"
        if sentiment == "negative":
            return "risk"
        if sentiment == "positive":
            if days < 30:
                return "good"
            if days < 90:
                return "caution"
            return "risk"
        if days < 30:
            return "good"
        if days < 90:
            return "caution"
        return "risk"

    @property
    def health_label(self):
        if self.relationship_tier:
            return self.tier_label
        level = self.health_level
        if level == "unknown":
            return "미접촉"
        if level == "good":
            return "순항"
        if level == "caution":
            return "주의"
        return "위험"

    @property
    def health_detail(self):
        """Contextual description for the health status."""
        level = self.health_level
        days = self.days_since_contact
        sentiment = self.last_sentiment

        if level == "unknown":
            return "아직 접점 기록이 없습니다"

        if level == "risk" and sentiment == "negative":
            return "최근 반응이 부정적이었습니다"
        if level == "risk":
            months = days // 30
            return f"좋은 관계였는데 {months}개월째 연락이 없습니다"
        if level == "caution":
            months = days // 30
            return f"접촉한 지 {months}개월이 지났습니다"

        if days == 0:
            return "오늘 접촉"
        return f"{days}일 전 접촉"


class Task(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "할 일"
        WAITING = "waiting", "대기"
        DONE = "done", "완료"

    class Source(models.TextChoices):
        MANUAL = "manual", "직접 입력"
        AI_EXTRACTED = "ai_extracted", "AI 추출"

    fc = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    contact = models.ForeignKey(
        "Contact",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tasks",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    source = models.CharField(
        max_length=15,
        choices=Source.choices,
        default=Source.MANUAL,
    )
    source_interactions = models.ManyToManyField(
        "Interaction",
        blank=True,
        related_name="detected_tasks",
    )

    class Meta:
        db_table = "tasks"
        ordering = ["status", "due_date", "-created_at"]

    def __str__(self):
        return self.title


class Interaction(BaseModel):
    class Type(models.TextChoices):
        CALL = "call", "통화"
        MEETING = "meeting", "미팅"
        MESSAGE = "message", "메시지"
        MEMO = "memo", "메모"

    class Sentiment(models.TextChoices):
        POSITIVE = "positive", "긍정"
        NEUTRAL = "neutral", "보통"
        NEGATIVE = "negative", "부정"

    fc = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name="interactions",
    )
    meeting = models.ForeignKey(
        "meetings.Meeting",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    import_batch = models.ForeignKey(
        "intelligence.ImportBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions",
    )
    type = models.CharField(max_length=10, choices=Type.choices)
    summary = models.TextField()
    sentiment = models.CharField(
        max_length=10,
        choices=Sentiment.choices,
        blank=True,
    )
    task_checked = models.BooleanField(default=False)

    class Meta:
        db_table = "interactions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_type_display()} - {self.contact.name}"
