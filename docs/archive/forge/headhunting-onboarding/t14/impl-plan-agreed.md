# t14: 설정 탭 템플릿 구현

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 설정 페이지의 탭 바 및 각 탭(프로필/이메일/텔레그램/알림) 파셜 템플릿을 구현한다.

**Design spec:** `docs/forge/headhunting-onboarding/t14/design-spec.md`

**depends_on:** t13

---

## Changes from Tempering

| Issue | Severity | Resolution |
|-------|----------|------------|
| R1-01: HTMX main nav entry missing tab bar | CRITICAL | Added HX-Target detection in views: `#main-content` gets full tab shell, `#settings-content` gets tab partial. Updated Step 2 and added Step 2a for view modifications |
| R1-02: Email POST returns wrong template | CRITICAL | Changed email form to POST to `settings_email`; added POST handling to `settings_email` view in Step 2a |
| R1-03: Telegram actions return non-partial | CRITICAL | Added partial-aware hx-post URLs and Step 5a for telegram view partial variants |
| R1-04: Tests too weak | CRITICAL | Rewrote Step 7 with content verification tests (tab bar, active content, HTMX partial checks) |
| R1-05: Style tokens inconsistent | MINOR | Noted: existing email_settings_content.html already uses indigo tokens. Keeping consistent with existing codebase. Will address project-wide in future design token pass |
| R1-06: Hardcoded terms/privacy URLs | MINOR | Changed to `{% url 'terms' %}` and `{% url 'privacy' %}` in Step 3 |

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `accounts/templates/accounts/settings.html` | 수정 | 탭 바 + `#settings-content` 컨테이너 구조로 변경 |
| `accounts/templates/accounts/partials/settings_tab_bar.html` | 생성 | 설정 탭 바 (프로필/이메일/텔레그램/알림) |
| `accounts/templates/accounts/partials/settings_content.html` | 수정 | 프로필 탭 파셜 (알림 섹션 제거, 래퍼 div 제거) |
| `accounts/templates/accounts/partials/settings_email.html` | 수정 | 이메일 탭 파셜 (기존 email_settings_content.html 재활용, POST를 settings_email로 변경) |
| `accounts/templates/accounts/partials/settings_telegram.html` | 수정 | 텔레그램 탭 파셜 (partial-aware endpoints 사용) |
| `accounts/templates/accounts/partials/settings_notify.html` | 수정 | 알림 설정 탭 파셜 |
| `accounts/views.py` | 수정 | settings 뷰에 HX-Target 분기 + settings_email POST 처리 추가 |
| `projects/views_telegram.py` | 수정 | telegram_unbind/test_send에 partial variant 추가 |
| `tests/accounts/test_settings_tabs.py` | 수정 | 콘텐츠 검증 테스트 추가 |

---

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

The `settings.html` now provides the full settings shell: page header, tab bar, and `#settings-content` container. The content block outputs this entire shell, so when HTMX targets `#main-content`, the full tab UI is injected.

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

**Key change from original plan:** All tab views now use this template for both HTMX-to-`#main-content` and non-HTMX requests. See Step 2a for the view logic changes.

- [ ] **Step 2a: Update views for HX-Target aware rendering**

This step modifies `accounts/views.py` to handle two HTMX scenarios:
1. **`HX-Target: #main-content`** (sidebar/nav entry) → return `settings.html` (full tab shell via base_partial)
2. **`HX-Target: #settings-content`** (tab switching) → return only the tab partial
3. **Non-HTMX** → return `settings.html` (full page via base.html)

