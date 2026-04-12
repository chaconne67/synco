import secrets
import string
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
    last_news_seen_at = models.DateTimeField(null=True, blank=True)
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

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PENDING = "pending", "Pending"
        REJECTED = "rejected", "Rejected"

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    def __str__(self) -> str:
        return f"{self.user} - {self.organization} ({self.role})"


class InviteCode(BaseModel):
    """초대코드 — Organization 가입용."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        CONSULTANT = "consultant", "Consultant"
        VIEWER = "viewer", "Viewer"

    code = models.CharField(max_length=20, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="invite_codes",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CONSULTANT,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_invite_codes",
    )
    max_uses = models.PositiveIntegerField(default=1)
    used_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.code} ({self.organization.name}, {self.role})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_code() -> str:
        chars = string.ascii_uppercase + string.digits
        while True:
            code = "".join(secrets.choice(chars) for _ in range(8))
            if not InviteCode.objects.filter(code=code).exists():
                return code

    @property
    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        if self.expires_at:
            from django.utils import timezone

            if self.expires_at <= timezone.now():
                return False
        return True

    def use(self) -> None:
        self.used_count += 1
        self.save(update_fields=["used_count", "updated_at"])


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


class EmailMonitorConfig(BaseModel):
    """Gmail 모니터링 설정."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="email_monitor_config",
    )
    gmail_credentials = models.BinaryField()
    is_active = models.BooleanField(default=True)
    filter_labels = models.JSONField(default=list, blank=True)
    filter_from = models.JSONField(default=list, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_history_id = models.CharField(max_length=255, blank=True)

    def __str__(self) -> str:
        return f"EmailMonitor: {self.user} (active={self.is_active})"

    def set_credentials(self, credentials_dict: dict) -> None:
        """Encrypt and store OAuth2 credentials."""
        import json

        from projects.services.email.crypto import encrypt_data

        self.gmail_credentials = encrypt_data(json.dumps(credentials_dict).encode())

    def get_credentials(self) -> dict:
        """Decrypt and return OAuth2 credentials."""
        import json

        from projects.services.email.crypto import decrypt_data

        return json.loads(decrypt_data(bytes(self.gmail_credentials)))


NOTIFICATION_TYPES = ("contact_result", "recommendation_feedback", "project_approval", "newsfeed_update")
CHANNELS = ("web", "telegram")


def _default_notification_preferences():
    return {
        "contact_result": {"web": True, "telegram": True},
        "recommendation_feedback": {"web": True, "telegram": True},
        "project_approval": {"web": True, "telegram": True},
        "newsfeed_update": {"web": True, "telegram": False},
    }


class NotificationPreference(BaseModel):
    """사용자별 알림 설정."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    preferences = models.JSONField(default=_default_notification_preferences)

    def __str__(self) -> str:
        return f"NotificationPref: {self.user}"

    def clean(self) -> None:
        super().clean()
        from django.core.exceptions import ValidationError

        if not isinstance(self.preferences, dict):
            raise ValidationError("preferences must be a dict")
        for ntype in NOTIFICATION_TYPES:
            if ntype not in self.preferences:
                raise ValidationError(f"Missing notification type: {ntype}")
            channels = self.preferences[ntype]
            if not isinstance(channels, dict):
                raise ValidationError(f"'{ntype}' must be a dict of channels")
            for ch in CHANNELS:
                if ch not in channels:
                    raise ValidationError(f"Missing channel '{ch}' for '{ntype}'")
                if not isinstance(channels[ch], bool):
                    raise ValidationError(f"'{ntype}.{ch}' must be a boolean")
