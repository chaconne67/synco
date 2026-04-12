# t18: email_disconnect 리다이렉트 수정 + 최종 통합 테스트

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이메일 관련 뷰의 리다이렉트가 새 설정 탭 URL을 사용하는지 검증하고, 타겟 테스트를 추가하여 2단계 통합의 회귀를 방지한다.

**Design spec:** `docs/forge/headhunting-onboarding/t18/design-spec.md`

**depends_on:** t13, t14

---

## Changes from Tempering

| Issue | Severity | Resolution |
|-------|----------|------------|
| I1: Step 1 is a no-op (already implemented) | CRITICAL | ACCEPTED — Convert to verification + regression test (email_disconnect already redirects to settings_email) |
| I2: Step 2 targets wrong view, introduces duplicate logic | CRITICAL | ACCEPTED — Remove Step 2 entirely (settings_email already handles HTMX POST) |
| I3: Verification plan too weak | CRITICAL | ACCEPTED — Add targeted tests before full suite run |
| I4: Duplicate save logic drift | MINOR | ACCEPTED — Note discrepancy, defer consolidation to future task |

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `tests/accounts/test_email_views.py` | 생성 | email_disconnect redirect, email_settings backward compat, settings_email HTMX POST 테스트 |

---

- [ ] **Step 1: Verify email_disconnect redirect (no code change needed)**

Verify that `accounts/views.py` line ~420 already has:
```python
    return redirect(reverse("settings_email"))
```

This was already implemented in t13. No code change required — the regression test in Step 2 will protect this.

- [ ] **Step 2: Add targeted integration tests**

Create `tests/accounts/test_email_views.py`:

```python
import pytest
from django.test import Client as TestClient
from django.contrib.auth import get_user_model

from accounts.models import Membership, Organization

User = get_user_model()


@pytest.fixture
def active_user(db):
    org = Organization.objects.create(name="Test Org")
    user = User.objects.create_user(username="emailuser", password="pass")
    Membership.objects.create(user=user, organization=org, status="active")
    return user


@pytest.mark.django_db
class TestEmailDisconnect:
    """Verify email_disconnect redirects to settings_email tab."""

    def test_disconnect_redirects_to_settings_email(self, active_user):
        """email_disconnect should redirect to /accounts/settings/email/."""
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/email/disconnect/")
        assert response.status_code == 302
        assert response.url == "/accounts/settings/email/"


@pytest.mark.django_db
class TestLegacyEmailSettings:
    """Verify legacy email_settings page backward compatibility."""

    def test_legacy_email_settings_returns_full_page(self, active_user):
        """GET /accounts/email/settings/ returns email_settings.html (full page)."""
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/email/settings/")
        assert response.status_code == 200
        assert "accounts/email_settings.html" in [t.name for t in response.templates]

    def test_legacy_email_settings_post_returns_full_page(self, active_user):
        """POST to legacy email_settings returns full page (not partial)."""
        client = TestClient()
        client.force_login(active_user)
        response = client.post(
            "/accounts/email/settings/",
            {"filter_from": "test@example.com", "is_active": "on"},
        )
        assert response.status_code == 200
        assert "accounts/email_settings.html" in [t.name for t in response.templates]


@pytest.mark.django_db
class TestSettingsEmailHTMX:
    """Verify settings_email tab handles HTMX POST with partial response."""

    def test_settings_email_htmx_post_returns_partial(self, active_user):
        """HTMX POST to settings_email returns partial template."""
        from accounts.models import EmailMonitorConfig

        EmailMonitorConfig.objects.create(
            user=active_user,
            gmail_credentials=b"",
            is_active=True,
        )
        client = TestClient()
        client.force_login(active_user)
        response = client.post(
            "/accounts/settings/email/",
            {"filter_from": "test@example.com", "is_active": "on"},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="settings-content",
        )
        assert response.status_code == 200
        assert "accounts/partials/settings_email.html" in [
            t.name for t in response.templates
        ]
        content = response.content.decode()
        assert "<html" not in content

    def test_settings_email_full_page_get(self, active_user):
        """Full page GET to settings_email renders settings.html shell."""
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/email/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS (old + new, including new test_email_views.py)

- [ ] **Step 4: Commit**

```bash
git add tests/accounts/test_email_views.py
git commit -m "test(accounts): add email disconnect redirect and settings integration tests"
```

<!-- forge:t18:impl-plan:complete:2026-04-12T20:15:00+09:00 -->
