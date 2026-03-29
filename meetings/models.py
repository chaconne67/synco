from django.conf import settings
from django.db import models

from common.mixins import BaseModel


class Meeting(BaseModel):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "예정"
        COMPLETED = "completed", "완료"
        CANCELLED = "cancelled", "취소"

    fc = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="meetings",
    )
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="meetings",
    )
    title = models.CharField(max_length=200)
    scheduled_at = models.DateTimeField()
    scheduled_end_at = models.DateTimeField()
    location = models.CharField(max_length=200, blank=True)
    reminder_sent = models.BooleanField(default=False)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )

    class Meta:
        db_table = "meetings"
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"{self.title} ({self.scheduled_at:%m/%d %H:%M})"
