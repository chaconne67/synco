# P15 Telegram Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Telegram bot integration for notifications, approval actions via Inline Keyboard, multi-step contact recording, text-based task queries, and automated reminders.

**Architecture:** A new `projects/telegram/` package handles bot initialization, message formatting, keyboard building, webhook auth, and callback routing. Views in `projects/views_telegram.py` expose 4 endpoints under `/telegram/`. The notification service (`projects/services/notification.py`) sends messages via the bot and manages idempotency. All business mutations delegate to existing service functions (`approval.py`, `contact.py`) — Telegram handlers are thin wrappers. Text queries reuse P14's `intent_parser` and `entity_resolver`. A management command handles reminders via host cron.

**Tech Stack:** Django 5.2, python-telegram-bot>=21.0, Django cache framework (LocMemCache), HTMX, Tailwind CSS.

**Source spec:** `docs/forge/headhunting-workflow/p15-telegram-integration/design-spec-agreed.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `projects/telegram/__init__.py` | Package init |
| `projects/telegram/bot.py` | Bot instance creation (no webhook registration) |
| `projects/telegram/auth.py` | Webhook secret validation + `verify_telegram_user_access` |
| `projects/telegram/keyboards.py` | InlineKeyboard builders (64-byte callback_data) |
| `projects/telegram/formatters.py` | Message text formatting (Markdown) |
| `projects/telegram/handlers.py` | Callback query + message dispatch (thin wrapper over services) |
| `projects/services/notification.py` | send/update/bulk notification + Telegram API calls |
| `projects/views_telegram.py` | webhook, bind, unbind, test views |
| `projects/urls_telegram.py` | URL routing for `/telegram/` |
| `projects/management/__init__.py` | Package init |
| `projects/management/commands/__init__.py` | Package init |
| `projects/management/commands/send_reminders.py` | Daily reminder generation + send |
| `projects/management/commands/setup_telegram_webhook.py` | One-time webhook URL registration |
| `accounts/templates/accounts/telegram_bind.html` | Binding settings UI |
| `tests/test_p15_telegram_models.py` | Model + migration tests |
| `tests/test_p15_telegram_auth.py` | Webhook auth + user access tests |
| `tests/test_p15_telegram_notification.py` | Notification service tests |
| `tests/test_p15_telegram_keyboards.py` | Keyboard builder tests |
| `tests/test_p15_telegram_handlers.py` | Callback handler tests |
| `tests/test_p15_telegram_views.py` | View endpoint tests |
| `tests/test_p15_telegram_reminders.py` | Reminder command tests |

### Modified Files

| File | Change |
|------|--------|
| `accounts/models.py` | Add `TelegramVerification` model, add `verified_at` to `TelegramBinding` |
| `projects/models.py` | Add `telegram_chat_id` to `Notification` |
| `main/settings.py` | Add `TELEGRAM_BOT_TOKEN`, `SITE_URL`, `TELEGRAM_WEBHOOK_SECRET`, `CACHES` |
| `main/urls.py` | Add `path("telegram/", include("projects.urls_telegram"))` |
| `pyproject.toml` | Add `python-telegram-bot>=21.0` dependency |
| `.env.example` | Add `TELEGRAM_BOT_TOKEN`, `SITE_URL`, `TELEGRAM_WEBHOOK_SECRET` |

---

## Task 1: Dependencies and Settings

**Files:**
- Modify: `pyproject.toml:7-25`
- Modify: `main/settings.py:140-236`
- Modify: `.env.example`

- [ ] **Step 1: Add python-telegram-bot to dependencies**

In `pyproject.toml`, add to the `dependencies` list:

```toml
    "python-telegram-bot>=21.0",
```

Add it after the `"pymupdf>=1.27.2.2"` line inside the dependencies array.

- [ ] **Step 2: Install the dependency**

Run: `cd /home/work/synco && uv sync`
Expected: Resolves and installs python-telegram-bot

- [ ] **Step 3: Add Telegram settings to main/settings.py**

Append after the `OPENAI_API_KEY` line (line 141):

```python
# Telegram Bot
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
SITE_URL = os.environ.get("SITE_URL", "https://synco.kr")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
```

Append after the `STORAGES` block (after line 192):

```python
# Cache (used for Telegram webhook dedup)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
```

- [ ] **Step 4: Update .env.example**

Append to `.env.example`:

```
# Telegram Bot
TELEGRAM_BOT_TOKEN=
SITE_URL=https://synco.kr
TELEGRAM_WEBHOOK_SECRET=
```

- [ ] **Step 5: Verify settings load**

Run: `cd /home/work/synco && uv run python -c "from main.settings import TELEGRAM_BOT_TOKEN, SITE_URL, TELEGRAM_WEBHOOK_SECRET; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock main/settings.py .env.example
git commit -m "feat(p15): add python-telegram-bot dependency and telegram settings"
```

---

## Task 2: Model Migrations

**Files:**
- Modify: `accounts/models.py:80-92`
- Modify: `projects/models.py:454-490`
- Create: migrations (auto-generated)
- Test: `tests/test_p15_telegram_models.py`

- [ ] **Step 1: Write model tests**

Create `tests/test_p15_telegram_models.py`:

```python
"""P15: Telegram model tests."""

import pytest
from datetime import timedelta
from django.utils import timezone

from accounts.models import Membership, Organization, TelegramBinding, TelegramVerification, User
from projects.models import Notification


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


class TestTelegramBinding:
    def test_verified_at_field_exists(self, user):
        binding = TelegramBinding.objects.create(
            user=user, chat_id="123456", is_active=True, verified_at=timezone.now()
        )
        binding.refresh_from_db()
        assert binding.verified_at is not None

    def test_verified_at_nullable(self, user):
        binding = TelegramBinding.objects.create(
            user=user, chat_id="123456", is_active=True
        )
        binding.refresh_from_db()
        assert binding.verified_at is None


