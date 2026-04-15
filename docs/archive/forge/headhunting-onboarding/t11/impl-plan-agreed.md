# t11: NotificationPreference 모델 추가

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자별 알림 수신 여부를 저장하는 `NotificationPreference` 모델을 추가한다.

**Design spec:** `docs/forge/headhunting-onboarding/t11/design-spec.md`

**depends_on:** 없음 (1단계 완료 기준)

> **NOTE: 레코드 생성 정책** — 기존 사용자에 대한 data migration backfill은 수행하지 않는다.
> 후속 태스크(t13)에서 모든 접근점이 `get_or_create` 패턴을 사용하므로,
> 기존 사용자도 첫 접근 시 자동으로 기본값 레코드가 생성된다 (lazy creation).

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `accounts/models.py` | 수정 | `NotificationPreference` 모델 + 상수 + `clean()` 추가 |
| `accounts/admin.py` | 수정 | Admin 등록 |
| `tests/accounts/test_notification_pref.py` | 생성 | NotificationPreference 모델 테스트 |

---

- [ ] **Step 1: Write failing test for NotificationPreference model**

```python
# tests/accounts/test_notification_pref.py
import pytest
from django.contrib import admin
from django.db import IntegrityError

from accounts.models import NotificationPreference, _default_notification_preferences

User = __import__("django.contrib.auth", fromlist=["get_user_model"]).get_user_model()


@pytest.mark.django_db
class TestNotificationPreference:
    def test_create_default_preferences(self):
        user = User.objects.create_user(username="np1", password="pass")
        pref = NotificationPreference.objects.create(user=user)
        assert pref.preferences == _default_notification_preferences()

    def test_update_preferences(self):
        user = User.objects.create_user(username="np2", password="pass")
        pref = NotificationPreference.objects.create(user=user)
        pref.preferences["contact_result"]["telegram"] = False
        pref.save()
        pref.refresh_from_db()
        assert pref.preferences["contact_result"]["telegram"] is False

    def test_one_to_one_with_user(self):
        user = User.objects.create_user(username="np3", password="pass")
        NotificationPreference.objects.create(user=user)
        with pytest.raises(IntegrityError):
            NotificationPreference.objects.create(user=user)

    def test_get_or_create_defaults(self):
        user = User.objects.create_user(username="np4", password="pass")
        pref, created = NotificationPreference.objects.get_or_create(user=user)
        assert created is True
        assert pref.preferences == _default_notification_preferences()

    def test_admin_registered(self):
        assert NotificationPreference in admin.site._registry
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_notification_pref.py -v`
Expected: FAIL — `ImportError: cannot import name 'NotificationPreference'`

- [ ] **Step 3: Add NotificationPreference model to accounts/models.py**

Add after the `EmailMonitorConfig` class at the end of the file:

```python
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
```

- [ ] **Step 4: Register in admin**

In `accounts/admin.py`, add import and admin class:

```python
from .models import NotificationPreference

@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user",)
    search_fields = ("user__username",)
```

- [ ] **Step 5: Create and run migration**

Run: `uv run python manage.py makemigrations accounts && uv run python manage.py migrate`

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/accounts/test_notification_pref.py -v`
Expected: All 5 tests PASS

- [ ] **Step 7: Commit**

```bash
git add accounts/models.py accounts/admin.py accounts/migrations/ tests/accounts/
git commit -m "feat(accounts): add NotificationPreference model"
```

<!-- forge:t11:구현담금질:complete:2026-04-12T22:30:00+09:00 -->
