import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        FC = "fc", "FC (설계사)"
        CEO = "ceo", "CEO (대표)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kakao_id = models.BigIntegerField(unique=True, null=True, blank=True)
    role = models.CharField(max_length=3, choices=Role.choices, blank=True)
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