class TestTelegramVerification:
    def test_create_verification(self, user):
        v = TelegramVerification.objects.create(
            user=user,
            code="123456",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        assert v.consumed is False
        assert v.attempts == 0

    def test_expired_verification(self, user):
        v = TelegramVerification.objects.create(
            user=user,
            code="123456",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        assert v.is_expired is True

    def test_valid_verification(self, user):
        v = TelegramVerification.objects.create(
            user=user,
            code="123456",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        assert v.is_expired is False

    def test_consumed_is_expired(self, user):
        v = TelegramVerification.objects.create(
            user=user,
            code="123456",
            expires_at=timezone.now() + timedelta(minutes=5),
            consumed=True,
        )
        assert v.is_expired is True

    def test_max_attempts_exceeded(self, user):
        v = TelegramVerification.objects.create(
            user=user,
            code="123456",
            expires_at=timezone.now() + timedelta(minutes=5),
            attempts=5,
        )
        assert v.is_blocked is True

    def test_str(self, user):
        v = TelegramVerification.objects.create(
            user=user,
            code="123456",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        assert "123456" in str(v)


class TestNotificationChatId:
    def test_telegram_chat_id_field(self, user):
        n = Notification.objects.create(
            recipient=user,
            type=Notification.Type.REMINDER,
            title="Test",
            body="Test body",
            telegram_chat_id="999888",
        )
        n.refresh_from_db()
        assert n.telegram_chat_id == "999888"

    def test_telegram_chat_id_blank_default(self, user):
        n = Notification.objects.create(
            recipient=user,
            type=Notification.Type.REMINDER,
            title="Test",
            body="Test body",
        )
        n.refresh_from_db()
        assert n.telegram_chat_id == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_models.py -v --no-header 2>&1 | head -30`
Expected: FAIL (TelegramVerification does not exist, verified_at field not found, telegram_chat_id not found)

- [ ] **Step 3: Add verified_at to TelegramBinding**

In `accounts/models.py`, modify the `TelegramBinding` class:

```python
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
```

- [ ] **Step 4: Add TelegramVerification model**

In `accounts/models.py`, after the `TelegramBinding` class, add:

```python
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
```

- [ ] **Step 5: Add telegram_chat_id to Notification**

In `projects/models.py`, in the `Notification` class, add after `telegram_message_id`:

```python
    telegram_chat_id = models.CharField(max_length=100, blank=True, default="")
```

- [ ] **Step 6: Generate and apply migrations**

Run:
```bash
cd /home/work/synco && uv run python manage.py makemigrations accounts projects
cd /home/work/synco && uv run python manage.py migrate
```
Expected: Two migration files created and applied

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_models.py -v --no-header`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add accounts/models.py projects/models.py accounts/migrations/ projects/migrations/ tests/test_p15_telegram_models.py
git commit -m "feat(p15): add TelegramVerification model, verified_at, telegram_chat_id fields"
```

---

## Task 3: Bot Initialization + Webhook Auth

**Files:**
- Create: `projects/telegram/__init__.py`
- Create: `projects/telegram/bot.py`
- Create: `projects/telegram/auth.py`
- Test: `tests/test_p15_telegram_auth.py`

- [ ] **Step 1: Write auth tests**

Create `tests/test_p15_telegram_auth.py`:

```python
"""P15: Telegram auth tests."""

import pytest
from unittest.mock import MagicMock

from django.test import RequestFactory, override_settings

from accounts.models import Membership, Organization, TelegramBinding, User
from projects.telegram.auth import validate_webhook_secret, verify_telegram_user_access


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


@pytest.fixture
def binding(user):
    return TelegramBinding.objects.create(
        user=user, chat_id="12345", is_active=True
    )


class TestWebhookSecret:
    @override_settings(TELEGRAM_WEBHOOK_SECRET="mysecret")
    def test_valid_secret(self):
        factory = RequestFactory()
        request = factory.post(
            "/telegram/webhook/",
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="mysecret",
        )
        assert validate_webhook_secret(request) is True

    @override_settings(TELEGRAM_WEBHOOK_SECRET="mysecret")
    def test_invalid_secret(self):
        factory = RequestFactory()
        request = factory.post(
            "/telegram/webhook/",
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong",
        )
        assert validate_webhook_secret(request) is False

    @override_settings(TELEGRAM_WEBHOOK_SECRET="mysecret")
    def test_missing_secret_header(self):
        factory = RequestFactory()
        request = factory.post(
            "/telegram/webhook/",
            content_type="application/json",
        )
        assert validate_webhook_secret(request) is False

    @override_settings(TELEGRAM_WEBHOOK_SECRET="")
    def test_empty_configured_secret_rejects(self):
        factory = RequestFactory()
        request = factory.post(
            "/telegram/webhook/",
            content_type="application/json",
        )
        assert validate_webhook_secret(request) is False


class TestVerifyUserAccess:
    def test_valid_access(self, binding, org):
        from clients.models import Client
        client = Client.objects.create(name="Acme", organization=org)
        from projects.models import Project
        project = Project.objects.create(
            client=client, organization=org, title="Test", created_by=binding.user
        )
        user, user_org = verify_telegram_user_access("12345", project)
        assert user == binding.user
        assert user_org == org

    def test_unknown_chat_id(self):
        with pytest.raises(Exception):
            verify_telegram_user_access("unknown", MagicMock(organization=MagicMock()))

    def test_inactive_binding(self, binding):
        binding.is_active = False
        binding.save()
        with pytest.raises(Exception):
            verify_telegram_user_access("12345", MagicMock(organization=MagicMock()))

    def test_wrong_organization(self, binding):
        other_org = Organization.objects.create(name="Other Firm")
        mock_obj = MagicMock()
        mock_obj.organization = other_org
        with pytest.raises(Exception):
            verify_telegram_user_access("12345", mock_obj)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_auth.py -v --no-header 2>&1 | head -20`
Expected: FAIL (module not found)

- [ ] **Step 3: Create telegram package init**

Create `projects/telegram/__init__.py`:

```python
```

(Empty file)

- [ ] **Step 4: Create bot.py**

Create `projects/telegram/bot.py`:

```python
"""Telegram Bot instance factory.

Does NOT register webhooks. Use management command `setup_telegram_webhook` for that.
"""

from __future__ import annotations

import logging

from django.conf import settings
from telegram import Bot

logger = logging.getLogger(__name__)

_bot_instance: Bot | None = None


def get_bot() -> Bot:
    """Return a shared Bot instance. Raises if token is not configured."""
    global _bot_instance
    if _bot_instance is None:
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is not configured. "
                "Set the environment variable before using Telegram features."
            )
        _bot_instance = Bot(token=token)
    return _bot_instance


def reset_bot() -> None:
    """Reset the cached bot instance (for testing)."""
    global _bot_instance
    _bot_instance = None
```

- [ ] **Step 5: Create auth.py**

Create `projects/telegram/auth.py`:

```python
"""Telegram webhook authentication and user access verification."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied

from accounts.models import Membership, Organization, TelegramBinding, User

logger = logging.getLogger(__name__)


def validate_webhook_secret(request) -> bool:
    """Validate the X-Telegram-Bot-Api-Secret-Token header.

    Returns False if the configured secret is empty (misconfigured).
    """
    configured_secret = settings.TELEGRAM_WEBHOOK_SECRET
    if not configured_secret:
        logger.warning("TELEGRAM_WEBHOOK_SECRET is not configured")
        return False

    header = request.META.get("HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN", "")
    return header == configured_secret


def verify_telegram_user_access(
    chat_id: str, obj
) -> tuple[User, Organization]:
    """Verify that the Telegram chat_id maps to a user with access to obj.

    Args:
        chat_id: Telegram chat ID from the update
        obj: Django model instance with an `organization` attribute

    Returns:
        (user, organization) tuple

    Raises:
        PermissionDenied: If binding not found, inactive, or org mismatch
    """
    try:
        binding = TelegramBinding.objects.select_related("user").get(
            chat_id=chat_id, is_active=True
        )
    except TelegramBinding.DoesNotExist:
        raise PermissionDenied("텔레그램 바인딩을 찾을 수 없습니다.")

    user = binding.user

    try:
        membership = Membership.objects.select_related("organization").get(user=user)
    except Membership.DoesNotExist:
        raise PermissionDenied("조직 소속이 없습니다.")

    user_org = membership.organization

    # Check that the object belongs to the user's organization
    obj_org = getattr(obj, "organization", None)
    if obj_org is not None and obj_org != user_org:
        raise PermissionDenied("이 작업에 대한 권한이 없습니다.")

    return user, user_org
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_auth.py -v --no-header`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add projects/telegram/ tests/test_p15_telegram_auth.py
git commit -m "feat(p15): add telegram bot init and webhook auth module"
```

---

## Task 4: Keyboard Builders + Formatters

**Files:**
- Create: `projects/telegram/keyboards.py`
- Create: `projects/telegram/formatters.py`
- Test: `tests/test_p15_telegram_keyboards.py`

- [ ] **Step 1: Write keyboard and formatter tests**

Create `tests/test_p15_telegram_keyboards.py`:

```python
"""P15: Telegram keyboard and formatter tests."""

import uuid
import pytest
from projects.telegram.keyboards import (
    build_approval_keyboard,
    build_contact_channel_keyboard,
    build_contact_result_keyboard,
    build_contact_save_keyboard,
    build_disambiguation_keyboard,
    parse_callback_data,
)
from projects.telegram.formatters import (
    format_approval_request,
    format_contact_step,
    format_reminder,
    format_todo_list,
)


class TestCallbackData:
    def test_parse_valid(self):
        result = parse_callback_data("n:abc12345:approve")
        assert result == {"notification_short_id": "abc12345", "action": "approve"}

    def test_parse_invalid_prefix(self):
        result = parse_callback_data("x:abc12345:approve")
        assert result is None

    def test_parse_too_few_parts(self):
        result = parse_callback_data("n:abc12345")
        assert result is None

    def test_callback_data_under_64_bytes(self):
        # UUID hex[:8] = 8 chars, action up to ~20 chars
        nid = uuid.uuid4().hex[:8]
        data = f"n:{nid}:approve"
        assert len(data.encode("utf-8")) <= 64


class TestApprovalKeyboard:
    def test_builds_4_buttons(self):
        kb = build_approval_keyboard("abc12345")
        # InlineKeyboardMarkup has inline_keyboard attribute (list of rows)
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(buttons) == 4
        actions = [parse_callback_data(b.callback_data)["action"] for b in buttons]
        assert "approve" in actions
        assert "reject" in actions
        assert "join" in actions
        assert "message" in actions

    def test_all_callback_data_under_64_bytes(self):
        kb = build_approval_keyboard("abc12345")
        for row in kb.inline_keyboard:
            for btn in row:
                assert len(btn.callback_data.encode("utf-8")) <= 64


class TestContactKeyboards:
    def test_channel_keyboard(self):
        kb = build_contact_channel_keyboard("abc12345")
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(buttons) == 3  # phone, kakao, email

    def test_result_keyboard(self):
        kb = build_contact_result_keyboard("abc12345")
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(buttons) == 4  # interested, no_response, on_hold, rejected

    def test_save_keyboard(self):
        kb = build_contact_save_keyboard("abc12345")
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(buttons) == 1  # save without memo


class TestDisambiguationKeyboard:
    def test_builds_candidate_list(self):
        candidates = [
            {"id": "uuid1", "name": "홍길동", "detail": "Rayence 팀장"},
            {"id": "uuid2", "name": "홍길동", "detail": "Samsung 연구원"},
        ]
        kb = build_disambiguation_keyboard("abc12345", candidates)
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(buttons) == 2


class TestFormatters:
    def test_format_approval_request(self):
        text = format_approval_request(
            requester_name="전병권",
            project_title="Rayence 품질기획팀장",
            conflict_info="김소연의 'Rayence 품질기획파트장' (서칭중)",
            message="인사팀 이부장으로부터 직접 의뢰 받았습니다",
        )
        assert "전병권" in text
        assert "Rayence" in text
        assert "synco" in text.lower() or "[synco]" in text

    def test_format_contact_step_channel(self):
        text = format_contact_step(
            candidate_name="홍길동",
            step="channel",
        )
        assert "홍길동" in text
        assert "연락 방법" in text

    def test_format_contact_step_result(self):
        text = format_contact_step(
            candidate_name="홍길동",
            step="result",
            channel="전화",
        )
        assert "결과" in text

    def test_format_contact_step_confirm(self):
        text = format_contact_step(
            candidate_name="홍길동",
            step="confirm",
            channel="전화",
            result="관심",
        )
        assert "홍길동" in text
        assert "전화" in text
        assert "관심" in text

    def test_format_reminder(self):
        text = format_reminder(
            reminder_type="recontact",
            details="홍길동 - Rayence 프로젝트",
        )
        assert "홍길동" in text

    def test_format_todo_list(self):
        actions = [
            {"text": "홍길동 재컨택", "project_title": "Rayence"},
            {"text": "김철수 서류 검토", "project_title": "Samsung"},
        ]
        text = format_todo_list(actions)
        assert "홍길동" in text
        assert "Samsung" in text

    def test_format_todo_list_empty(self):
        text = format_todo_list([])
        assert "없습니다" in text or "없음" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_keyboards.py -v --no-header 2>&1 | head -20`
Expected: FAIL (module not found)

- [ ] **Step 3: Create keyboards.py**

Create `projects/telegram/keyboards.py`:

```python
"""Inline Keyboard builders for Telegram bot.

All callback_data values MUST be under 64 bytes (Telegram API limit).
Format: "n:{notification_short_id}:{action}"
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _cb(short_id: str, action: str) -> str:
    """Build callback_data string. Asserts 64-byte limit."""
    data = f"n:{short_id}:{action}"
    assert len(data.encode("utf-8")) <= 64, f"callback_data too long: {len(data.encode('utf-8'))} bytes"
    return data


def parse_callback_data(data: str) -> dict | None:
    """Parse callback_data string into components.

    Returns {"notification_short_id": str, "action": str} or None if invalid.
    """
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "n":
        return None
    return {"notification_short_id": parts[1], "action": parts[2]}


def build_approval_keyboard(short_id: str) -> InlineKeyboardMarkup:
    """Build approval request keyboard with 4 action buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 승인", callback_data=_cb(short_id, "approve")),
            InlineKeyboardButton("🔗 합류", callback_data=_cb(short_id, "join")),
        ],
        [
            InlineKeyboardButton("💬 메시지", callback_data=_cb(short_id, "message")),
            InlineKeyboardButton("❌ 반려", callback_data=_cb(short_id, "reject")),
        ],
    ])


def build_contact_channel_keyboard(short_id: str) -> InlineKeyboardMarkup:
    """Build contact channel selection keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📞 전화", callback_data=_cb(short_id, "ch_phone")),
            InlineKeyboardButton("💬 카톡", callback_data=_cb(short_id, "ch_kakao")),
            InlineKeyboardButton("📧 이메일", callback_data=_cb(short_id, "ch_email")),
        ],
    ])


