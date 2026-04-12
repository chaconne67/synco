# t13: 설정 탭 URL + 뷰 통합

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 분산된 설정 페이지(프로필, Gmail, 텔레그램, 알림)를 `/accounts/settings/` 아래 탭 URL로 통합하고, 각 탭에 대응하는 뷰를 추가한다.

**Design spec:** `docs/forge/headhunting-onboarding/t13/design-spec.md`

**depends_on:** t11, t12

---

## Changes from Tempering

| Issue | Severity | Resolution |
|-------|----------|------------|
| R1-01: Onboarding URLs deleted from urlpatterns | CRITICAL | Step 3 changed from full replace to append-only — preserves invite/pending/rejected routes |
| R1-02: Missing templates cause TemplateDoesNotExist | CRITICAL | Added Step 4 to create stub templates so tests pass; full templates deferred to t14 |
| R1-03: Root URL home duplicated | CRITICAL | Removed `path("", views.home, name="home")` from Step 3 |
| R1-04: Tests too weak | CRITICAL | Added `assertTemplateUsed` and HTMX partial check to tests |

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `accounts/urls.py` | 수정 | 설정 탭 URL 추가 |
| `accounts/views.py` | 수정 | 설정 탭 뷰 (settings_page 수정, settings_profile/email/telegram/notify 추가) |
| `accounts/templates/accounts/partials/settings_email.html` | 생성 | 이메일 탭 스텁 템플릿 (t14에서 완성) |
| `accounts/templates/accounts/partials/settings_telegram.html` | 생성 | 텔레그램 탭 스텁 템플릿 (t14에서 완성) |
| `accounts/templates/accounts/partials/settings_notify.html` | 생성 | 알림 탭 스텁 템플릿 (t14에서 완성) |
| `projects/views_telegram.py` | 수정 | `telegram_bind_partial` 뷰 추가 |
| `projects/urls_telegram.py` | 수정 | 파셜 URL 추가 |
| `tests/accounts/test_settings_tabs.py` | 생성 | 설정 탭 통합 테스트 |

---

- [ ] **Step 1: Write failing tests for settings tab views**

```python
# tests/accounts/test_settings_tabs.py
import pytest
from django.test import Client as TestClient
from django.contrib.auth import get_user_model

from accounts.models import Membership, Organization

User = get_user_model()


@pytest.fixture
def active_user(db):
    org = Organization.objects.create(name="Test Org")
    user = User.objects.create_user(username="tabuser", password="pass")
    Membership.objects.create(user=user, organization=org, status="active")
    return user


@pytest.mark.django_db
class TestSettingsRedirect:
    def test_settings_redirects_to_profile(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/")
        assert response.status_code == 302
        assert response.url == "/accounts/settings/profile/"


@pytest.mark.django_db
class TestSettingsProfileTab:
    def test_profile_tab_returns_200(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/profile/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]

    def test_profile_tab_htmx_returns_partial(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get(
            "/accounts/settings/profile/",
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        assert "accounts/partials/settings_content.html" in [
            t.name for t in response.templates
        ]
        # HTMX partial should not contain full base layout
        content = response.content.decode()
        assert "<html" not in content


@pytest.mark.django_db
class TestSettingsEmailTab:
    def test_email_tab_returns_200(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/email/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]


@pytest.mark.django_db
class TestSettingsTelegramTab:
    def test_telegram_tab_returns_200(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/telegram/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]


@pytest.mark.django_db
class TestSettingsNotifyTab:
    def test_notify_tab_returns_200(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/notify/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]

    def test_notify_tab_post_saves_preferences(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.post(
            "/accounts/settings/notify/",
            {
                "contact_result_web": "on",
                "contact_result_telegram": "",
                "recommendation_feedback_web": "on",
                "recommendation_feedback_telegram": "on",
                "project_approval_web": "on",
                "project_approval_telegram": "",
                "newsfeed_update_web": "",
                "newsfeed_update_telegram": "",
            },
        )
        assert response.status_code == 200
        from accounts.models import NotificationPreference
        pref = NotificationPreference.objects.get(user=active_user)
        assert pref.preferences["contact_result"]["telegram"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_settings_tabs.py -v`
