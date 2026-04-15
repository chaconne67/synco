# 통합 설정 + 조직 관리 구현 계획 (Plan 2/3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 분산된 설정 페이지(프로필, Gmail, 텔레그램, 알림)를 단일 URL 아래 탭으로 통합하고, owner용 조직/멤버/초대코드 관리 UI를 구축한다.

**Architecture:** `/accounts/settings/` 아래에 HTMX 탭 전환 방식(프로젝트 상세 `detail_tab_bar.html` 패턴과 동일)으로 프로필/이메일/텔레그램/알림 탭을 통합한다. `/org/` 아래에 조직 정보/멤버 관리/초대코드 관리 탭을 구축한다. `NotificationPreference` 모델을 추가하고, `accounts/forms.py`에 폼 클래스를 생성한다. 사이드바에 owner 전용 "조직 관리" 메뉴를 추가한다.

**Tech Stack:** Django 5.2, HTMX, Tailwind CSS, pytest

**Design spec:** `docs/forge/headhunting-onboarding/phase2/design-spec.md`

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `accounts/models.py` | 수정 | `NotificationPreference` 모델 추가 |
| `accounts/forms.py` | 생성 | `OrganizationForm`, `InviteCodeCreateForm`, `NotificationPreferenceForm` |
| `accounts/views.py` | 수정 | 설정 탭 뷰 (settings_page 수정, settings_profile/email/telegram/notify 추가) |
| `accounts/views_org.py` | 생성 | 조직 관리 뷰 (org_redirect, org_info, org_members, org_invites 등) |
| `accounts/urls.py` | 수정 | 설정 탭 URL 추가 |
| `accounts/urls_org.py` | 생성 | `/org/` URL 구조 |
| `accounts/templates/accounts/settings.html` | 수정 | 탭 바 + `#settings-content` 컨테이너 구조로 변경 |
| `accounts/templates/accounts/partials/settings_tab_bar.html` | 생성 | 설정 탭 바 (프로필/이메일/텔레그램/알림) |
| `accounts/templates/accounts/partials/settings_content.html` | 수정 | 프로필 탭 파셜 (알림 섹션 제거) |
| `accounts/templates/accounts/partials/settings_email.html` | 생성 | 이메일 탭 파셜 (기존 email_settings_content.html 재활용) |
| `accounts/templates/accounts/partials/settings_telegram.html` | 생성 | 텔레그램 탭 파셜 |
| `accounts/templates/accounts/partials/settings_notify.html` | 생성 | 알림 설정 탭 파셜 |
| `accounts/templates/accounts/org_base.html` | 생성 | 조직 관리 베이스 (탭 바 + `#org-content`) |
| `accounts/templates/accounts/partials/org_tab_bar.html` | 생성 | 조직 관리 탭 바 (정보/멤버/초대코드) |
| `accounts/templates/accounts/partials/org_info.html` | 생성 | 조직 정보 탭 파셜 |
| `accounts/templates/accounts/partials/org_members.html` | 생성 | 멤버 관리 탭 파셜 |
| `accounts/templates/accounts/partials/org_invites.html` | 생성 | 초대코드 관리 탭 파셜 |
| `projects/views_telegram.py` | 수정 | `telegram_bind_partial` 뷰 추가 |
| `projects/urls_telegram.py` | 수정 | 파셜 URL 추가 |
| `templates/common/nav_sidebar.html` | 수정 | "조직 관리" 메뉴 추가 (owner 조건부) |
| `templates/common/nav_bottom.html` | 수정 | 모바일 "조직 관리" 추가 (owner 조건부) |
| `main/urls.py` | 수정 | `/org/` URL include 추가 |
| `tests/accounts/test_settings_tabs.py` | 생성 | 설정 탭 통합 테스트 |
| `tests/accounts/test_notification_pref.py` | 생성 | NotificationPreference 모델 테스트 |
| `tests/accounts/test_org_management.py` | 생성 | 조직 관리 뷰 테스트 |

---

### Task 1: NotificationPreference 모델 추가

**Files:**
- Modify: `accounts/models.py`
- Create: `tests/accounts/test_notification_pref.py`

- [ ] **Step 1: Write failing test for NotificationPreference model**

```python
# tests/accounts/test_notification_pref.py
import pytest
from django.contrib.auth import get_user_model

from accounts.models import NotificationPreference

User = get_user_model()


DEFAULT_PREFS = {
    "contact_result": {"web": True, "telegram": True},
    "recommendation_feedback": {"web": True, "telegram": True},
    "project_approval": {"web": True, "telegram": True},
    "newsfeed_update": {"web": True, "telegram": False},
}


@pytest.mark.django_db
class TestNotificationPreference:
    def test_create_default_preferences(self):
        user = User.objects.create_user(username="np1", password="pass")
        pref = NotificationPreference.objects.create(user=user)
        assert pref.preferences == DEFAULT_PREFS

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
        with pytest.raises(Exception):
            NotificationPreference.objects.create(user=user)

    def test_get_or_create_defaults(self):
        user = User.objects.create_user(username="np4", password="pass")
        pref, created = NotificationPreference.objects.get_or_create(user=user)
        assert created is True
        assert pref.preferences == DEFAULT_PREFS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_notification_pref.py -v`
Expected: FAIL — `ImportError: cannot import name 'NotificationPreference'`

- [ ] **Step 3: Add NotificationPreference model to accounts/models.py**

Add after the `EmailMonitorConfig` class at the end of the file:

```python
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
Expected: All 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add accounts/models.py accounts/admin.py accounts/migrations/ tests/accounts/
git commit -m "feat(accounts): add NotificationPreference model"
```

---

### Task 2: accounts/forms.py 생성

**Files:**
- Create: `accounts/forms.py`

- [ ] **Step 1: Create accounts/forms.py with all forms**