def build_contact_result_keyboard(short_id: str) -> InlineKeyboardMarkup:
    """Build contact result selection keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("😊 관심있음", callback_data=_cb(short_id, "rs_interest")),
            InlineKeyboardButton("😐 미응답", callback_data=_cb(short_id, "rs_noresp")),
        ],
        [
            InlineKeyboardButton("🤔 보류", callback_data=_cb(short_id, "rs_hold")),
            InlineKeyboardButton("❌ 거절", callback_data=_cb(short_id, "rs_reject")),
        ],
    ])


def build_contact_save_keyboard(short_id: str) -> InlineKeyboardMarkup:
    """Build contact save (skip memo) keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 저장 — 메모 없이", callback_data=_cb(short_id, "save"))],
    ])


def build_disambiguation_keyboard(
    short_id: str, candidates: list[dict]
) -> InlineKeyboardMarkup:
    """Build candidate disambiguation keyboard.

    Each candidate dict: {"id": str, "name": str, "detail": str}
    """
    buttons = []
    for i, c in enumerate(candidates[:5]):  # Max 5 choices
        label = f"{i + 1}. {c['name']} - {c['detail']}"
        # Truncate label to avoid display issues
        if len(label) > 40:
            label = label[:37] + "..."
        buttons.append([
            InlineKeyboardButton(label, callback_data=_cb(short_id, f"sel_{i}"))
        ])
    return InlineKeyboardMarkup(buttons)
```

- [ ] **Step 4: Create formatters.py**

Create `projects/telegram/formatters.py`:

```python
"""Message text formatters for Telegram bot.

All output uses Telegram MarkdownV2 or plain text.
We use plain text to avoid escaping complexity.
"""

from __future__ import annotations


def format_approval_request(
    *,
    requester_name: str,
    project_title: str,
    conflict_info: str,
    message: str = "",
) -> str:
    """Format approval request notification message."""
    lines = [
        "🤖 [synco] 프로젝트 등록 승인 요청",
        "",
        f"  {requester_name} → {project_title}",
        f"  충돌: {conflict_info}",
    ]
    if message:
        lines.append(f'  메시지: "{message}"')
    return "\n".join(lines)


def format_contact_step(
    *,
    candidate_name: str,
    step: str,
    channel: str = "",
    result: str = "",
) -> str:
    """Format contact recording step message."""
    if step == "channel":
        return (
            f"🤖 {candidate_name} 컨택 결과를 기록합니다.\n\n"
            f"  연락 방법은?"
        )
    elif step == "result":
        return (
            f"🤖 {candidate_name} 컨택 기록 중\n"
            f"  채널: {channel}\n\n"
            f"  결과는?"
        )
    elif step == "confirm":
        return (
            f"🤖 컨택 기록 저장:\n"
            f"  {candidate_name} | {channel} | {result}\n"
            f"  메모를 입력해주세요. (건너뛰려면 아래 버튼)"
        )
    return f"🤖 {candidate_name} 컨택 기록"


def format_reminder(*, reminder_type: str, details: str) -> str:
    """Format reminder notification message."""
    type_labels = {
        "recontact": "📞 재컨택 예정",
        "lock_expiry": "🔓 잠금 만료 임박",
        "submission_review": "📋 서류 검토 대기",
        "interview_tomorrow": "📅 내일 면접",
    }
    label = type_labels.get(reminder_type, "🔔 리마인더")
    return f"{label}\n\n{details}"


def format_todo_list(actions: list[dict]) -> str:
    """Format today's action list."""
    if not actions:
        return "🤖 오늘의 할 일이 없습니다."

    lines = ["🤖 오늘의 할 일:"]
    for i, action in enumerate(actions, 1):
        project = action.get("project_title", "")
        text = action.get("text", "")
        lines.append(f"  {i}. [{project}] {text}")
    return "\n".join(lines)


