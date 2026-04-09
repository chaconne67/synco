import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from common.mixins import BaseModel


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kakao_id = models.BigIntegerField(unique=True, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    company_name = models.CharField(max_length=100, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=50, blank=True)
    revenue_range = models.CharField(max_length=50, blank=True)
    employee_count = models.IntegerField(null=True, blank=True)
    ga_id = models.CharField(max_length=100, blank=True)
    push_subscription = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"


class Organization(BaseModel):
    """서치펌 (멀티테넌시 단위)."""

    class Plan(models.TextChoices):
        BASIC = "basic", "Basic"
        STANDARD = "standard", "Standard"
        PREMIUM = "premium", "Premium"
        PARTNER = "partner", "Partner"

    name = models.CharField(max_length=200)
    plan = models.CharField(
        max_length=20,
        choices=Plan.choices,
        default=Plan.BASIC,
    )
    db_share_enabled = models.BooleanField(default=False)
    logo = models.FileField(upload_to="organizations/logos/", blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Membership(BaseModel):
    """Organization 소속 관계."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        CONSULTANT = "consultant", "Consultant"
        VIEWER = "viewer", "Viewer"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="membership",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CONSULTANT,
    )

    def __str__(self) -> str:
        return f"{self.user} - {self.organization} ({self.role})"


class TelegramBinding(BaseModel):
    """텔레그램 바인딩."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="telegram_binding",
    )
    chat_id = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.user} - {self.chat_id}"


class TelegramVerification(BaseModel):
    """텔레그램 인증 코드."""

    MAX_ATTEMPTS = 5

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="telegram_verifications",
    )
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    consumed = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone
        return self.consumed or self.expires_at <= timezone.now()

    @property
    def is_blocked(self) -> bool:
        return self.attempts >= self.MAX_ATTEMPTS

    def __str__(self) -> str:
        return f"{self.user} - {self.code} (expired={self.is_expired})"