```python
# accounts/forms.py
from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator

from .models import InviteCode, NotificationPreference, Organization


class OrganizationForm(forms.ModelForm):
    """조직 정보 수정 폼 (owner용)."""

    class Meta:
        model = Organization
        fields = ["name", "logo"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "w-full px-3 py-2.5 text-[14px] border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent",
                    "placeholder": "조직명",
                }
            ),
            "logo": forms.ClearableFileInput(
                attrs={
                    "class": "block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100",
                }
            ),
        }


class InviteCodeCreateForm(forms.Form):
    """초대코드 생성 폼."""

    role = forms.ChoiceField(
        choices=[
            ("consultant", "Consultant"),
            ("viewer", "Viewer"),
        ],
        initial="consultant",
        widget=forms.Select(
            attrs={
                "class": "w-full px-3 py-2.5 text-[14px] border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent",
            }
        ),
    )
    max_uses = forms.IntegerField(
        initial=1,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        widget=forms.NumberInput(
            attrs={
                "class": "w-full px-3 py-2.5 text-[14px] border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent",
                "min": "1",
                "max": "100",
            }
        ),
    )
    expires_at = forms.DateTimeField(
        required=False,
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "w-full px-3 py-2.5 text-[14px] border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent",
            }
        ),
    )


class NotificationPreferenceForm(forms.Form):
    """알림 설정 폼. JSONField를 개별 체크박스로 분리."""

    # 새 컨택 결과
    contact_result_web = forms.BooleanField(required=False)
    contact_result_telegram = forms.BooleanField(required=False)
    # 추천 피드백
    recommendation_feedback_web = forms.BooleanField(required=False)
    recommendation_feedback_telegram = forms.BooleanField(required=False)
    # 프로젝트 승인 요청
    project_approval_web = forms.BooleanField(required=False)
    project_approval_telegram = forms.BooleanField(required=False)
    # 뉴스피드 업데이트
    newsfeed_update_web = forms.BooleanField(required=False)
    newsfeed_update_telegram = forms.BooleanField(required=False)

    def load_from_preferences(self, preferences: dict):
        """JSONField dict -> form initial values."""
        for key, channels in preferences.items():
            for channel, enabled in channels.items():
                field_name = f"{key}_{channel}"
                if field_name in self.fields:
                    self.initial[field_name] = enabled

    def to_preferences(self) -> dict:
        """Form cleaned_data -> JSONField dict."""
        return {
            "contact_result": {
                "web": self.cleaned_data.get("contact_result_web", True),
                "telegram": self.cleaned_data.get("contact_result_telegram", True),
            },
            "recommendation_feedback": {
                "web": self.cleaned_data.get("recommendation_feedback_web", True),
                "telegram": self.cleaned_data.get("recommendation_feedback_telegram", True),
            },
            "project_approval": {
                "web": self.cleaned_data.get("project_approval_web", True),
                "telegram": self.cleaned_data.get("project_approval_telegram", True),
            },
            "newsfeed_update": {
                "web": self.cleaned_data.get("newsfeed_update_web", True),
                "telegram": self.cleaned_data.get("newsfeed_update_telegram", False),
            },
        }
```

- [ ] **Step 2: Commit**

```bash
git add accounts/forms.py
git commit -m "feat(accounts): add OrganizationForm, InviteCodeCreateForm, NotificationPreferenceForm"
```

---

### Task 3: 설정 탭 URL + 뷰 통합