def format_status_summary(
    *,
    project_title: str,
    status: str,
    contacts_count: int,
    submissions_count: int,
    interviews_count: int,
) -> str:
    """Format project status summary."""
    return (
        f"🤖 {project_title} 현황\n\n"
        f"  상태: {status}\n"
        f"  컨택: {contacts_count}건\n"
        f"  추천: {submissions_count}건\n"
        f"  면접: {interviews_count}건"
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_keyboards.py -v --no-header`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add projects/telegram/keyboards.py projects/telegram/formatters.py tests/test_p15_telegram_keyboards.py
git commit -m "feat(p15): add telegram keyboard builders and message formatters"
```

---

## Task 5: Notification Service

**Files:**
- Create: `projects/services/notification.py`
- Test: `tests/test_p15_telegram_notification.py`

- [ ] **Step 1: Write notification service tests**

Create `tests/test_p15_telegram_notification.py`:

```python
"""P15: Notification service tests."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from django.utils import timezone

from accounts.models import Membership, Organization, TelegramBinding, User
from projects.models import Notification
from projects.services.notification import (
    send_notification,
    send_bulk_notifications,
    update_telegram_message,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


@pytest.fixture
def binding(user):
    return TelegramBinding.objects.create(
        user=user, chat_id="12345", is_active=True, verified_at=timezone.now()
    )


@pytest.fixture
def notification(user):
    return Notification.objects.create(
        recipient=user,
        type=Notification.Type.REMINDER,
        title="Test Reminder",
        body="Test body",
    )


class TestSendNotification:
    @patch("projects.services.notification._send_telegram_message")
    def test_send_success(self, mock_send, binding, notification):
        mock_send.return_value = "msg_123"
        result = send_notification(notification)
        assert result is True
        notification.refresh_from_db()
        assert notification.status == Notification.Status.SENT
        assert notification.telegram_message_id == "msg_123"
        assert notification.telegram_chat_id == "12345"

    @patch("projects.services.notification._send_telegram_message")
    def test_send_no_binding(self, mock_send, notification):
        """No TelegramBinding → skip, return False."""
        result = send_notification(notification)
        assert result is False
        mock_send.assert_not_called()

    @patch("projects.services.notification._send_telegram_message")
    def test_send_inactive_binding(self, mock_send, user, notification):
        TelegramBinding.objects.create(
            user=user, chat_id="12345", is_active=False
        )
        result = send_notification(notification)
        assert result is False
        mock_send.assert_not_called()

    @patch("projects.services.notification._send_telegram_message")
    def test_send_api_failure(self, mock_send, binding, notification):
        mock_send.side_effect = Exception("Telegram API error")
        result = send_notification(notification)
        assert result is False
        notification.refresh_from_db()
        assert notification.status == Notification.Status.PENDING


class TestSendBulk:
    @patch("projects.services.notification._send_telegram_message")
    def test_bulk_send(self, mock_send, binding, user):
        mock_send.return_value = "msg_1"
        n1 = Notification.objects.create(
            recipient=user, type=Notification.Type.NEWS,
            title="News 1", body="Body 1",
        )
        n2 = Notification.objects.create(
            recipient=user, type=Notification.Type.NEWS,
            title="News 2", body="Body 2",
        )
        count = send_bulk_notifications([n1, n2])
        assert count == 2


class TestUpdateMessage:
    @patch("projects.services.notification._edit_telegram_message")
    def test_update_success(self, mock_edit, binding, notification):
        notification.telegram_message_id = "msg_123"
        notification.telegram_chat_id = "12345"
        notification.save()
        result = update_telegram_message(notification, "Updated text")
        assert result is True
        mock_edit.assert_called_once()

    @patch("projects.services.notification._edit_telegram_message")
    def test_update_chat_id_mismatch(self, mock_edit, user, notification):
        """Rebind scenario: chat_id changed → skip update."""
        TelegramBinding.objects.create(
            user=user, chat_id="99999", is_active=True
        )
        notification.telegram_message_id = "msg_123"
        notification.telegram_chat_id = "12345"  # Old chat_id
        notification.save()
        result = update_telegram_message(notification, "Updated text")
        assert result is False
        mock_edit.assert_not_called()

    @patch("projects.services.notification._edit_telegram_message")
    def test_update_no_message_id(self, mock_edit, binding, notification):
        """No telegram_message_id → skip."""
        result = update_telegram_message(notification, "Updated text")
        assert result is False
        mock_edit.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_notification.py -v --no-header 2>&1 | head -20`
Expected: FAIL (module not found)

- [ ] **Step 3: Create notification.py service**

Create `projects/services/notification.py`:

```python
"""Notification creation, Telegram delivery, and message update service."""

from __future__ import annotations

import asyncio
import logging

from django.conf import settings

from accounts.models import TelegramBinding
from projects.models import Notification

logger = logging.getLogger(__name__)


def _send_telegram_message(
    chat_id: str,
    text: str,
    reply_markup=None,
) -> str:
    """Send a message via Telegram Bot API. Returns message_id as string.

    This is the single point of Telegram API contact for sending.
    Uses synchronous wrapper around async python-telegram-bot.
    """
    from projects.telegram.bot import get_bot

    bot = get_bot()

    async def _send():
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        return str(msg.message_id)

    return asyncio.run(_send())


def _edit_telegram_message(
    chat_id: str,
    message_id: str,
    text: str,
    reply_markup=None,
) -> bool:
    """Edit an existing Telegram message. Returns True on success."""
    from projects.telegram.bot import get_bot

    bot = get_bot()

    async def _edit():
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=int(message_id),
            text=text,
            reply_markup=reply_markup,
        )
        return True

    return asyncio.run(_edit())


def send_notification(
    notification: Notification,
    text: str | None = None,
    reply_markup=None,
) -> bool:
    """Send a Notification via Telegram.

    1. Look up recipient's TelegramBinding
    2. If no binding or inactive → return False
    3. Send message → record message_id + chat_id snapshot
    4. On API failure → log + return False (no exception propagation)
    """
    try:
        binding = TelegramBinding.objects.get(
            user=notification.recipient, is_active=True
        )
    except TelegramBinding.DoesNotExist:
        return False

    message_text = text or f"{notification.title}\n\n{notification.body}"

    try:
        message_id = _send_telegram_message(
            chat_id=binding.chat_id,
            text=message_text,
            reply_markup=reply_markup,
        )
        notification.telegram_message_id = message_id
        notification.telegram_chat_id = binding.chat_id
        notification.status = Notification.Status.SENT
        notification.save(
            update_fields=["telegram_message_id", "telegram_chat_id", "status"]
        )
        return True
    except Exception:
        logger.exception(
            "Failed to send Telegram notification %s", notification.pk
        )
        return False


def send_bulk_notifications(notifications: list[Notification]) -> int:
    """Send multiple notifications. Returns count of successful sends."""
    success_count = 0
    for notification in notifications:
        if send_notification(notification):
            success_count += 1
    return success_count


def update_telegram_message(
    notification: Notification,
    new_text: str,
    reply_markup=None,
) -> bool:
    """Update an existing Telegram message.

    1. Check telegram_message_id exists
    2. Compare telegram_chat_id with current binding's chat_id
    3. If mismatch (rebind occurred) → skip, return False
    4. Edit message text
    """
    if not notification.telegram_message_id:
        return False

    if not notification.telegram_chat_id:
        return False

    try:
        binding = TelegramBinding.objects.get(
            user=notification.recipient, is_active=True
        )
    except TelegramBinding.DoesNotExist:
        return False

    # Rebind check: if chat_id changed, don't try to edit old message
    if binding.chat_id != notification.telegram_chat_id:
        return False

    try:
        _edit_telegram_message(
            chat_id=notification.telegram_chat_id,
            message_id=notification.telegram_message_id,
            text=new_text,
            reply_markup=reply_markup,
        )
        return True
    except Exception:
        logger.exception(
            "Failed to update Telegram message for notification %s",
            notification.pk,
        )
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_notification.py -v --no-header`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/notification.py tests/test_p15_telegram_notification.py
git commit -m "feat(p15): add notification service with telegram send/update/bulk"
```

---

## Task 6: Callback Handlers

**Files:**
- Create: `projects/telegram/handlers.py`
- Test: `tests/test_p15_telegram_handlers.py`

- [ ] **Step 1: Write handler tests**

Create `tests/test_p15_telegram_handlers.py`:

```python
"""P15: Telegram callback handler tests."""

import uuid
import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone

from accounts.models import Membership, Organization, TelegramBinding, User
from clients.models import Client
from projects.models import (
    Contact,
    Notification,
    Project,
    ProjectApproval,
)
from projects.telegram.handlers import (
    handle_approval_callback,
    handle_contact_callback,
    CHANNEL_MAP,
    RESULT_MAP,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user_owner(db, org):
    u = User.objects.create_user(username="owner", password="test1234")
    Membership.objects.create(user=u, organization=org, role="owner")
    return u


@pytest.fixture
def user_consultant(db, org):
    u = User.objects.create_user(username="consultant", password="test1234")
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


@pytest.fixture
def binding(user_owner):
    return TelegramBinding.objects.create(
        user=user_owner, chat_id="12345", is_active=True
    )


@pytest.fixture
def client_obj(org):
    return Client.objects.create(name="Acme Corp", organization=org)


@pytest.fixture
def project(org, client_obj, user_consultant):
    return Project.objects.create(
        client=client_obj, organization=org,
        title="Test Position", created_by=user_consultant,
    )


@pytest.fixture
def pending_approval(project, user_consultant, user_owner):
    return ProjectApproval.objects.create(
        project=project, requested_by=user_consultant,
        conflict_project=None,
    )


class TestApprovalCallback:
    @patch("projects.telegram.handlers._update_notification_message")
    def test_approve_action(self, mock_update, binding, pending_approval, user_owner):
        notif = Notification.objects.create(
            recipient=user_owner,
            type=Notification.Type.APPROVAL_REQUEST,
            title="Approval",
            body="Test",
            callback_data={
                "action": "approval",
                "approval_id": str(pending_approval.pk),
            },
        )
        result = handle_approval_callback(
            notification=notif,
            action="approve",
            user=user_owner,
        )
        assert result["ok"] is True
        pending_approval.refresh_from_db()
        assert pending_approval.status == ProjectApproval.Status.APPROVED

    @patch("projects.telegram.handlers._update_notification_message")
    def test_reject_action(self, mock_update, binding, pending_approval, user_owner):
        notif = Notification.objects.create(
            recipient=user_owner,
            type=Notification.Type.APPROVAL_REQUEST,
            title="Approval",
            body="Test",
            callback_data={
                "action": "approval",
                "approval_id": str(pending_approval.pk),
            },
        )
        result = handle_approval_callback(
            notification=notif,
            action="reject",
            user=user_owner,
        )
        assert result["ok"] is True

    @patch("projects.telegram.handlers._update_notification_message")
    def test_invalid_approval_id(self, mock_update, user_owner):
        notif = Notification.objects.create(
            recipient=user_owner,
            type=Notification.Type.APPROVAL_REQUEST,
            title="Approval",
            body="Test",
            callback_data={"action": "approval", "approval_id": str(uuid.uuid4())},
        )
        result = handle_approval_callback(
            notification=notif, action="approve", user=user_owner,
        )
        assert result["ok"] is False


class TestContactCallback:
    @patch("projects.telegram.handlers._send_next_step")
    def test_channel_selection(self, mock_send, binding, user_owner, project):
        from candidates.models import Candidate
        candidate = Candidate.objects.create(
            name="홍길동", owned_by=binding.user.membership.organization
        )
        notif = Notification.objects.create(
            recipient=user_owner,
            type=Notification.Type.AUTO_GENERATED,
            title="Contact",
            body="Test",
            callback_data={
                "action": "contact_record",
                "step": 1,
                "project_id": str(project.pk),
                "candidate_id": str(candidate.pk),
            },
        )
        result = handle_contact_callback(
            notification=notif,
            action="ch_phone",
            user=user_owner,
        )
        assert result["ok"] is True
        assert result["next_step"] == 2

    @patch("projects.telegram.handlers._send_next_step")
    def test_result_selection(self, mock_send, binding, user_owner, project):
        from candidates.models import Candidate
        candidate = Candidate.objects.create(
            name="홍길동", owned_by=binding.user.membership.organization
        )
        notif = Notification.objects.create(
            recipient=user_owner,
            type=Notification.Type.AUTO_GENERATED,
            title="Contact",
            body="Test",
            callback_data={
                "action": "contact_record",
                "step": 2,
                "project_id": str(project.pk),
                "candidate_id": str(candidate.pk),
                "channel": "전화",
            },
        )
        result = handle_contact_callback(
            notification=notif,
            action="rs_interest",
            user=user_owner,
        )
        assert result["ok"] is True
        assert result["next_step"] == 3

    @patch("projects.telegram.handlers._send_next_step")
    def test_save_creates_contact(self, mock_send, binding, user_owner, project):
        from candidates.models import Candidate
        candidate = Candidate.objects.create(
            name="홍길동", owned_by=binding.user.membership.organization
        )
        notif = Notification.objects.create(
            recipient=user_owner,
            type=Notification.Type.AUTO_GENERATED,
            title="Contact",
            body="Test",
            callback_data={
                "action": "contact_record",
                "step": 3,
                "project_id": str(project.pk),
                "candidate_id": str(candidate.pk),
                "channel": "전화",
                "result": "관심",
            },
        )
        result = handle_contact_callback(
            notification=notif,
            action="save",
            user=user_owner,
        )
        assert result["ok"] is True
        assert Contact.objects.filter(
            project=project, candidate=candidate
        ).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_handlers.py -v --no-header 2>&1 | head -20`
Expected: FAIL (module not found)

- [ ] **Step 3: Create handlers.py**

Create `projects/telegram/handlers.py`:

```python
"""Telegram callback and message handlers.

All business logic delegates to existing service functions.
Handlers are thin wrappers that translate Telegram actions to service calls.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from accounts.models import User
from projects.models import Contact, Notification, ProjectApproval
from projects.services.approval import (
    InvalidApprovalTransition,
    approve_project,
    merge_project,
    reject_project,
    send_admin_message,
)
from projects.services.contact import check_duplicate

logger = logging.getLogger(__name__)

# Map callback action suffixes to Contact.Channel values
CHANNEL_MAP = {
    "ch_phone": Contact.Channel.PHONE,
    "ch_kakao": Contact.Channel.KAKAO,
    "ch_email": Contact.Channel.EMAIL,
}

# Map callback action suffixes to Contact.Result values
RESULT_MAP = {
    "rs_interest": Contact.Result.INTERESTED,
    "rs_noresp": Contact.Result.NO_RESPONSE,
    "rs_hold": Contact.Result.ON_HOLD,
    "rs_reject": Contact.Result.REJECTED,
}


def _update_notification_message(notification: Notification, text: str) -> None:
    """Update the Telegram message for a notification (fire-and-forget)."""
    from projects.services.notification import update_telegram_message

    try:
        update_telegram_message(notification, text)
    except Exception:
        logger.exception("Failed to update telegram message for %s", notification.pk)


def _send_next_step(
    *,
    recipient: User,
    callback_data: dict,
    text: str,
    reply_markup=None,
) -> Notification:
    """Create a new Notification for the next step and send it."""
    from projects.services.notification import send_notification

    notif = Notification.objects.create(
        recipient=recipient,
        type=Notification.Type.AUTO_GENERATED,
        title="컨택 기록",
        body=text,
        callback_data=callback_data,
    )
    send_notification(notif, text=text, reply_markup=reply_markup)
    return notif


def handle_approval_callback(
    *,
    notification: Notification,
    action: str,
    user: User,
) -> dict:
    """Handle approval-related callback actions.

    Actions: approve, reject, join, message
    Delegates to projects/services/approval.py functions.
    """
    approval_id = notification.callback_data.get("approval_id")
    if not approval_id:
        return {"ok": False, "error": "승인 데이터가 없습니다."}

    try:
        approval = ProjectApproval.objects.get(pk=approval_id)
    except ProjectApproval.DoesNotExist:
        return {"ok": False, "error": "승인 요청을 찾을 수 없습니다."}

    try:
        if action == "approve":
            approve_project(approval, user)
            _update_notification_message(notification, f"✅ 승인 완료 — {approval.project.title}")
            return {"ok": True, "result": "approved"}

        elif action == "reject":
            reject_project(approval, user)
            _update_notification_message(notification, f"❌ 반려 완료 — {approval.project.title}")
            return {"ok": True, "result": "rejected"}

        elif action == "join":
            merge_project(approval, user)
            _update_notification_message(notification, f"🔗 합류 완료 — {approval.project.title}")
            return {"ok": True, "result": "joined"}

        elif action == "message":
            # Message action: respond with instruction to type message
            return {"ok": True, "result": "awaiting_message", "prompt": "메시지를 입력해주세요."}

        else:
            return {"ok": False, "error": f"알 수 없는 액션: {action}"}

    except InvalidApprovalTransition as e:
        return {"ok": False, "error": str(e)}


def handle_contact_callback(
    *,
    notification: Notification,
    action: str,
    user: User,
) -> dict:
    """Handle multi-step contact recording callback.

    Step 1: channel selection (ch_phone, ch_kakao, ch_email)
    Step 2: result selection (rs_interest, rs_noresp, rs_hold, rs_reject)
    Step 3: save (save) — creates Contact via service layer
    """
    cb = notification.callback_data
    step = cb.get("step", 1)
    project_id = cb.get("project_id")
    candidate_id = cb.get("candidate_id")

    from projects.models import Project
    from candidates.models import Candidate
    from projects.telegram.keyboards import (
        build_contact_result_keyboard,
        build_contact_save_keyboard,
    )
    from projects.telegram.formatters import format_contact_step

    try:
        project = Project.objects.get(pk=project_id)
        candidate = Candidate.objects.get(pk=candidate_id)
    except (Project.DoesNotExist, Candidate.DoesNotExist):
        return {"ok": False, "error": "프로젝트 또는 후보자를 찾을 수 없습니다."}

    if step == 1 and action in CHANNEL_MAP:
        # Channel selected → move to step 2 (result selection)
        channel = CHANNEL_MAP[action]
        next_cb = {
            **cb,
            "step": 2,
            "channel": channel,
            "parent_notification_id": str(notification.pk),
        }
        text = format_contact_step(
            candidate_name=candidate.name, step="result", channel=channel,
        )
        short_id = str(notification.pk).replace("-", "")[:8]
        _send_next_step(
            recipient=user,
            callback_data=next_cb,
            text=text,
            reply_markup=build_contact_result_keyboard(short_id),
        )
        return {"ok": True, "next_step": 2}

    elif step == 2 and action in RESULT_MAP:
        # Result selected → move to step 3 (confirm/save)
        result_val = RESULT_MAP[action]
        channel = cb.get("channel", "")
        next_cb = {
            **cb,
            "step": 3,
            "result": result_val,
            "parent_notification_id": str(notification.pk),
        }
        text = format_contact_step(
            candidate_name=candidate.name,
            step="confirm",
            channel=channel,
            result=result_val,
        )
        short_id = str(notification.pk).replace("-", "")[:8]
        _send_next_step(
            recipient=user,
            callback_data=next_cb,
            text=text,
            reply_markup=build_contact_save_keyboard(short_id),
        )
        return {"ok": True, "next_step": 3}

    elif step == 3 and action == "save":
        # Final save — delegate to service layer
        channel = cb.get("channel", "")
        result_val = cb.get("result", "")

        # Check duplicate via existing service
        dup = check_duplicate(project, candidate)
        if dup["blocked"]:
            return {"ok": False, "error": dup["warnings"][0]}

        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user,
            channel=channel,
            result=result_val,
            contacted_at=timezone.now(),
        )

        # Release overlapping RESERVED locks (same as existing contact_create view)
        Contact.objects.filter(
            project=project,
            candidate=candidate,
            result=Contact.Result.RESERVED,
            locked_until__gt=timezone.now(),
        ).update(locked_until=timezone.now())

        _update_notification_message(
            notification,
            f"✅ 컨택 기록 저장 완료\n{candidate.name} | {channel} | {result_val}",
        )
        return {"ok": True, "contact_id": str(contact.pk)}

    return {"ok": False, "error": "잘못된 단계입니다."}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_handlers.py -v --no-header`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/telegram/handlers.py tests/test_p15_telegram_handlers.py
git commit -m "feat(p15): add telegram callback handlers for approval and contact recording"
```

---

## Task 7: Views + URL Routing

**Files:**
- Create: `projects/views_telegram.py`
- Create: `projects/urls_telegram.py`
- Modify: `main/urls.py`
- Create: `accounts/templates/accounts/telegram_bind.html`
- Test: `tests/test_p15_telegram_views.py`

- [ ] **Step 1: Write view tests**

Create `tests/test_p15_telegram_views.py`:

```python
"""P15: Telegram view tests."""

import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client as TestClient, override_settings
from django.utils import timezone

from accounts.models import (
    Membership,
    Organization,
    TelegramBinding,
    TelegramVerification,
    User,
)
from projects.models import Notification


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


@pytest.fixture
def auth_client(user):
    c = TestClient()
    c.login(username="tester", password="test1234")
    return c


@pytest.fixture
def binding(user):
    return TelegramBinding.objects.create(
        user=user, chat_id="12345", is_active=True, verified_at=timezone.now()
    )


class TestWebhookView:
    @override_settings(TELEGRAM_WEBHOOK_SECRET="testsecret")
    def test_missing_secret_returns_403(self):
        c = TestClient()
        resp = c.post(
            "/telegram/webhook/",
            data=json.dumps({"update_id": 1}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    @override_settings(TELEGRAM_WEBHOOK_SECRET="testsecret")
    def test_wrong_secret_returns_403(self):
        c = TestClient()
        resp = c.post(
            "/telegram/webhook/",
            data=json.dumps({"update_id": 1}),
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong",
        )
        assert resp.status_code == 403

    @override_settings(TELEGRAM_WEBHOOK_SECRET="testsecret")
    def test_invalid_json_returns_400(self):
        c = TestClient()
        resp = c.post(
            "/telegram/webhook/",
            data="not json",
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="testsecret",
        )
        assert resp.status_code == 400

    @override_settings(TELEGRAM_WEBHOOK_SECRET="testsecret")
    @patch("projects.views_telegram._process_update")
    def test_valid_webhook(self, mock_process):
        c = TestClient()
        resp = c.post(
            "/telegram/webhook/",
            data=json.dumps({"update_id": 123}),
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="testsecret",
        )
        assert resp.status_code == 200
        mock_process.assert_called_once()

    @override_settings(TELEGRAM_WEBHOOK_SECRET="testsecret")
    @patch("projects.views_telegram._process_update")
    def test_duplicate_update_id_skipped(self, mock_process):
        c = TestClient()
        payload = json.dumps({"update_id": 456})
        # First request
        c.post(
            "/telegram/webhook/", data=payload,
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="testsecret",
        )
        # Second request (duplicate)
        c.post(
            "/telegram/webhook/", data=payload,
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="testsecret",
        )
        # Should only process once
        assert mock_process.call_count == 1


class TestBindView:
    def test_bind_get_shows_form(self, auth_client):
        resp = auth_client.get("/telegram/bind/")
        assert resp.status_code == 200

    def test_bind_post_creates_verification(self, auth_client, user):
        resp = auth_client.post("/telegram/bind/")
        assert resp.status_code == 200
        v = TelegramVerification.objects.filter(user=user, consumed=False).first()
        assert v is not None
        assert len(v.code) == 6

    def test_bind_post_invalidates_previous_codes(self, auth_client, user):
        # Create a previous verification
        TelegramVerification.objects.create(
            user=user, code="111111",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        auth_client.post("/telegram/bind/")
        old = TelegramVerification.objects.get(code="111111")
        assert old.consumed is True


class TestUnbindView:
    def test_unbind(self, auth_client, binding):
        resp = auth_client.post("/telegram/unbind/")
        assert resp.status_code == 200
        binding.refresh_from_db()
        assert binding.is_active is False

    def test_unbind_no_binding(self, auth_client):
        resp = auth_client.post("/telegram/unbind/")
        assert resp.status_code == 200  # Graceful


class TestTestSendView:
    @patch("projects.services.notification._send_telegram_message")
    def test_send_test_message(self, mock_send, auth_client, binding):
        mock_send.return_value = "msg_1"
        resp = auth_client.post("/telegram/test/")
        assert resp.status_code == 200
        mock_send.assert_called_once()

    def test_send_without_binding(self, auth_client):
        resp = auth_client.post("/telegram/test/")
        assert resp.status_code == 200  # Returns error message, not 500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_views.py -v --no-header 2>&1 | head -20`
Expected: FAIL (import errors / 404s)

- [ ] **Step 3: Create urls_telegram.py**

Create `projects/urls_telegram.py`:

```python
from django.urls import path

from . import views_telegram

app_name = "telegram"

urlpatterns = [
    path("webhook/", views_telegram.telegram_webhook, name="webhook"),
    path("bind/", views_telegram.telegram_bind, name="bind"),
    path("unbind/", views_telegram.telegram_unbind, name="unbind"),
    path("test/", views_telegram.telegram_test_send, name="test"),
]
```

- [ ] **Step 4: Add URL include to main/urls.py**

In `main/urls.py`, add after the projects include (line 20):

```python
    path("telegram/", include("projects.urls_telegram")),
```

Also add `"projects.urls_telegram"` uses `include`, so the import is already present.

- [ ] **Step 5: Create views_telegram.py**

Create `projects/views_telegram.py`:

```python
"""Telegram webhook and binding views."""

from __future__ import annotations

import json
import logging
import random
import string
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import TelegramBinding, TelegramVerification
from projects.telegram.auth import validate_webhook_secret

logger = logging.getLogger(__name__)

DEDUP_TTL = 300  # 5 minutes


def _process_update(data: dict) -> None:
    """Process a Telegram update (callback_query or message).

    Dispatches to appropriate handler based on update type.
    """
    from projects.telegram.handlers import (
        handle_approval_callback,
        handle_contact_callback,
    )
    from projects.telegram.keyboards import parse_callback_data
    from projects.telegram.auth import verify_telegram_user_access
    from projects.models import Notification

    # Handle callback_query (button press)
    callback_query = data.get("callback_query")
    if callback_query:
        cb_data = callback_query.get("data", "")
        parsed = parse_callback_data(cb_data)
        if not parsed:
            logger.warning("Invalid callback_data: %s", cb_data)
            return

        short_id = parsed["notification_short_id"]
        action = parsed["action"]

        # Find notification by short_id (UUID hex prefix)
        try:
            notification = Notification.objects.get(
                pk__startswith=short_id,
            )
        except (Notification.DoesNotExist, Notification.MultipleObjectsReturned):
            # Fallback: search by hex prefix in string
            notifications = Notification.objects.filter(
                id__startswith=short_id
            )
            if notifications.count() != 1:
                logger.warning("Cannot resolve notification for short_id: %s", short_id)
                return
            notification = notifications.first()

        chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
        cb = notification.callback_data
        notif_action = cb.get("action", "")

        try:
            if notif_action == "approval":
                user, _ = verify_telegram_user_access(chat_id, notification.callback_data.get("project"))
                handle_approval_callback(
                    notification=notification, action=action, user=user,
                )
            elif notif_action == "contact_record":
                from projects.models import Project
                project = Project.objects.get(pk=cb["project_id"])
                user, _ = verify_telegram_user_access(chat_id, project)
                handle_contact_callback(
                    notification=notification, action=action, user=user,
                )
        except Exception:
            logger.exception("Error handling callback for notification %s", notification.pk)
        return

    # Handle text message (free-text query)
    message = data.get("message")
    if message:
        text = message.get("text", "")
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Handle /start command for binding
        if text.startswith("/start "):
            code = text[7:].strip()
            _handle_start_command(chat_id, code)
            return

        # Text queries will be handled in a future task (P14 dependency)
        logger.info("Text message from %s: %s", chat_id, text[:100])


def _handle_start_command(chat_id: str, code: str) -> None:
    """Handle /start <code> command for binding verification."""
    from projects.services.notification import _send_telegram_message

    try:
        verification = TelegramVerification.objects.filter(
            code=code,
            consumed=False,
            expires_at__gt=timezone.now(),
        ).select_related("user").first()

        if not verification:
            try:
                _send_telegram_message(chat_id, "인증 코드가 만료되었거나 존재하지 않습니다.")
            except Exception:
                pass
            return

        if verification.is_blocked:
            try:
                _send_telegram_message(chat_id, "인증 시도 횟수를 초과했습니다. 새 코드를 발급해주세요.")
            except Exception:
                pass
            return

        verification.attempts += 1
        verification.consumed = True
        verification.save(update_fields=["attempts", "consumed"])

        # Create or update binding
        binding, created = TelegramBinding.objects.update_or_create(
            user=verification.user,
            defaults={
                "chat_id": chat_id,
                "is_active": True,
                "verified_at": timezone.now(),
            },
        )

        try:
            _send_telegram_message(chat_id, "✅ synco 텔레그램 연동이 완료되었습니다!")
        except Exception:
            pass

    except Exception:
        logger.exception("Error handling /start command")


@csrf_exempt
@require_POST
def telegram_webhook(request):
    """POST /telegram/webhook/ — Telegram Bot webhook endpoint."""
    if not validate_webhook_secret(request):
        return HttpResponse(status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=400)

    # Idempotency: check update_id
    update_id = data.get("update_id")
    if update_id:
        cache_key = f"tg_update:{update_id}"
        if cache.get(cache_key):
            return HttpResponse(status=200)
        cache.set(cache_key, True, DEDUP_TTL)

    try:
        _process_update(data)
    except Exception:
        logger.exception("Error processing Telegram update")

    # Always return 200 to prevent Telegram retries
    return HttpResponse(status=200)


@login_required
def telegram_bind(request):
    """GET/POST /telegram/bind/ — Telegram binding settings."""
    if request.method == "POST":
        user = request.user

        # Invalidate previous codes
        TelegramVerification.objects.filter(
            user=user, consumed=False,
        ).update(consumed=True)

        # Generate new 6-digit code
        code = "".join(random.choices(string.digits, k=6))
        verification = TelegramVerification.objects.create(
            user=user,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        # Check if already bound
        try:
            binding = TelegramBinding.objects.get(user=user)
            is_bound = binding.is_active
        except TelegramBinding.DoesNotExist:
            is_bound = False

        return render(request, "accounts/telegram_bind.html", {
            "code": code,
            "is_bound": is_bound,
            "expires_minutes": 5,
        })

    # GET: show current binding status
    try:
        binding = TelegramBinding.objects.get(user=request.user)
        is_bound = binding.is_active
        verified_at = binding.verified_at
    except TelegramBinding.DoesNotExist:
        is_bound = False
        verified_at = None

    return render(request, "accounts/telegram_bind.html", {
        "is_bound": is_bound,
        "verified_at": verified_at,
    })


@login_required
@require_POST
def telegram_unbind(request):
    """POST /telegram/unbind/ — Deactivate Telegram binding."""
    try:
        binding = TelegramBinding.objects.get(user=request.user)
        binding.is_active = False
        binding.save(update_fields=["is_active"])
    except TelegramBinding.DoesNotExist:
        pass

    return render(request, "accounts/telegram_bind.html", {
        "is_bound": False,
        "message": "텔레그램 연동이 해제되었습니다.",
    })


@login_required
@require_POST
def telegram_test_send(request):
    """POST /telegram/test/ — Send a test message."""
    from projects.services.notification import _send_telegram_message

    try:
        binding = TelegramBinding.objects.get(
            user=request.user, is_active=True
        )
    except TelegramBinding.DoesNotExist:
        return render(request, "accounts/telegram_bind.html", {
            "is_bound": False,
            "error": "텔레그램이 연결되어 있지 않습니다.",
        })

    try:
        _send_telegram_message(binding.chat_id, "🤖 synco 테스트 메시지입니다!")
        return render(request, "accounts/telegram_bind.html", {
            "is_bound": True,
            "verified_at": binding.verified_at,
            "message": "테스트 메시지가 전송되었습니다.",
        })
    except Exception:
        return render(request, "accounts/telegram_bind.html", {
            "is_bound": True,
            "verified_at": binding.verified_at,
            "error": "메시지 전송에 실패했습니다.",
        })
```

- [ ] **Step 6: Create telegram_bind.html template**

Create `accounts/templates/accounts/telegram_bind.html`:

```html
{% extends "base.html" %}
{% block title %}텔레그램 연동{% endblock %}
{% block content %}
<div class="max-w-lg mx-auto py-8">
  <h2 class="text-xl font-bold mb-6">텔레그램 연동 설정</h2>

  {% if message %}
  <div class="mb-4 p-3 bg-green-50 text-green-700 rounded-lg text-sm">
    {{ message }}
  </div>
  {% endif %}

  {% if error %}
  <div class="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">
    {{ error }}
  </div>
  {% endif %}

  {% if code %}
  <div class="mb-6 p-4 bg-blue-50 rounded-lg">
    <p class="text-sm text-gray-600 mb-2">텔레그램 Bot에 아래 코드를 보내주세요:</p>
    <p class="text-3xl font-mono font-bold text-center tracking-widest my-4">{{ code }}</p>
    <p class="text-xs text-gray-500 text-center">
      /start {{ code }} — {{ expires_minutes }}분 내 입력
    </p>
  </div>
  {% endif %}

  {% if is_bound %}
  <div class="mb-4 p-3 bg-green-50 rounded-lg">
    <p class="text-sm text-green-700">
      ✅ 텔레그램이 연결되어 있습니다.
      {% if verified_at %}
      <span class="text-xs text-gray-500">({{ verified_at|date:"Y-m-d H:i" }})</span>
      {% endif %}
    </p>
  </div>

  <div class="flex gap-3">
    <form method="post" action="{% url 'telegram:test' %}" class="flex-1">
      {% csrf_token %}
      <button type="submit"
        class="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm">
        테스트 메시지 보내기
      </button>
    </form>
    <form method="post" action="{% url 'telegram:unbind' %}" class="flex-1">
      {% csrf_token %}
      <button type="submit"
        class="w-full px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 text-sm">
        연동 해제
      </button>
    </form>
  </div>
  {% else %}
  <form method="post" action="{% url 'telegram:bind' %}">
    {% csrf_token %}
    <button type="submit"
      class="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm">
      텔레그램 연결하기
    </button>
  </form>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_views.py -v --no-header`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add projects/views_telegram.py projects/urls_telegram.py main/urls.py accounts/templates/accounts/telegram_bind.html tests/test_p15_telegram_views.py
git commit -m "feat(p15): add telegram webhook, bind/unbind views with URL routing"
```

---

## Task 8: Management Commands

**Files:**
- Create: `projects/management/__init__.py`
- Create: `projects/management/commands/__init__.py`
- Create: `projects/management/commands/send_reminders.py`
- Create: `projects/management/commands/setup_telegram_webhook.py`
- Test: `tests/test_p15_telegram_reminders.py`

- [ ] **Step 1: Write reminder tests**

Create `tests/test_p15_telegram_reminders.py`:

```python
"""P15: Reminder management command tests."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts.models import Membership, Organization, TelegramBinding, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import (
    Contact,
    Interview,
    Notification,
    Project,
    Submission,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


@pytest.fixture
def binding(user):
    return TelegramBinding.objects.create(
        user=user, chat_id="12345", is_active=True, verified_at=timezone.now()
    )


@pytest.fixture
def client_obj(org):
    return Client.objects.create(name="Acme", organization=org)


@pytest.fixture
def project(org, client_obj, user):
    return Project.objects.create(
        client=client_obj, organization=org,
        title="Test Project", created_by=user,
    )


@pytest.fixture
def candidate(org):
    return Candidate.objects.create(name="홍길동", owned_by=org)


class TestSendReminders:
    @patch("projects.services.notification.send_notification")
    def test_recontact_reminder(self, mock_send, binding, project, candidate, user):
        mock_send.return_value = True
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            result=Contact.Result.RESERVED,
            next_contact_date=date.today(),
            locked_until=timezone.now() + timedelta(days=1),
        )
        call_command("send_reminders")
        # Should create a Notification
        assert Notification.objects.filter(
            type=Notification.Type.REMINDER
        ).exists()

    @patch("projects.services.notification.send_notification")
    def test_lock_expiry_reminder(self, mock_send, binding, project, candidate, user):
        mock_send.return_value = True
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            result=Contact.Result.RESERVED,
            locked_until=timezone.now() + timedelta(days=1),
        )
        call_command("send_reminders")
        assert Notification.objects.filter(
            type=Notification.Type.REMINDER,
        ).exists()

    @patch("projects.services.notification.send_notification")
    def test_submission_review_reminder(self, mock_send, binding, project, candidate, user):
        mock_send.return_value = True
        Submission.objects.create(
            project=project, candidate=candidate, consultant=user,
            status=Submission.Status.SUBMITTED,
            submitted_at=timezone.now() - timedelta(days=3),
        )
        call_command("send_reminders")
        assert Notification.objects.filter(
            type=Notification.Type.REMINDER,
        ).exists()

    @patch("projects.services.notification.send_notification")
    def test_interview_tomorrow_reminder(self, mock_send, binding, project, candidate, user):
        mock_send.return_value = True
        sub = Submission.objects.create(
            project=project, candidate=candidate, consultant=user,
            status=Submission.Status.PASSED,
        )
        Interview.objects.create(
            submission=sub, round=1,
            scheduled_at=timezone.now() + timedelta(days=1),
            type=Interview.Type.IN_PERSON,
        )
        call_command("send_reminders")
        assert Notification.objects.filter(
            type=Notification.Type.REMINDER,
        ).exists()

    @patch("projects.services.notification.send_notification")
    def test_no_reminders_when_nothing_due(self, mock_send, binding, project):
        mock_send.return_value = True
        call_command("send_reminders")
        assert not Notification.objects.filter(
            type=Notification.Type.REMINDER,
        ).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_reminders.py -v --no-header 2>&1 | head -20`
Expected: FAIL (command not found)

- [ ] **Step 3: Create package init files**

Create `projects/management/__init__.py` and `projects/management/commands/__init__.py` (both empty files).

- [ ] **Step 4: Create send_reminders command**

Create `projects/management/commands/send_reminders.py`:

```python
"""Generate and send daily reminder notifications via Telegram."""