Expected: FAIL — URL not found, views not defined

- [ ] **Step 3: Update accounts/urls.py — add settings tab URLs**

Add settings tab URLs to the existing urlpatterns. **Keep all existing routes** (including onboarding). Do NOT add a root `home` path (already in `main/urls.py`).

```python
from django.urls import path

from . import views

urlpatterns = [
    # Note: home is now in main/urls.py as root entry point
    path("accounts/login/", views.login_page, name="login"),
    path("accounts/kakao/login/", views.kakao_login, name="kakao_login"),
    path("accounts/kakao/callback/", views.kakao_callback, name="kakao_callback"),
    # Settings tabs
    path("accounts/settings/", views.settings_page, name="settings"),
    path("accounts/settings/profile/", views.settings_profile, name="settings_profile"),
    path("accounts/settings/email/", views.settings_email, name="settings_email"),
    path("accounts/settings/telegram/", views.settings_telegram, name="settings_telegram"),
    path("accounts/settings/notify/", views.settings_notify, name="settings_notify"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    # Onboarding
    path("accounts/invite/", views.invite_code_page, name="invite_code"),
    path("accounts/pending/", views.pending_approval_page, name="pending_approval"),
    path("accounts/rejected/", views.rejected_page, name="rejected"),
    # P18: Gmail integration (keep existing URLs for OAuth flow)
    path("accounts/email/connect/", views.email_connect, name="email_connect"),
    path("accounts/email/callback/", views.email_oauth_callback, name="email_callback"),
    path("accounts/email/settings/", views.email_settings, name="email_settings"),
    path("accounts/email/disconnect/", views.email_disconnect, name="email_disconnect"),
]
```

- [ ] **Step 4: Create stub templates for settings tabs**

These are minimal stubs so views render without `TemplateDoesNotExist`. Full implementations come in t14.

**`accounts/templates/accounts/partials/settings_email.html`:**
```html
<div id="settings-tab-email">
  <p class="text-gray-400 text-[15px]">이메일 설정 (준비 중)</p>
</div>
```

**`accounts/templates/accounts/partials/settings_telegram.html`:**
```html
<div id="settings-tab-telegram">
  <p class="text-gray-400 text-[15px]">텔레그램 설정 (준비 중)</p>
</div>
```

**`accounts/templates/accounts/partials/settings_notify.html`:**
```html
<div id="settings-tab-notify">
  <p class="text-gray-400 text-[15px]">알림 설정 (준비 중)</p>
</div>
```

- [ ] **Step 5: Update accounts/views.py — modify settings_page, add tab views**

Modify `settings_page` to redirect to profile tab:

```python
@login_required
def settings_page(request):
    return redirect("settings_profile")
```

Add new tab views after `settings_page`:

```python
@login_required
def settings_profile(request):
    """GET /accounts/settings/profile/ — Profile tab."""
    if getattr(request, "htmx", None):
        return render(request, "accounts/partials/settings_content.html", {"active_tab": "profile"})
    return render(request, "accounts/settings.html", {"active_tab": "profile"})


@login_required
def settings_email(request):
    """GET /accounts/settings/email/ — Email tab."""
    from .models import EmailMonitorConfig

    config = EmailMonitorConfig.objects.filter(user=request.user).first()
    context = {"config": config, "active_tab": "email"}

    if getattr(request, "htmx", None):
        return render(request, "accounts/partials/settings_email.html", context)
    return render(request, "accounts/settings.html", {
        **context,
        "tab_template": "accounts/partials/settings_email.html",
    })


@login_required
def settings_telegram(request):
    """GET /accounts/settings/telegram/ — Telegram tab."""
    from .models import TelegramBinding

    try:
        binding = TelegramBinding.objects.get(user=request.user)
        is_bound = binding.is_active
        verified_at = binding.verified_at
    except TelegramBinding.DoesNotExist:
        is_bound = False
        verified_at = None

    context = {"is_bound": is_bound, "verified_at": verified_at, "active_tab": "telegram"}

    if getattr(request, "htmx", None):
        return render(request, "accounts/partials/settings_telegram.html", context)
    return render(request, "accounts/settings.html", {
        **context,
        "tab_template": "accounts/partials/settings_telegram.html",
    })


@login_required
def settings_notify(request):
    """GET/POST /accounts/settings/notify/ — Notification preferences tab."""
    from .forms import NotificationPreferenceForm
    from .models import NotificationPreference

    pref, _created = NotificationPreference.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = NotificationPreferenceForm(request.POST)
        if form.is_valid():
            pref.preferences = form.to_preferences()
            pref.save(update_fields=["preferences", "updated_at"])

    form = NotificationPreferenceForm()
    form.load_from_preferences(pref.preferences)

    context = {"form": form, "active_tab": "notify"}

    if getattr(request, "htmx", None):
        return render(request, "accounts/partials/settings_notify.html", context)
    return render(request, "accounts/settings.html", {
        **context,
        "tab_template": "accounts/partials/settings_notify.html",
    })
```

Also update `email_oauth_callback` redirect to point to new settings email tab:

```python
# In email_oauth_callback, change the final redirect:
    return redirect(reverse("settings_email"))
```

- [ ] **Step 6: Add telegram_bind_partial to projects/views_telegram.py**

Add a new view that reuses the bind logic but renders the settings tab partial:

```python
@login_required
def telegram_bind_partial(request):
    """Settings tab partial for telegram binding. Reuses bind logic."""
    template = "accounts/partials/settings_telegram.html"

    if request.method == "POST":
        user = request.user

        # Invalidate previous codes
        TelegramVerification.objects.filter(
            user=user,
            consumed=False,
        ).update(consumed=True)

        code = None
        for _ in range(3):
            candidate_code = "".join(random.choices(string.digits, k=6))
            collision = TelegramVerification.objects.filter(
                code=candidate_code,
                consumed=False,
                expires_at__gt=timezone.now(),
            ).exists()
            if not collision:
                code = candidate_code
                break

        if code is None:
            return render(
                request,
                template,
                {"error": "코드 생성에 실패했습니다. 다시 시도해주세요.", "active_tab": "telegram"},
            )

        TelegramVerification.objects.create(
            user=user,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        try:
            binding = TelegramBinding.objects.get(user=user)
            is_bound = binding.is_active
        except TelegramBinding.DoesNotExist:
            is_bound = False

        return render(
            request,
            template,
            {"code": code, "is_bound": is_bound, "expires_minutes": 5, "active_tab": "telegram"},
        )

    # GET
    try:
        binding = TelegramBinding.objects.get(user=request.user)
        is_bound = binding.is_active
        verified_at = binding.verified_at
    except TelegramBinding.DoesNotExist:
        is_bound = False
        verified_at = None

    return render(
        request,
        template,
        {"is_bound": is_bound, "verified_at": verified_at, "active_tab": "telegram"},
    )
```

- [ ] **Step 7: Add partial URL to projects/urls_telegram.py**

Add to `urlpatterns`:

```python
    path("settings-partial/", views_telegram.telegram_bind_partial, name="bind_partial"),
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/accounts/test_settings_tabs.py -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add accounts/urls.py accounts/views.py accounts/templates/ projects/views_telegram.py projects/urls_telegram.py tests/accounts/
git commit -m "feat(accounts): add settings tab views and URLs for profile/email/telegram/notify"
```

<!-- forge:t13:impl-plan:complete:2026-04-12T23:30:00+09:00 -->