```python
# accounts/views.py — update settings tab views

def _is_tab_switch(request):
    """Check if this is an HTMX tab switch (targeting #settings-content)."""
    return (
        getattr(request, "htmx", None)
        and request.headers.get("HX-Target") == "settings-content"
    )


@login_required
def settings_profile(request):
    """GET /accounts/settings/profile/ — Profile tab."""
    context = {"active_tab": "profile"}
    if _is_tab_switch(request):
        return render(request, "accounts/partials/settings_content.html", context)
    return render(request, "accounts/settings.html", context)


@login_required
def settings_email(request):
    """GET/POST /accounts/settings/email/ — Email tab."""
    from .models import EmailMonitorConfig

    config = EmailMonitorConfig.objects.filter(user=request.user).first()

    if request.method == "POST" and config:
        config.filter_from = [
            e.strip()
            for e in request.POST.get("filter_from", "").split(",")
            if e.strip()
        ]
        config.is_active = request.POST.get("is_active") == "on"
        config.save(update_fields=["filter_from", "is_active", "updated_at"])

    context = {"config": config, "active_tab": "email"}

    if _is_tab_switch(request) or (getattr(request, "htmx", None) and request.method == "POST"):
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

    if _is_tab_switch(request):
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

    if _is_tab_switch(request) or (getattr(request, "htmx", None) and request.method == "POST"):
        return render(request, "accounts/partials/settings_notify.html", context)
    return render(request, "accounts/settings.html", {
        **context,
        "tab_template": "accounts/partials/settings_notify.html",
    })
```

**Note:** `_is_tab_switch` checks `HX-Target` header (without `#` prefix since HTMX sends the ID without it). POST responses always return the partial (they come from within the tab context).

- [ ] **Step 3: Update settings_content.html (profile tab)**

Remove the "알림" section and the outer wrapper div (wrapper is now in `settings.html`). Use `{% url %}` tags for terms/privacy links.

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
    <a href="{% url 'terms' %}" class="flex items-center justify-between group">
      <span class="text-[15px] text-gray-500 group-hover:text-gray-700">이용약관</span>
      <svg class="w-4 h-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
      </svg>
    </a>
    <a href="{% url 'privacy' %}" class="flex items-center justify-between group">
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

Reuses content from `email_settings_content.html` but without page header/back button. **Critical change:** form POSTs to `settings_email` instead of `email_settings`, with `hx-target="#settings-content"`.

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
          hx-post="{% url 'settings_email' %}"
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

**Critical change:** test/unbind actions POST to `telegram:bind_partial` endpoint which returns the tab partial. This ensures all telegram actions stay within the tab context.

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
          hx-post="{% url 'telegram:test_partial' %}"
          hx-target="#settings-content"
          class="flex-1">
      {% csrf_token %}
      <button type="submit"
        class="w-full px-4 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-[14px] font-medium transition">
        테스트 메시지 보내기
      </button>
    </form>
    <form method="post" action="{% url 'telegram:unbind' %}"
          hx-post="{% url 'telegram:unbind_partial' %}"
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

- [ ] **Step 5a: Add telegram partial variant views and URLs**

Add partial-aware endpoints for test/unbind in `projects/views_telegram.py`:

```python
# projects/views_telegram.py — add partial variants

@login_required
@require_POST
def telegram_test_partial(request):
    """POST /telegram/test-partial/ — Test message, returns settings tab partial."""
    from projects.services.notification import _send_telegram_message

    template = "accounts/partials/settings_telegram.html"

    try:
        binding = TelegramBinding.objects.get(user=request.user, is_active=True)
    except TelegramBinding.DoesNotExist:
        return render(request, template, {
            "is_bound": False,
            "error": "텔레그램이 연결되어 있지 않습니다.",
            "active_tab": "telegram",
        })

    try:
        _send_telegram_message(binding.chat_id, "🤖 synco 테스트 메시지입니다!")
        return render(request, template, {
            "is_bound": True,
            "verified_at": binding.verified_at,
            "message": "테스트 메시지가 전송되었습니다.",
            "active_tab": "telegram",
        })
    except Exception:
        return render(request, template, {
            "is_bound": True,
            "verified_at": binding.verified_at,
            "error": "메시지 전송에 실패했습니다.",
            "active_tab": "telegram",
        })


@login_required
@require_POST
def telegram_unbind_partial(request):
    """POST /telegram/unbind-partial/ — Unbind, returns settings tab partial."""
    template = "accounts/partials/settings_telegram.html"

    try:
        binding = TelegramBinding.objects.get(user=request.user)
        binding.is_active = False
        binding.save(update_fields=["is_active"])
    except TelegramBinding.DoesNotExist:
        pass

    return render(request, template, {
        "is_bound": False,
        "message": "텔레그램 연동이 해제되었습니다.",
        "active_tab": "telegram",
    })
```