from __future__ import annotations

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from projects.models import Contact, Interview, Notification, Submission
from projects.services.notification import send_notification
from projects.telegram.formatters import format_reminder


class Command(BaseCommand):
    help = "Generate and send daily reminder notifications"

    def handle(self, *args, **options):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        now = timezone.now()
        total_sent = 0

        # 1. Recontact reminders
        recontacts = Contact.objects.filter(
            next_contact_date=today,
            result=Contact.Result.RESERVED,
        ).select_related("consultant", "candidate", "project")

        for contact in recontacts:
            if not contact.consultant:
                continue
            notif = Notification.objects.create(
                recipient=contact.consultant,
                type=Notification.Type.REMINDER,
                title="재컨택 예정",
                body=f"{contact.candidate.name} - {contact.project.title}",
            )
            text = format_reminder(
                reminder_type="recontact",
                details=f"{contact.candidate.name} - {contact.project.title}",
            )
            if send_notification(notif, text=text):
                total_sent += 1

        # 2. Lock expiry reminders (tomorrow)
        lock_expiring = Contact.objects.filter(
            locked_until__date=tomorrow,
            result=Contact.Result.RESERVED,
        ).select_related("consultant", "candidate", "project")

        for contact in lock_expiring:
            if not contact.consultant:
                continue
            notif = Notification.objects.create(
                recipient=contact.consultant,
                type=Notification.Type.REMINDER,
                title="잠금 만료 임박",
                body=f"{contact.candidate.name} - {contact.project.title}",
            )
            text = format_reminder(
                reminder_type="lock_expiry",
                details=f"{contact.candidate.name} - {contact.project.title} (만료: {contact.locked_until:%m/%d})",
            )
            if send_notification(notif, text=text):
                total_sent += 1

        # 3. Submission review pending 2+ days
        stale_submissions = Submission.objects.filter(
            status=Submission.Status.SUBMITTED,
            submitted_at__lte=now - timedelta(days=2),
            client_feedback="",
        ).select_related("consultant", "candidate", "project")

        for sub in stale_submissions:
            if not sub.consultant:
                continue
            notif = Notification.objects.create(
                recipient=sub.consultant,
                type=Notification.Type.REMINDER,
                title="서류 검토 대기",
                body=f"{sub.candidate.name} - {sub.project.title} (제출: {sub.submitted_at:%m/%d})",
            )
            text = format_reminder(
                reminder_type="submission_review",
                details=f"{sub.candidate.name} - {sub.project.title} (제출: {sub.submitted_at:%m/%d})",
            )
            if send_notification(notif, text=text):
                total_sent += 1

        # 4. Interview tomorrow
        tomorrow_interviews = Interview.objects.filter(
            scheduled_at__date=tomorrow,
            result=Interview.Result.PENDING,
        ).select_related("submission__consultant", "submission__candidate", "submission__project")

        for interview in tomorrow_interviews:
            consultant = interview.submission.consultant
            if not consultant:
                continue
            candidate = interview.submission.candidate
            project = interview.submission.project
            notif = Notification.objects.create(
                recipient=consultant,
                type=Notification.Type.REMINDER,
                title="내일 면접",
                body=f"{candidate.name} - {project.title} ({interview.scheduled_at:%H:%M})",
            )
            text = format_reminder(
                reminder_type="interview_tomorrow",
                details=f"{candidate.name} - {project.title}\n시간: {interview.scheduled_at:%H:%M}\n장소: {interview.location or '미정'}",
            )
            if send_notification(notif, text=text):
                total_sent += 1

        self.stdout.write(
            self.style.SUCCESS(f"Sent {total_sent} reminder(s)")
        )