**Files:**
- Modify: `accounts/urls.py`
- Modify: `accounts/views.py`
- Modify: `projects/views_telegram.py`
- Modify: `projects/urls_telegram.py`
- Create: `tests/accounts/test_settings_tabs.py`

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

    def test_profile_tab_htmx_returns_partial(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get(
            "/accounts/settings/profile/",
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestSettingsEmailTab:
    def test_email_tab_returns_200(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/email/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestSettingsTelegramTab:
    def test_telegram_tab_returns_200(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/telegram/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestSettingsNotifyTab:
    def test_notify_tab_returns_200(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/notify/")
        assert response.status_code == 200

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

Replace the existing `accounts/settings/` path and add new paths:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
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
    # P18: Gmail integration (keep existing URLs for OAuth flow)
    path("accounts/email/connect/", views.email_connect, name="email_connect"),
    path("accounts/email/callback/", views.email_oauth_callback, name="email_callback"),
    path("accounts/email/settings/", views.email_settings, name="email_settings"),
    path("accounts/email/disconnect/", views.email_disconnect, name="email_disconnect"),
]
```

- [ ] **Step 4: Update accounts/views.py — modify settings_page, add tab views**

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

- [ ] **Step 5: Add telegram_bind_partial to projects/views_telegram.py**

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

- [ ] **Step 6: Add partial URL to projects/urls_telegram.py**

Add to `urlpatterns`:

```python
    path("settings-partial/", views_telegram.telegram_bind_partial, name="bind_partial"),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/accounts/test_settings_tabs.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add accounts/urls.py accounts/views.py projects/views_telegram.py projects/urls_telegram.py tests/accounts/
git commit -m "feat(accounts): add settings tab views and URLs for profile/email/telegram/notify"
```

---

### Task 4: 설정 탭 템플릿 구현

**Files:**
- Modify: `accounts/templates/accounts/settings.html`
- Create: `accounts/templates/accounts/partials/settings_tab_bar.html`
- Modify: `accounts/templates/accounts/partials/settings_content.html`
- Create: `accounts/templates/accounts/partials/settings_email.html`
- Create: `accounts/templates/accounts/partials/settings_telegram.html`
- Create: `accounts/templates/accounts/partials/settings_notify.html`

- [ ] **Step 1: Create settings_tab_bar.html**

```html
{# accounts/templates/accounts/partials/settings_tab_bar.html #}
<div class="border-b border-gray-200 flex gap-0 overflow-x-auto -mx-4 lg:-mx-8 px-4 lg:px-8">
  {% with active=active_tab|default:"profile" %}

  <button hx-get="{% url 'settings_profile' %}"
          hx-target="#settings-content"
          hx-push-url="true"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'profile' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    프로필
  </button>

  <button hx-get="{% url 'settings_email' %}"
          hx-target="#settings-content"
          hx-push-url="true"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'email' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    이메일
  </button>

  <button hx-get="{% url 'settings_telegram' %}"
          hx-target="#settings-content"
          hx-push-url="true"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'telegram' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    텔레그램
  </button>

  <button hx-get="{% url 'settings_notify' %}"
          hx-target="#settings-content"
          hx-push-url="true"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'notify' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    알림
  </button>

  {% endwith %}
</div>
```

- [ ] **Step 2: Rewrite settings.html to use tab layout**

```html
{# accounts/templates/accounts/settings.html #}
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}

{% block title %}synco - 설정{% endblock %}

{% block content %}
<div class="p-4 lg:p-8 space-y-6">
  <!-- Page Header -->
  <div>
    <h1 class="text-heading font-bold">설정</h1>
  </div>

  <!-- Tab Bar -->
  {% include "accounts/partials/settings_tab_bar.html" %}

  <!-- Tab Content -->
  <div id="settings-content">
    {% if tab_template %}
      {% include tab_template %}
    {% else %}
      {% include "accounts/partials/settings_content.html" %}
    {% endif %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Update settings_content.html (profile tab) — remove notification section**

Remove the "알림" section (lines 31-36 of the current file). The resulting file keeps:
- 내 정보 section
- 앱 정보 section
- 로그아웃 link

```html
{# accounts/templates/accounts/partials/settings_content.html #}
{% load static %}

<!-- My Info -->
<section class="bg-white rounded-lg border border-gray-100 p-5">
  <h2 class="text-[15px] font-semibold text-gray-500 mb-4">내 정보</h2>

  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <span class="text-[15px] text-gray-500">이름</span>
      <span class="text-[15px] font-medium">{{ user.first_name|default:"-" }}</span>
    </div>
    <div class="flex items-center justify-between">
      <span class="text-[15px] text-gray-500">소속</span>
      <span class="text-[15px] font-medium">{{ user.company_name|default:"-" }}</span>
    </div>
    <div class="flex items-center justify-between">
      <span class="text-[15px] text-gray-500">전화번호</span>
      <span class="text-[15px] font-medium">{{ user.phone|default:"-" }}</span>
    </div>
  </div>
</section>

<!-- App Info -->
<section class="bg-white rounded-lg border border-gray-100 p-5">
  <h2 class="text-[15px] font-semibold text-gray-500 mb-4">앱 정보</h2>

  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <span class="text-[15px] text-gray-500">버전</span>
      <span class="text-[15px] text-gray-500">1.0.0</span>
    </div>
    <a href="/terms/" class="flex items-center justify-between group">
      <span class="text-[15px] text-gray-500 group-hover:text-gray-700">이용약관</span>
      <svg class="w-4 h-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
      </svg>
    </a>
    <a href="/privacy/" class="flex items-center justify-between group">
      <span class="text-[15px] text-gray-500 group-hover:text-gray-700">개인정보처리방침</span>
      <svg class="w-4 h-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
      </svg>
    </a>
  </div>
</section>

<!-- Logout -->
<div class="pt-2 pb-4">
  <a href="{% url 'logout' %}"
     class="block w-full text-center text-[15px] font-medium text-red-500 py-3 rounded-lg hover:bg-red-50 transition">
    로그아웃
  </a>
</div>
```

- [ ] **Step 4: Create settings_email.html (email tab partial)**

Reuses the content from `email_settings_content.html` but without the page header/back button:

```html
{# accounts/templates/accounts/partials/settings_email.html #}
{% load static %}

{% if config %}
  <!-- Connection Status -->
  <section class="bg-white rounded-lg border border-gray-100 p-5">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-[15px] font-semibold text-gray-500">Gmail 연결</h2>
      <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium
        {% if config.is_active %}bg-green-50 text-green-700{% else %}bg-gray-100 text-gray-500{% endif %}">
        <span class="w-1.5 h-1.5 rounded-full
          {% if config.is_active %}bg-green-500{% else %}bg-gray-400{% endif %}"></span>
        {% if config.is_active %}활성{% else %}비활성{% endif %}
      </span>
    </div>

    <div class="space-y-3 text-[14px] text-gray-500">
      {% if config.last_checked_at %}
        <div class="flex items-center justify-between">
          <span>마지막 확인</span>
          <span class="font-medium text-gray-700">{{ config.last_checked_at|date:"Y-m-d H:i" }}</span>
        </div>
      {% endif %}
    </div>
  </section>

  <!-- Filter Settings -->
  <section class="bg-white rounded-lg border border-gray-100 p-5">
    <h2 class="text-[15px] font-semibold text-gray-500 mb-4">필터 설정</h2>

    <form method="post"
          hx-post="{% url 'email_settings' %}"
          hx-target="#settings-content"
          hx-push-url="false">
      {% csrf_token %}
      <div class="space-y-4">
        <div>
          <label for="filter_from" class="block text-[14px] font-medium text-gray-700 mb-1.5">발신자 필터</label>
          <input type="text" name="filter_from" id="filter_from"
                 value="{{ config.filter_from|join:', ' }}"
                 placeholder="email1@example.com, email2@example.com"
                 class="w-full px-3 py-2.5 text-[14px] border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent">
          <p class="mt-1 text-[12px] text-gray-400">쉼표로 구분하여 입력하세요. 비워두면 모든 발신자의 이메일을 확인합니다.</p>
        </div>
        <div class="flex items-center justify-between">
          <label for="is_active" class="text-[14px] font-medium text-gray-700">모니터링 활성화</label>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" name="is_active" id="is_active"
                   {% if config.is_active %}checked{% endif %} class="sr-only peer">
            <div class="w-11 h-6 bg-gray-200 peer-focus:ring-2 peer-focus:ring-indigo-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
          </label>
        </div>
      </div>
      <div class="mt-6">
        <button type="submit" class="w-full py-2.5 text-[14px] font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition">설정 저장</button>
      </div>
    </form>
  </section>

  <!-- Disconnect -->
  <section class="bg-white rounded-lg border border-gray-100 p-5">
    <h2 class="text-[15px] font-semibold text-gray-500 mb-3">연결 해제</h2>
    <p class="text-[13px] text-gray-400 mb-4">Gmail 연결을 해제합니다. 이미 가져온 이력서는 유지됩니다.</p>
    <a href="{% url 'email_disconnect' %}"
       onclick="return confirm('Gmail 연결을 해제하시겠습니까?')"
       class="block w-full text-center py-2.5 text-[14px] font-medium text-red-500 border border-red-200 rounded-lg hover:bg-red-50 transition">
      Gmail 연결 해제
    </a>
  </section>

{% else %}
  <!-- Not Connected -->
  <section class="bg-white rounded-lg border border-gray-100 p-5">
    <div class="text-center py-8">
      <div class="w-16 h-16 mx-auto mb-4 bg-gray-50 rounded-full flex items-center justify-center">
        <svg class="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>
        </svg>
      </div>
      <h2 class="text-[16px] font-semibold text-gray-700 mb-2">Gmail 연결</h2>
      <p class="text-[14px] text-gray-400 mb-6 max-w-sm mx-auto">
        Gmail을 연결하면 이메일로 수신된 이력서를 자동으로 가져올 수 있습니다.
      </p>
      <a href="{% url 'email_connect' %}"
         class="inline-flex items-center gap-2 px-6 py-2.5 text-[14px] font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition">
        Gmail 계정 연결하기
      </a>
    </div>
  </section>
{% endif %}
```

- [ ] **Step 5: Create settings_telegram.html (telegram tab partial)**

```html
{# accounts/templates/accounts/partials/settings_telegram.html #}
{% load static %}

{% if message %}
<div class="mb-4 p-3 bg-green-50 text-green-700 rounded-lg text-sm">{{ message }}</div>
{% endif %}

{% if error %}
<div class="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">{{ error }}</div>
{% endif %}

{% if code %}
<section class="bg-white rounded-lg border border-gray-100 p-5">
  <div class="p-4 bg-blue-50 rounded-lg">
    <p class="text-sm text-gray-600 mb-2">텔레그램 Bot에 아래 코드를 보내주세요:</p>
    <p class="text-3xl font-mono font-bold text-center tracking-widest my-4">{{ code }}</p>
    <p class="text-xs text-gray-500 text-center">
      /start {{ code }} — {{ expires_minutes }}분 내 입력
    </p>
  </div>
</section>
{% endif %}

{% if is_bound %}
<section class="bg-white rounded-lg border border-gray-100 p-5">
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-[15px] font-semibold text-gray-500">텔레그램 연동</h2>
    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-50 text-green-700">
      <span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>
      연결됨
    </span>
  </div>
  {% if verified_at %}
  <p class="text-[13px] text-gray-400 mb-4">연동일: {{ verified_at|date:"Y-m-d H:i" }}</p>
  {% endif %}

  <div class="flex gap-3">
    <form method="post" action="{% url 'telegram:test' %}"
          hx-post="{% url 'telegram:test' %}"
          hx-target="#settings-content"
          class="flex-1">
      {% csrf_token %}
      <button type="submit"
        class="w-full px-4 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-[14px] font-medium transition">
        테스트 메시지 보내기
      </button>
    </form>
    <form method="post" action="{% url 'telegram:unbind' %}"
          hx-post="{% url 'telegram:unbind' %}"
          hx-target="#settings-content"
          class="flex-1">
      {% csrf_token %}
      <button type="submit"
        class="w-full px-4 py-2.5 border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50 text-[14px] font-medium transition">
        연동 해제
      </button>
    </form>
  </div>
</section>
{% else %}
<section class="bg-white rounded-lg border border-gray-100 p-5">
  <div class="text-center py-8">
    <div class="w-16 h-16 mx-auto mb-4 bg-gray-50 rounded-full flex items-center justify-center">
      <svg class="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>
      </svg>
    </div>
    <h2 class="text-[16px] font-semibold text-gray-700 mb-2">텔레그램 연결</h2>
    <p class="text-[14px] text-gray-400 mb-6 max-w-sm mx-auto">
      텔레그램을 연결하면 프로젝트 알림을 실시간으로 받을 수 있습니다.
    </p>
    <form method="post" action="{% url 'telegram:bind' %}"
          hx-post="{% url 'telegram:bind_partial' %}"
          hx-target="#settings-content">
      {% csrf_token %}
      <button type="submit"
        class="inline-flex items-center gap-2 px-6 py-2.5 text-[14px] font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition">
        텔레그램 연결하기
      </button>
    </form>
  </div>
</section>
{% endif %}
```

- [ ] **Step 6: Create settings_notify.html (notification tab partial)**

```html
{# accounts/templates/accounts/partials/settings_notify.html #}
{% load static %}

<section class="bg-white rounded-lg border border-gray-100 p-5">
  <h2 class="text-[15px] font-semibold text-gray-500 mb-4">알림 설정</h2>

  <form method="post"
        hx-post="{% url 'settings_notify' %}"
        hx-target="#settings-content"
        hx-push-url="false">
    {% csrf_token %}

    <div class="space-y-1">
      <!-- Header row -->
      <div class="grid grid-cols-3 gap-4 pb-2 border-b border-gray-100">
        <span class="text-[13px] font-medium text-gray-500">알림 유형</span>
        <span class="text-[13px] font-medium text-gray-500 text-center">웹</span>
        <span class="text-[13px] font-medium text-gray-500 text-center">텔레그램</span>
      </div>

      <!-- Contact result -->
      <div class="grid grid-cols-3 gap-4 py-3 border-b border-gray-50">
        <span class="text-[14px] text-gray-700">새 컨택 결과</span>
        <div class="text-center">
          <input type="checkbox" name="contact_result_web"
                 {% if form.initial.contact_result_web %}checked{% endif %}
                 class="w-4 h-4 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500">
        </div>
        <div class="text-center">
          <input type="checkbox" name="contact_result_telegram"
                 {% if form.initial.contact_result_telegram %}checked{% endif %}
                 class="w-4 h-4 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500">
        </div>
      </div>

      <!-- Recommendation feedback -->
      <div class="grid grid-cols-3 gap-4 py-3 border-b border-gray-50">
        <span class="text-[14px] text-gray-700">추천 피드백</span>
        <div class="text-center">
          <input type="checkbox" name="recommendation_feedback_web"
                 {% if form.initial.recommendation_feedback_web %}checked{% endif %}
                 class="w-4 h-4 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500">
        </div>
        <div class="text-center">
          <input type="checkbox" name="recommendation_feedback_telegram"
                 {% if form.initial.recommendation_feedback_telegram %}checked{% endif %}
                 class="w-4 h-4 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500">
        </div>
      </div>

      <!-- Project approval -->
      <div class="grid grid-cols-3 gap-4 py-3 border-b border-gray-50">
        <span class="text-[14px] text-gray-700">프로젝트 승인 요청</span>
        <div class="text-center">
          <input type="checkbox" name="project_approval_web"
                 {% if form.initial.project_approval_web %}checked{% endif %}
                 class="w-4 h-4 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500">
        </div>
        <div class="text-center">
          <input type="checkbox" name="project_approval_telegram"
                 {% if form.initial.project_approval_telegram %}checked{% endif %}
                 class="w-4 h-4 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500">
        </div>
      </div>

      <!-- Newsfeed update -->
      <div class="grid grid-cols-3 gap-4 py-3">
        <span class="text-[14px] text-gray-700">뉴스피드 업데이트</span>
        <div class="text-center">
          <input type="checkbox" name="newsfeed_update_web"
                 {% if form.initial.newsfeed_update_web %}checked{% endif %}
                 class="w-4 h-4 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500">
        </div>
        <div class="text-center">
          <input type="checkbox" name="newsfeed_update_telegram"
                 {% if form.initial.newsfeed_update_telegram %}checked{% endif %}
                 class="w-4 h-4 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500">
        </div>
      </div>
    </div>

    <div class="mt-6">
      <button type="submit"
              class="w-full py-2.5 text-[14px] font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition">
        설정 저장
      </button>
    </div>
  </form>
</section>
```

- [ ] **Step 7: Verify templates render correctly**

Run: `uv run pytest tests/accounts/test_settings_tabs.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add accounts/templates/
git commit -m "feat(accounts): add settings tab bar and tab partial templates"
```

---

### Task 5: 조직 관리 뷰 + URL + 테스트

**Files:**
- Create: `accounts/views_org.py`
- Create: `accounts/urls_org.py`
- Modify: `main/urls.py`
- Create: `tests/accounts/test_org_management.py`

- [ ] **Step 1: Write failing tests for org management views**

```python
# tests/accounts/test_org_management.py
import pytest
from django.test import Client as TestClient
from django.contrib.auth import get_user_model

from accounts.models import InviteCode, Membership, Organization

User = get_user_model()


@pytest.fixture
def owner_setup(db):
    org = Organization.objects.create(name="Test Org")
    owner = User.objects.create_user(username="owner1", password="pass")
    Membership.objects.create(user=owner, organization=org, role="owner", status="active")
    return owner, org


@pytest.fixture
def consultant_setup(db):
    org = Organization.objects.create(name="Test Org")
    consultant = User.objects.create_user(username="cons1", password="pass")
    Membership.objects.create(user=consultant, organization=org, role="consultant", status="active")
    return consultant, org


@pytest.mark.django_db
class TestOrgAccessControl:
    def test_owner_can_access_org(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        response = client.get("/org/")
        assert response.status_code == 302
        assert response.url == "/org/info/"

    def test_consultant_cannot_access_org(self, consultant_setup):
        consultant, org = consultant_setup
        client = TestClient()
        client.force_login(consultant)
        response = client.get("/org/info/")
        assert response.status_code == 403

    def test_anonymous_redirects_to_login(self):
        client = TestClient()
        response = client.get("/org/info/")
        assert response.status_code == 302
        assert "login" in response.url


@pytest.mark.django_db
class TestOrgInfo:
    def test_org_info_shows_org_data(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        response = client.get("/org/info/")
        assert response.status_code == 200
        assert "Test Org" in response.content.decode()

    def test_org_info_update(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        response = client.post("/org/info/", {"name": "Updated Org"})
        assert response.status_code == 200
        org.refresh_from_db()
        assert org.name == "Updated Org"


@pytest.mark.django_db
class TestOrgMembers:
    def test_members_list(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        response = client.get("/org/members/")
        assert response.status_code == 200
        assert "owner1" in response.content.decode()

    def test_approve_pending_member(self, owner_setup):
        owner, org = owner_setup
        pending_user = User.objects.create_user(username="pending1", password="pass")
        m = Membership.objects.create(
            user=pending_user, organization=org, role="consultant", status="pending"
        )
        client = TestClient()
        client.force_login(owner)
        response = client.post(f"/org/members/{m.pk}/approve/")
        m.refresh_from_db()
        assert m.status == "active"

    def test_reject_pending_member(self, owner_setup):
        owner, org = owner_setup
        pending_user = User.objects.create_user(username="pending2", password="pass")
        m = Membership.objects.create(
            user=pending_user, organization=org, role="consultant", status="pending"
        )
        client = TestClient()
        client.force_login(owner)
        response = client.post(f"/org/members/{m.pk}/reject/")
        m.refresh_from_db()
        assert m.status == "rejected"

    def test_change_role(self, owner_setup):
        owner, org = owner_setup
        member = User.objects.create_user(username="member1", password="pass")
        m = Membership.objects.create(
            user=member, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(owner)
        response = client.post(f"/org/members/{m.pk}/role/", {"role": "viewer"})
        m.refresh_from_db()
        assert m.role == "viewer"

    def test_cannot_change_owner_role(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        m = Membership.objects.get(user=owner)
        response = client.post(f"/org/members/{m.pk}/role/", {"role": "consultant"})
        assert response.status_code == 400
        m.refresh_from_db()
        assert m.role == "owner"

    def test_remove_member(self, owner_setup):
        owner, org = owner_setup
        member = User.objects.create_user(username="rem1", password="pass")
        m = Membership.objects.create(
            user=member, organization=org, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(owner)
        response = client.post(f"/org/members/{m.pk}/remove/")
        assert not Membership.objects.filter(pk=m.pk).exists()

    def test_cannot_remove_self(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        m = Membership.objects.get(user=owner)
        response = client.post(f"/org/members/{m.pk}/remove/")
        assert response.status_code == 400
        assert Membership.objects.filter(pk=m.pk).exists()


@pytest.mark.django_db
class TestOrgInvites:
    def test_invites_list(self, owner_setup):
        owner, org = owner_setup
        InviteCode.objects.create(organization=org, role="consultant", created_by=owner)
        client = TestClient()
        client.force_login(owner)
        response = client.get("/org/invites/")
        assert response.status_code == 200

    def test_create_invite_code(self, owner_setup):
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        response = client.post(
            "/org/invites/create/",
            {"role": "consultant", "max_uses": "5"},
        )
        assert InviteCode.objects.filter(organization=org, created_by=owner).exists()
        code = InviteCode.objects.filter(organization=org, created_by=owner).first()
        assert code.role == "consultant"
        assert code.max_uses == 5

    def test_deactivate_invite_code(self, owner_setup):
        owner, org = owner_setup
        code = InviteCode.objects.create(
            organization=org, role="consultant", created_by=owner
        )
        client = TestClient()
        client.force_login(owner)
        response = client.post(f"/org/invites/{code.pk}/deactivate/")
        code.refresh_from_db()
        assert code.is_active is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_org_management.py -v`
Expected: FAIL — URLs not found, views not defined

- [ ] **Step 3: Create accounts/views_org.py**

```python
# accounts/views_org.py
"""조직 관리 뷰 — owner 전용."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import InviteCodeCreateForm, OrganizationForm
from .helpers import _get_org
from .models import InviteCode, Membership


@login_required
@role_required("owner")
def org_redirect(request):
    """GET /org/ -> redirect to /org/info/."""
    return redirect("org_info")


@login_required
@role_required("owner")
def org_info(request):
    """GET/POST /org/info/ — 조직 정보 탭."""
    org = _get_org(request)
    form = OrganizationForm(instance=org)

    if request.method == "POST":
        form = OrganizationForm(request.POST, request.FILES, instance=org)
        if form.is_valid():
            form.save()

    context = {"org": org, "form": form, "active_tab": "info"}

    if getattr(request, "htmx", None):
        return render(request, "accounts/partials/org_info.html", context)
    return render(request, "accounts/org_base.html", {
        **context,
        "tab_template": "accounts/partials/org_info.html",
    })


@login_required
@role_required("owner")
def org_members(request):
    """GET /org/members/ — 멤버 관리 탭."""
    org = _get_org(request)
    members = Membership.objects.filter(organization=org).select_related("user").order_by(
        # pending first, then active, then rejected
        "status",
        "-created_at",
    )

    context = {"org": org, "members": members, "active_tab": "members"}

    if getattr(request, "htmx", None):
        return render(request, "accounts/partials/org_members.html", context)
    return render(request, "accounts/org_base.html", {
        **context,
        "tab_template": "accounts/partials/org_members.html",
    })


@login_required
@role_required("owner")
@require_POST
def org_member_approve(request, pk):
    """POST /org/members/<pk>/approve/ — 멤버 승인."""
    org = _get_org(request)
    membership = get_object_or_404(Membership, pk=pk, organization=org, status="pending")
    membership.status = "active"
    membership.save(update_fields=["status", "updated_at"])

    members = Membership.objects.filter(organization=org).select_related("user").order_by("status", "-created_at")
    return render(request, "accounts/partials/org_members.html", {
        "org": org, "members": members, "active_tab": "members",
        "message": f"{membership.user.first_name or membership.user.username}님이 승인되었습니다.",
    })


@login_required
@role_required("owner")
@require_POST
def org_member_reject(request, pk):
    """POST /org/members/<pk>/reject/ — 멤버 거절."""
    org = _get_org(request)
    membership = get_object_or_404(Membership, pk=pk, organization=org, status="pending")
    membership.status = "rejected"
    membership.save(update_fields=["status", "updated_at"])

    members = Membership.objects.filter(organization=org).select_related("user").order_by("status", "-created_at")
    return render(request, "accounts/partials/org_members.html", {
        "org": org, "members": members, "active_tab": "members",
        "message": f"{membership.user.first_name or membership.user.username}님의 가입이 거절되었습니다.",
    })


@login_required
@role_required("owner")
@require_POST
def org_member_role(request, pk):
    """POST /org/members/<pk>/role/ — 역할 변경."""
    org = _get_org(request)
    membership = get_object_or_404(Membership, pk=pk, organization=org, status="active")

    if membership.role == "owner":
        return HttpResponseBadRequest("owner 역할은 변경할 수 없습니다.")

    new_role = request.POST.get("role")
    if new_role not in ("consultant", "viewer"):
        return HttpResponseBadRequest("유효하지 않은 역할입니다.")

    membership.role = new_role
    membership.save(update_fields=["role", "updated_at"])

    members = Membership.objects.filter(organization=org).select_related("user").order_by("status", "-created_at")
    return render(request, "accounts/partials/org_members.html", {
        "org": org, "members": members, "active_tab": "members",
        "message": f"{membership.user.first_name or membership.user.username}님의 역할이 {new_role}로 변경되었습니다.",
    })


@login_required
@role_required("owner")
@require_POST
def org_member_remove(request, pk):
    """POST /org/members/<pk>/remove/ — 멤버 제거."""
    org = _get_org(request)
    membership = get_object_or_404(Membership, pk=pk, organization=org)

    # Cannot remove self
    if membership.user == request.user:
        return HttpResponseBadRequest("자기 자신을 제거할 수 없습니다.")

    # Cannot remove the only owner
    if membership.role == "owner":
        owner_count = Membership.objects.filter(
            organization=org, role="owner", status="active"
        ).count()
        if owner_count <= 1:
            return HttpResponseBadRequest("조직에 owner가 1명뿐이면 제거할 수 없습니다.")

    name = membership.user.first_name or membership.user.username
    membership.delete()

    members = Membership.objects.filter(organization=org).select_related("user").order_by("status", "-created_at")
    return render(request, "accounts/partials/org_members.html", {
        "org": org, "members": members, "active_tab": "members",
        "message": f"{name}님이 조직에서 제거되었습니다.",
    })


@login_required
@role_required("owner")
def org_invites(request):
    """GET /org/invites/ — 초대코드 관리 탭."""
    org = _get_org(request)
    codes = InviteCode.objects.filter(organization=org).order_by("-created_at")
    form = InviteCodeCreateForm()

    context = {"org": org, "codes": codes, "form": form, "active_tab": "invites"}

    if getattr(request, "htmx", None):
        return render(request, "accounts/partials/org_invites.html", context)
    return render(request, "accounts/org_base.html", {
        **context,
        "tab_template": "accounts/partials/org_invites.html",
    })


@login_required
@role_required("owner")
@require_POST
def org_invite_create(request):
    """POST /org/invites/create/ — 초대코드 생성."""
    org = _get_org(request)
    form = InviteCodeCreateForm(request.POST)

    if form.is_valid():
        InviteCode.objects.create(
            organization=org,
            role=form.cleaned_data["role"],
            max_uses=form.cleaned_data["max_uses"],
            expires_at=form.cleaned_data.get("expires_at"),
            created_by=request.user,
        )

    codes = InviteCode.objects.filter(organization=org).order_by("-created_at")
    form = InviteCodeCreateForm()
    return render(request, "accounts/partials/org_invites.html", {
        "org": org, "codes": codes, "form": form, "active_tab": "invites",
        "message": "초대코드가 생성되었습니다.",
    })


@login_required
@role_required("owner")
@require_POST
def org_invite_deactivate(request, pk):
    """POST /org/invites/<pk>/deactivate/ — 초대코드 비활성화."""
    org = _get_org(request)
    code = get_object_or_404(InviteCode, pk=pk, organization=org)
    code.is_active = False
    code.save(update_fields=["is_active", "updated_at"])

    codes = InviteCode.objects.filter(organization=org).order_by("-created_at")
    form = InviteCodeCreateForm()
    return render(request, "accounts/partials/org_invites.html", {
        "org": org, "codes": codes, "form": form, "active_tab": "invites",
        "message": "초대코드가 비활성화되었습니다.",
    })
```

- [ ] **Step 4: Create accounts/urls_org.py**

```python
# accounts/urls_org.py
from django.urls import path

from . import views_org

urlpatterns = [
    path("", views_org.org_redirect, name="org_redirect"),
    path("info/", views_org.org_info, name="org_info"),
    path("members/", views_org.org_members, name="org_members"),
    path("members/<uuid:pk>/approve/", views_org.org_member_approve, name="org_member_approve"),
    path("members/<uuid:pk>/reject/", views_org.org_member_reject, name="org_member_reject"),
    path("members/<uuid:pk>/role/", views_org.org_member_role, name="org_member_role"),
    path("members/<uuid:pk>/remove/", views_org.org_member_remove, name="org_member_remove"),
    path("invites/", views_org.org_invites, name="org_invites"),
    path("invites/create/", views_org.org_invite_create, name="org_invite_create"),
    path("invites/<uuid:pk>/deactivate/", views_org.org_invite_deactivate, name="org_invite_deactivate"),
]
```

- [ ] **Step 5: Add /org/ include to main/urls.py**

Add after the existing `path("telegram/", ...)` line:

```python
    path("org/", include("accounts.urls_org")),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/accounts/test_org_management.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add accounts/views_org.py accounts/urls_org.py main/urls.py tests/accounts/
git commit -m "feat(accounts): add org management views — info, members, invites"
```

---

### Task 6: 조직 관리 템플릿 구현

**Files:**
- Create: `accounts/templates/accounts/org_base.html`
- Create: `accounts/templates/accounts/partials/org_tab_bar.html`
- Create: `accounts/templates/accounts/partials/org_info.html`
- Create: `accounts/templates/accounts/partials/org_members.html`
- Create: `accounts/templates/accounts/partials/org_invites.html`

- [ ] **Step 1: Create org_base.html**

```html
{# accounts/templates/accounts/org_base.html #}
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}

{% block title %}synco - 조직 관리{% endblock %}

{% block content %}
<div class="p-4 lg:p-8 space-y-6">
  <!-- Page Header -->
  <div>
    <h1 class="text-heading font-bold">조직 관리</h1>
  </div>

  <!-- Tab Bar -->
  {% include "accounts/partials/org_tab_bar.html" %}

  <!-- Tab Content -->
  <div id="org-content">
    {% if tab_template %}
      {% include tab_template %}
    {% else %}
      {% include "accounts/partials/org_info.html" %}
    {% endif %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Create org_tab_bar.html**

```html
{# accounts/templates/accounts/partials/org_tab_bar.html #}
<div class="border-b border-gray-200 flex gap-0 overflow-x-auto -mx-4 lg:-mx-8 px-4 lg:px-8">
  {% with active=active_tab|default:"info" %}

  <button hx-get="{% url 'org_info' %}"
          hx-target="#org-content"
          hx-push-url="true"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'info' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    조직 정보
  </button>

  <button hx-get="{% url 'org_members' %}"
          hx-target="#org-content"
          hx-push-url="true"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'members' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    멤버 관리
  </button>

  <button hx-get="{% url 'org_invites' %}"
          hx-target="#org-content"
          hx-push-url="true"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'invites' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    초대코드
  </button>

  {% endwith %}
</div>
```

- [ ] **Step 3: Create org_info.html**

```html
{# accounts/templates/accounts/partials/org_info.html #}
{% load static %}

<section class="bg-white rounded-lg border border-gray-100 p-5">
  <h2 class="text-[15px] font-semibold text-gray-500 mb-4">조직 정보</h2>

  <form method="post"
        enctype="multipart/form-data"
        hx-post="{% url 'org_info' %}"
        hx-target="#org-content"
        hx-push-url="false">
    {% csrf_token %}

    <div class="space-y-4">
      <!-- Organization name -->
      <div>
        <label for="id_name" class="block text-[14px] font-medium text-gray-700 mb-1.5">조직명</label>
        {{ form.name }}
      </div>

      <!-- Logo -->
      <div>
        <label for="id_logo" class="block text-[14px] font-medium text-gray-700 mb-1.5">로고</label>
        {% if org.logo %}
        <div class="mb-2">
          <img src="{{ org.logo.url }}" alt="조직 로고" class="w-16 h-16 rounded-lg object-cover border border-gray-200">
        </div>
        {% endif %}
        {{ form.logo }}
      </div>

      <!-- Plan (read-only) -->
      <div class="flex items-center justify-between">
        <span class="text-[14px] text-gray-500">플랜</span>
        <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700">
          {{ org.get_plan_display }}
        </span>
      </div>

      <!-- DB share (read-only) -->
      <div class="flex items-center justify-between">
        <span class="text-[14px] text-gray-500">DB 공유</span>
        <span class="text-[14px] font-medium {% if org.db_share_enabled %}text-green-600{% else %}text-gray-400{% endif %}">
          {% if org.db_share_enabled %}사용 중{% else %}미사용{% endif %}
        </span>
      </div>
    </div>

    <div class="mt-6">
      <button type="submit"
              class="w-full py-2.5 text-[14px] font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition">
        저장
      </button>
    </div>
  </form>
</section>
```

- [ ] **Step 4: Create org_members.html**

```html
{# accounts/templates/accounts/partials/org_members.html #}
{% load static %}

{% if message %}
<div class="mb-4 p-3 bg-green-50 text-green-700 rounded-lg text-sm">{{ message }}</div>
{% endif %}

<section class="bg-white rounded-lg border border-gray-100">
  <div class="p-5 border-b border-gray-100">
    <h2 class="text-[15px] font-semibold text-gray-500">멤버 목록</h2>
  </div>

  <div class="divide-y divide-gray-50">
    {% for member in members %}
    <div class="p-4 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 bg-gray-100 rounded-full flex items-center justify-center text-[14px] font-medium text-gray-600">
          {{ member.user.first_name|default:member.user.username|truncatechars:2 }}
        </div>
        <div>
          <p class="text-[14px] font-medium text-gray-900">
            {{ member.user.first_name|default:member.user.username }}
          </p>
          <div class="flex items-center gap-2 mt-0.5">
            <span class="text-[12px] px-1.5 py-0.5 rounded
              {% if member.role == 'owner' %}bg-purple-50 text-purple-700
              {% elif member.role == 'consultant' %}bg-blue-50 text-blue-700
              {% else %}bg-gray-100 text-gray-600{% endif %}">
              {{ member.get_role_display }}
            </span>
            <span class="text-[12px] px-1.5 py-0.5 rounded
              {% if member.status == 'active' %}bg-green-50 text-green-700
              {% elif member.status == 'pending' %}bg-amber-50 text-amber-700
              {% else %}bg-red-50 text-red-700{% endif %}">
              {% if member.status == 'active' %}활성
              {% elif member.status == 'pending' %}승인대기
              {% else %}거절{% endif %}
            </span>
            <span class="text-[11px] text-gray-400">{{ member.created_at|date:"Y-m-d" }}</span>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-2">
        {% if member.status == 'pending' %}
          <!-- Approve/Reject buttons -->
          <form method="post"
                hx-post="{% url 'org_member_approve' member.pk %}"
                hx-target="#org-content">
            {% csrf_token %}
            <button type="submit"
                    class="px-3 py-1.5 text-[12px] font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 transition">
              승인
            </button>
          </form>
          <form method="post"
                hx-post="{% url 'org_member_reject' member.pk %}"
                hx-target="#org-content">
            {% csrf_token %}
            <button type="submit"
                    class="px-3 py-1.5 text-[12px] font-medium text-red-600 border border-red-200 rounded-lg hover:bg-red-50 transition">
              거절
            </button>
          </form>

        {% elif member.status == 'active' and member.role != 'owner' %}
          <!-- Role change dropdown -->
          <form method="post"
                hx-post="{% url 'org_member_role' member.pk %}"
                hx-target="#org-content">
            {% csrf_token %}
            <select name="role"
                    onchange="this.form.requestSubmit()"
                    class="text-[12px] px-2 py-1.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="consultant" {% if member.role == 'consultant' %}selected{% endif %}>Consultant</option>
              <option value="viewer" {% if member.role == 'viewer' %}selected{% endif %}>Viewer</option>
            </select>
          </form>
          <!-- Remove button -->
          <form method="post"
                hx-post="{% url 'org_member_remove' member.pk %}"
                hx-target="#org-content"
                hx-confirm="정말로 {{ member.user.first_name|default:member.user.username }}님을 조직에서 제거하시겠습니까?">
            {% csrf_token %}
            <button type="submit"
                    class="px-3 py-1.5 text-[12px] font-medium text-red-500 border border-red-200 rounded-lg hover:bg-red-50 transition">
              제거
            </button>
          </form>
        {% endif %}
      </div>
    </div>
    {% empty %}
    <div class="p-8 text-center text-[14px] text-gray-400">
      멤버가 없습니다.
    </div>
    {% endfor %}
  </div>
</section>
```

- [ ] **Step 5: Create org_invites.html**

```html
{# accounts/templates/accounts/partials/org_invites.html #}
{% load static %}

{% if message %}
<div class="mb-4 p-3 bg-green-50 text-green-700 rounded-lg text-sm">{{ message }}</div>
{% endif %}

<!-- Create invite code form -->
<section class="bg-white rounded-lg border border-gray-100 p-5 mb-4">
  <h2 class="text-[15px] font-semibold text-gray-500 mb-4">새 초대코드 생성</h2>

  <form method="post"
        hx-post="{% url 'org_invite_create' %}"
        hx-target="#org-content">
    {% csrf_token %}

    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <div>
        <label for="id_role" class="block text-[13px] font-medium text-gray-600 mb-1">역할</label>
        {{ form.role }}
      </div>
      <div>
        <label for="id_max_uses" class="block text-[13px] font-medium text-gray-600 mb-1">최대 사용 횟수</label>
        {{ form.max_uses }}
      </div>
      <div>
        <label for="id_expires_at" class="block text-[13px] font-medium text-gray-600 mb-1">만료일 (선택)</label>
        {{ form.expires_at }}
      </div>
    </div>

    <div class="mt-4">
      <button type="submit"
              class="w-full sm:w-auto px-6 py-2.5 text-[14px] font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition">
        초대코드 생성
      </button>
    </div>
  </form>
</section>

<!-- Invite code list -->
<section class="bg-white rounded-lg border border-gray-100">
  <div class="p-5 border-b border-gray-100">
    <h2 class="text-[15px] font-semibold text-gray-500">초대코드 목록</h2>
  </div>

  <!-- Desktop table -->
  <div class="hidden sm:block overflow-x-auto">
    <table class="w-full">
      <thead>
        <tr class="text-left text-[12px] font-medium text-gray-500 border-b border-gray-100">
          <th class="px-5 py-3">코드</th>
          <th class="px-5 py-3">역할</th>
          <th class="px-5 py-3">사용/최대</th>
          <th class="px-5 py-3">만료일</th>
          <th class="px-5 py-3">상태</th>
          <th class="px-5 py-3">액션</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-50">
        {% for code in codes %}
        <tr>
          <td class="px-5 py-3 font-mono text-[14px] font-medium text-gray-900">{{ code.code }}</td>
          <td class="px-5 py-3 text-[13px] text-gray-600">{{ code.get_role_display }}</td>
          <td class="px-5 py-3 text-[13px] text-gray-600">{{ code.used_count }}/{{ code.max_uses }}</td>
          <td class="px-5 py-3 text-[13px] text-gray-600">
            {% if code.expires_at %}{{ code.expires_at|date:"Y-m-d" }}{% else %}-{% endif %}
          </td>
          <td class="px-5 py-3">
            {% if code.is_valid %}
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-green-50 text-green-700">
                <span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>활성
              </span>
            {% elif not code.is_active %}
              <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-100 text-gray-500">비활성</span>
            {% else %}
              <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700">소진/만료</span>
            {% endif %}
          </td>
          <td class="px-5 py-3">
            <div class="flex items-center gap-2">
              {% if code.is_active and code.is_valid %}
                <button onclick="navigator.clipboard.writeText('{{ code.code }}'); window.showToast('코드가 복사되었습니다')"
                        class="px-2.5 py-1 text-[12px] font-medium text-indigo-600 border border-indigo-200 rounded-lg hover:bg-indigo-50 transition">
                  복사
                </button>
                <form method="post"
                      hx-post="{% url 'org_invite_deactivate' code.pk %}"
                      hx-target="#org-content">
                  {% csrf_token %}
                  <button type="submit"
                          class="px-2.5 py-1 text-[12px] font-medium text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50 transition">
                    비활성화
                  </button>
                </form>
              {% endif %}
            </div>
          </td>
        </tr>
        {% empty %}
        <tr>
          <td colspan="6" class="px-5 py-8 text-center text-[14px] text-gray-400">
            생성된 초대코드가 없습니다.
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <!-- Mobile card list -->
  <div class="sm:hidden divide-y divide-gray-50">
    {% for code in codes %}
    <div class="p-4 space-y-2">
      <div class="flex items-center justify-between">
        <span class="font-mono text-[14px] font-medium text-gray-900">{{ code.code }}</span>
        {% if code.is_valid %}
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-green-50 text-green-700">활성</span>
        {% elif not code.is_active %}
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-100 text-gray-500">비활성</span>
        {% else %}
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700">소진/만료</span>
        {% endif %}
      </div>
      <div class="text-[12px] text-gray-500">
        {{ code.get_role_display }} | {{ code.used_count }}/{{ code.max_uses }}
        {% if code.expires_at %} | {{ code.expires_at|date:"Y-m-d" }}{% endif %}
      </div>
      {% if code.is_active and code.is_valid %}
      <div class="flex gap-2 pt-1">
        <button onclick="navigator.clipboard.writeText('{{ code.code }}'); window.showToast('코드가 복사되었습니다')"
                class="px-3 py-1.5 text-[12px] font-medium text-indigo-600 border border-indigo-200 rounded-lg hover:bg-indigo-50 transition">
          복사
        </button>
        <form method="post"
              hx-post="{% url 'org_invite_deactivate' code.pk %}"
              hx-target="#org-content">
          {% csrf_token %}
          <button type="submit"
                  class="px-3 py-1.5 text-[12px] font-medium text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50 transition">
            비활성화
          </button>
        </form>
      </div>
      {% endif %}
    </div>
    {% empty %}
    <div class="p-8 text-center text-[14px] text-gray-400">
      생성된 초대코드가 없습니다.
    </div>
    {% endfor %}
  </div>
</section>
```

- [ ] **Step 6: Verify all org templates render**

Run: `uv run pytest tests/accounts/test_org_management.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add accounts/templates/accounts/org_base.html accounts/templates/accounts/partials/org_*.html
git commit -m "feat(accounts): add org management templates — info, members, invites tabs"
```

---

### Task 7: 사이드바 + 모바일 네비게이션 업데이트

**Files:**
- Modify: `templates/common/nav_sidebar.html`
- Modify: `templates/common/nav_bottom.html`

- [ ] **Step 1: Add "조직 관리" menu to nav_sidebar.html (owner only)**

After the "설정" menu item (before `<script>`), add the org management menu:

```html
  {% if membership and membership.role == 'owner' %}
  <a href="/org/"
     hx-get="/org/" hx-target="#main-content" hx-push-url="true"
     data-nav="org"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
    조직 관리
  </a>
  {% endif %}
```

Update the `updateSidebar()` JavaScript to include the org route:

```javascript
                 (key === 'org' && path.startsWith('/org')) ||
```

- [ ] **Step 2: Add "조직 관리" to nav_bottom.html (owner only, replaces reference on mobile)**

Since mobile bottom nav has limited space, add the org management icon only for owner role. Add before the settings icon:

```html
    {% if membership and membership.role == 'owner' %}
    <a href="/org/"
       hx-get="/org/" hx-target="#main-content" hx-push-url="true"
       data-nav="org"
       class="nav-tab flex flex-col items-center py-1 px-3 min-w-[64px] text-gray-500">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
      <span class="text-[12px] mt-0.5">조직</span>
    </a>
    {% endif %}
```

Update the `updateNav()` JavaScript to include the org route:

```javascript
                 (key === 'org' && path.startsWith('/org')) ||
```

- [ ] **Step 3: Verify sidebar rendering**

Run: `uv run pytest -v --timeout=30`
Expected: All existing tests still PASS

- [ ] **Step 4: Commit**

```bash
git add templates/common/nav_sidebar.html templates/common/nav_bottom.html
git commit -m "feat(nav): add org management menu for owner role in sidebar and mobile nav"
```

---

### Task 8: email_disconnect 리다이렉트 수정 + 최종 통합 테스트

**Files:**
- Modify: `accounts/views.py`
- All test files

- [ ] **Step 1: Update email_disconnect redirect**

In `accounts/views.py`, change `email_disconnect` return:

```python
    return redirect(reverse("settings_email"))
```

- [ ] **Step 2: Update email_settings POST to return settings tab partial**

In `accounts/views.py`, update `email_settings` to redirect to the tab when accessed from settings:

```python
@login_required
def email_settings(request):
    """Gmail monitoring settings page."""
    from .models import EmailMonitorConfig

    config = EmailMonitorConfig.objects.filter(user=request.user).first()

    if request.method == "POST" and config:
        config.filter_labels = request.POST.getlist("filter_labels")
        config.filter_from = [
            e.strip()
            for e in request.POST.get("filter_from", "").split(",")
            if e.strip()
        ]
        config.is_active = request.POST.get("is_active") == "on"
        config.save(
            update_fields=[
                "filter_labels",
                "filter_from",
                "is_active",
                "updated_at",
            ]
        )
        # If HTMX request, return the settings tab partial
        if getattr(request, "htmx", None):
            return render(request, "accounts/partials/settings_email.html", {
                "config": config,
                "active_tab": "email",
            })

    return render(request, "accounts/email_settings.html", {"config": config})
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v --timeout=30`
Expected: All tests PASS (old + new)

- [ ] **Step 4: Commit**

```bash
git add accounts/views.py
git commit -m "fix(accounts): update email redirect to settings tab, HTMX partial response for email settings"
```

---

<!-- forge:phase2:구현계획:draft:2026-04-12 -->