Add URLs in `projects/urls_telegram.py`:

```python
    path("test-partial/", views_telegram.telegram_test_partial, name="test_partial"),
    path("unbind-partial/", views_telegram.telegram_unbind_partial, name="unbind_partial"),
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

- [ ] **Step 7: Update tests with content verification**

Update existing tests and add new ones that verify content, not just status codes. This addresses t13 R1-04.

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
    def test_profile_full_page_renders_tab_bar(self, active_user):
        """Full page request renders settings.html with tab bar."""
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/profile/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]
        assert "accounts/partials/settings_tab_bar.html" in [t.name for t in response.templates]
        content = response.content.decode()
        # Tab bar buttons present
        assert "프로필" in content
        assert "이메일" in content
        assert "텔레그램" in content
        assert "알림" in content
        # Profile content present
        assert "내 정보" in content

    def test_profile_htmx_main_entry_includes_tab_bar(self, active_user):
        """HTMX request to #main-content includes tab bar (sidebar entry)."""
        client = TestClient()
        client.force_login(active_user)
        response = client.get(
            "/accounts/settings/profile/",
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="main-content",
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "프로필" in content
        assert "이메일" in content
        assert "settings-content" in content  # Container for tab content
        assert "<html" not in content  # No full page wrapper

    def test_profile_htmx_tab_switch_returns_partial_only(self, active_user):
        """HTMX request to #settings-content returns only profile partial."""
        client = TestClient()
        client.force_login(active_user)
        response = client.get(
            "/accounts/settings/profile/",
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="settings-content",
        )
        assert response.status_code == 200
        assert "accounts/partials/settings_content.html" in [
            t.name for t in response.templates
        ]
        content = response.content.decode()
        assert "내 정보" in content
        assert "<html" not in content
        # Should NOT contain tab bar (only partial)
        assert "settings_tab_bar" not in content


@pytest.mark.django_db
class TestSettingsEmailTab:
    def test_email_tab_returns_200_with_tab_bar(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/email/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]
        content = response.content.decode()
        assert "Gmail" in content or "이메일" in content


@pytest.mark.django_db
class TestSettingsTelegramTab:
    def test_telegram_tab_returns_200_with_tab_bar(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/telegram/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]
        content = response.content.decode()
        assert "텔레그램" in content


@pytest.mark.django_db
class TestSettingsNotifyTab:
    def test_notify_tab_returns_200_with_tab_bar(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/notify/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]
        content = response.content.decode()
        assert "알림 설정" in content

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

    def test_notify_htmx_post_returns_partial(self, active_user):
        """HTMX POST returns only the notify partial, not full page."""
        client = TestClient()
        client.force_login(active_user)
        response = client.post(
            "/accounts/settings/notify/",
            {
                "contact_result_web": "on",
            },
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="settings-content",
        )
        assert response.status_code == 200
        assert "accounts/partials/settings_notify.html" in [
            t.name for t in response.templates
        ]
        content = response.content.decode()
        assert "알림 설정" in content
        assert "<html" not in content
```

- [ ] **Step 8: Run tests to verify**

Run: `uv run pytest tests/accounts/test_settings_tabs.py -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add accounts/templates/ accounts/views.py projects/views_telegram.py projects/urls_telegram.py tests/accounts/
git commit -m "feat(accounts): add settings tab bar and tab partial templates"
```

<!-- forge:t14:impl-plan:complete:2026-04-12T16:45:00+09:00 -->