```

- [ ] **Step 5: Create setup_telegram_webhook command**

Create `projects/management/commands/setup_telegram_webhook.py`:

```python
"""Register Telegram webhook URL with the Bot API."""

from __future__ import annotations

import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Register the Telegram Bot webhook URL"

    def handle(self, *args, **options):
        from projects.telegram.bot import get_bot

        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            raise CommandError("TELEGRAM_BOT_TOKEN is not configured")

        site_url = settings.SITE_URL
        secret = settings.TELEGRAM_WEBHOOK_SECRET
        webhook_url = f"{site_url}/telegram/webhook/"

        bot = get_bot()

        async def _setup():
            result = await bot.set_webhook(
                url=webhook_url,
                secret_token=secret if secret else None,
            )
            return result

        success = asyncio.run(_setup())

        if success:
            self.stdout.write(
                self.style.SUCCESS(f"Webhook registered: {webhook_url}")
            )
        else:
            raise CommandError("Failed to register webhook")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_reminders.py -v --no-header`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add projects/management/ tests/test_p15_telegram_reminders.py
git commit -m "feat(p15): add send_reminders and setup_telegram_webhook management commands"
```

---

## Task 9: Full Integration Test + Existing Test Regression

- [ ] **Step 1: Run all P15 tests together**

Run: `cd /home/work/synco && uv run pytest tests/test_p15_telegram_*.py -v --no-header`
Expected: All tests PASS

