import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from common.mixins import BaseModel


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    avatar = models.ImageField(upload_to="accounts/avatars/", blank=True)
    phone = models.CharField(max_length=20, blank=True)
    company_name = models.CharField(max_length=100, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=50, blank=True)
    revenue_range = models.CharField(max_length=50, blank=True)
    employee_count = models.IntegerField(null=True, blank=True)
    ga_id = models.CharField(max_length=100, blank=True)
    push_subscription = models.JSONField(null=True, blank=True)

    class Level(models.IntegerChoices):
        PENDING = 0, "대기"
        STAFF = 1, "직원"
        BOSS = 2, "사장"

    level = models.IntegerField(
        choices=Level.choices,
        default=Level.PENDING,
    )

    last_news_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"

    @property
    def display_name(self) -> str:
        """Korean display name: last_name + first_name, then username fallback."""
        name = f"{(self.last_name or '').strip()}{(self.first_name or '').strip()}"
        if name:
            return name
        full_name = (self.get_full_name() or "").strip()
        return full_name or self.username

    @property
    def display_initial(self) -> str:
        return self.display_name[:1].upper()


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


NOTIFICATION_TYPES = (
    "contact_result",
    "recommendation_feedback",
    "project_approval",
    "newsfeed_update",
)
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