- [ ] **Step 2: Run full test suite to check for regressions**

Run: `cd /home/work/synco && uv run pytest -v --no-header 2>&1 | tail -30`
Expected: All existing tests still pass. No regressions.

- [ ] **Step 3: Run linter**

Run: `cd /home/work/synco && uv run ruff check projects/telegram/ projects/services/notification.py projects/views_telegram.py projects/urls_telegram.py projects/management/ tests/test_p15_telegram_*.py`
Expected: No errors

- [ ] **Step 4: Run formatter**

Run: `cd /home/work/synco && uv run ruff format projects/telegram/ projects/services/notification.py projects/views_telegram.py projects/urls_telegram.py projects/management/ tests/test_p15_telegram_*.py`

- [ ] **Step 5: Run migration check**

Run: `cd /home/work/synco && uv run python manage.py makemigrations --check --dry-run`
Expected: No changes detected

- [ ] **Step 6: Final commit if any formatting changes**

```bash
git add -A
git commit -m "style(p15): apply ruff formatting to telegram integration"
```

---

## Implementation Order

Execute tasks 1 through 9 in order. Each task builds on the previous:

| Task | Dependency | Summary |
|------|-----------|---------|
| 1 | None | Dependencies + settings |
| 2 | Task 1 | Models + migrations |
| 3 | Task 1 | Bot init + auth module |
| 4 | Task 3 | Keyboards + formatters |
| 5 | Task 2, 3 | Notification service |
| 6 | Task 4, 5 | Callback handlers |
| 7 | Task 3, 5, 6 | Views + URLs + template |
| 8 | Task 5 | Management commands (reminders + webhook setup) |
| 9 | All | Integration test + regression check |
