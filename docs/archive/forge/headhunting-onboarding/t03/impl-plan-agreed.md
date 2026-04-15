# Task 3: 카카오 로그인 플로우 수정 + 온보딩 화면 (확정 구현계획서)

**Goal:** 카카오 로그인 후 Membership 상태에 따라 적절한 화면(대시보드/초대코드/승인대기/거절)으로 라우팅하고, 초대코드 입력/승인대기/거절 화면을 구현한다.

**Design spec:** `docs/forge/headhunting-onboarding/t03/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료)

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `main/urls.py` | 수정 | 루트 URL을 dashboard에서 home으로 변경 |
| `accounts/views.py` | 수정 | home 수정, invite_code/pending/rejected 뷰 추가, consultant 가입 시 owner 알림 |
| `accounts/urls.py` | 수정 | 초대코드/승인대기/거절 URL 추가 |
| `accounts/templates/accounts/invite_code.html` | 생성 | 초대코드 입력 화면 |
| `accounts/templates/accounts/pending_approval.html` | ���성 | 승인 대기 화면 |
| `accounts/templates/accounts/rejected.html` | 생성 | 거절 안내 화면 |
| `tests/accounts/test_onboarding.py` | 생성 | 온보딩 플로우 테스트 |

---

- [ ] **Step 1: Write failing tests for onboarding flow**

```python
# tests/accounts/test_onboarding.py
import pytest
from django.test import Client as TestClient
from django.contrib.auth import get_user_model

from accounts.models import InviteCode, Membership, Organization

User = get_user_model()


@pytest.mark.django_db
class TestInviteCodeView:
    def test_no_membership_shows_invite_page(self):
        user = User.objects.create_user(username="new", password="pass")
        client = TestClient()
        client.force_login(user)

        response = client.get("/accounts/invite/")
        assert response.status_code == 200
        assert "초대코드" in response.content.decode()

    def test_valid_owner_code_creates_active_membership(self):
        org = Organization.objects.create(name="Org")
        code = InviteCode.objects.create(
            organization=org, role="owner", max_uses=1
        )
        user = User.objects.create_user(username="boss", password="pass")
        client = TestClient()
        client.force_login(user)

        response = client.post(
            "/accounts/invite/", {"code": code.code}, follow=True
        )
        membership = Membership.objects.get(user=user)
        assert membership.status == "active"
        assert membership.role == "owner"
        code.refresh_from_db()
        assert code.used_count == 1

    def test_valid_consultant_code_creates_pending_membership(self):
        org = Organization.objects.create(name="Org")
        code = InviteCode.objects.create(
            organization=org, role="consultant", max_uses=10
        )
        user = User.objects.create_user(username="emp", password="pass")
        client = TestClient()
        client.force_login(user)

        response = client.post(
            "/accounts/invite/", {"code": code.code}, follow=True
        )
        membership = Membership.objects.get(user=user)
        assert membership.status == "pending"
        assert membership.role == "consultant"

    def test_invalid_code_shows_error(self):
        user = User.objects.create_user(username="bad", password="pass")
        client = TestClient()
        client.force_login(user)

        response = client.post("/accounts/invite/", {"code": "INVALID1"})
        assert response.status_code == 200
        assert "유효하지 않은" in response.content.decode()

    def test_expired_code_shows_error(self):
        from datetime import timedelta
        from django.utils import timezone

        org = Organization.objects.create(name="Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        user = User.objects.create_user(username="late", password="pass")
        client = TestClient()
        client.force_login(user)

        response = client.post("/accounts/invite/", {"code": code.code})
        assert response.status_code == 200
        assert "유효하지 않은" in response.content.decode()

    def test_pending_user_redirected_from_invite(self):
        """pending 사용자가 /accounts/invite/에 접근하면 승인대기로 리다이렉트."""
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="pend_inv", password="pass")
        Membership.objects.create(
            user=user, organization=org, status="pending", role="consultant"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/accounts/invite/")
        assert response.status_code == 302
        assert "pending" in response.url


@pytest.mark.django_db
class TestPendingApprovalView:
    def test_pending_user_sees_waiting_page(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="wait", password="pass")
        Membership.objects.create(
            user=user, organization=org, status="pending"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/accounts/pending/")
        assert response.status_code == 200
        assert "승인" in response.content.decode()

    def test_active_user_redirects_to_dashboard(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="active", password="pass")
        Membership.objects.create(
            user=user, organization=org, status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/accounts/pending/")
        assert response.status_code == 302


@pytest.mark.django_db
class TestRejectedView:
    def test_rejected_user_sees_rejection_page(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="rej", password="pass")
        Membership.objects.create(
            user=user, organization=org, status="rejected"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/accounts/rejected/")
        assert response.status_code == 200
        assert "거절" in response.content.decode()

    def test_active_user_redirects_from_rejected(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="act2", password="pass")
        Membership.objects.create(
            user=user, organization=org, status="active"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/accounts/rejected/")
        assert response.status_code == 302


@pytest.mark.django_db
class TestHomeRedirection:
    def test_no_membership_redirects_to_invite(self):
        user = User.objects.create_user(username="nomem", password="pass")
        client = TestClient()
        client.force_login(user)

        response = client.get("/")
        assert response.status_code == 302
        assert "invite" in response.url

    def test_pending_redirects_to_pending(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="pend", password="pass")
        Membership.objects.create(
            user=user, organization=org, status="pending"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/")
        assert response.status_code == 302
        assert "pending" in response.url

    def test_rejected_redirects_to_rejected(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="rej2", password="pass")
        Membership.objects.create(
            user=user, organization=org, status="rejected"
        )
        client = TestClient()
        client.force_login(user)

        response = client.get("/")
        assert response.status_code == 302
        assert "rejected" in response.url
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/accounts/test_onboarding.py -v`
Expected: FAIL -- URLs not found, views not defined

- [ ] **Step 3: Create invite_code.html template**

```html
{# accounts/templates/accounts/invite_code.html #}
{% load static %}
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>synco -- 초대코드 입력</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.min.css">
  <link rel="stylesheet" href="{% static 'css/output.css' %}">
</head>
<body class="bg-slate-50 font-sans min-h-screen flex items-center justify-center">
  <div class="w-full max-w-sm px-6">
    <div class="text-center mb-8">
      <h1 class="text-2xl font-bold text-primary mb-2">synco</h1>
      <p class="text-gray-500 text-[15px]">조직에 참여하려면 초대코드를 입력하세요.</p>
    </div>

    <form method="post" class="space-y-4">
      {% csrf_token %}
      <div>
        <input
          type="text"
          name="code"
          placeholder="초대코드 8자리"
          maxlength="8"
          class="w-full px-4 py-3 border border-gray-300 rounded-lg text-center text-lg tracking-widest font-mono uppercase focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          autocomplete="off"
          autofocus
          required
        >
      </div>

      {% if error %}
      <p class="text-red-500 text-sm text-center">{{ error }}</p>
      {% endif %}

      <button
        type="submit"
        class="w-full py-3 bg-primary text-white rounded-lg font-medium hover:bg-primary-dark transition"
      >
        참여하기
      </button>
    </form>

    <div class="mt-6 text-center">
      <p class="text-gray-400 text-sm">초대코드가 없으신가요?</p>
      <p class="text-gray-400 text-sm">조직 관리자에게 문의하세요.</p>
    </div>

    <div class="mt-8 text-center">
      <a href="{% url 'logout' %}" class="text-gray-400 text-sm hover:text-gray-600">로그아���</a>
    </div>
  </div>
</body>
</html>
```

- [ ] **Step 4: Create pending_approval.html template**

```html
{# accounts/templates/accounts/pending_approval.html #}
{% load static %}
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>synco -- 승인 대기</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.min.css">
  <link rel="stylesheet" href="{% static 'css/output.css' %}">
</head>
<body class="bg-slate-50 font-sans min-h-screen flex items-center justify-center">
  <div class="w-full max-w-sm px-6 text-center">
    <div class="mb-8">
      <h1 class="text-2xl font-bold text-primary mb-2">synco</h1>
      <div class="w-16 h-16 mx-auto mb-4 bg-amber-100 rounded-full flex items-center justify-center">
        <svg class="w-8 h-8 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>
      </div>
      <h2 class="text-lg font-semibold text-gray-900 mb-2">가입 승인을 기다리고 있습니다</h2>
      <p class="text-gray-500 text-[15px]">조직 관리자가 승인하면 서비스를 ��용할 수 있습니다.</p>
    </div>

    <a href="{% url 'logout' %}" class="text-gray-400 text-sm hover:text-gray-600">로그아웃</a>
  </div>
</body>
</html>
```

- [ ] **Step 5: Create rejected.html template**

```html
{# accounts/templates/accounts/rejected.html #}
{% load static %}
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>synco -- 가입 거절</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.min.css">
  <link rel="stylesheet" href="{% static 'css/output.css' %}">
</head>
<body class="bg-slate-50 font-sans min-h-screen flex items-center justify-center">
  <div class="w-full max-w-sm px-6 text-center">
    <div class="mb-8">
      <h1 class="text-2xl font-bold text-primary mb-2">synco</h1>
      <div class="w-16 h-16 mx-auto mb-4 bg-red-100 rounded-full flex items-center justify-center">
        <svg class="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </div>
      <h2 class="text-lg font-semibold text-gray-900 mb-2">가입 요청이 거절되었습니다</h2>
      <p class="text-gray-500 text-[15px]">관리자에게 문의하세요.</p>
    </div>

    <a href="{% url 'logout' %}" class="text-gray-400 text-sm hover:text-gray-600">로그아웃</a>
  </div>
</body>
</html>
```

- [ ] **Step 6: Modify main/urls.py — root URL to home view**

**[CRITICAL FIX from I-R1-01]** `main/urls.py`에서 루트 `""` 경로를 `dashboard`가 아닌 `accounts.views.home`으로 변경:

```python
# main/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import home
from projects.views import dashboard, dashboard_actions, dashboard_team

urlpatterns = [
    path("admin/", admin.site.urls),
    # Root: onboarding router (routes by membership status)
    path("", home, name="home"),
    # Dashboard: explicit path only (protected by membership_required in t04)
    path("dashboard/", dashboard, name="dashboard"),
    path("dashboard/actions/", dashboard_actions, name="dashboard_actions"),
    path("dashboard/team/", dashboard_team, name="dashboard_team"),
    # Accounts (login, settings, etc.)
    path("", include("accounts.urls")),
    path("candidates/", include("candidates.urls")),
    path("clients/", include("clients.urls")),
    path("reference/", include("clients.urls_reference")),
    path("voice/", include("projects.urls_voice")),
    path("projects/", include("projects.urls")),
    path("telegram/", include("projects.urls_telegram")),
    path("news/", include("projects.urls_news")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

**주의:** `name="dashboard"` 를 `path("dashboard/", ...)` 에 부여하여 기존 `redirect("dashboard")` 호출이 `/dashboard/`로 올바르게 작동하도록 함. 기존 `name="dashboard_explicit"` 제거.

- [ ] **Step 7: Add invite/pending/rejected views to accounts/views.py**

Add imports at top of `accounts/views.py`:

```python
from django.db import transaction

from .models import InviteCode, Membership, User
```

Replace the `home` function and add new views after it:

```python
@login_required
def home(request):
    """Root redirect -- route by membership status."""
    try:
        membership = request.user.membership
        if membership.status == "pending":
            return redirect("pending_approval")
        if membership.status == "rejected":
            return redirect("rejected")
        return redirect("dashboard")
    except Membership.DoesNotExist:
        return redirect("invite_code")


@login_required
def invite_code_page(request):
    """초대코드 입력 화면."""
    # Already has membership -- redirect to appropriate page
    try:
        m = request.user.membership
        if m.status == "active":
            return redirect("dashboard")
        if m.status == "pending":
            return redirect("pending_approval")
        if m.status == "rejected":
            return redirect("rejected")
    except Membership.DoesNotExist:
        pass

    error = None
    if request.method == "POST":
        code_str = request.POST.get("code", "").strip().upper()
        try:
            invite = InviteCode.objects.get(code=code_str)
        except InviteCode.DoesNotExist:
            invite = None

        if invite and invite.is_valid:
            # Owner gets immediate activation
            status = "active" if invite.role == "owner" else "pending"
            with transaction.atomic():
                Membership.objects.create(
                    user=request.user,
                    organization=invite.organization,
                    role=invite.role,
                    status=status,
                )
                invite.use()

            if status == "active":
                return redirect("dashboard")
            else:
                # Notify organization owners about new pending member
                _notify_owners_new_pending(request.user, invite.organization)
                return redirect("pending_approval")
        else:
            error = "유효하지 않은 초대코드입니다."

    return render(request, "accounts/invite_code.html", {"error": error})


def _notify_owners_new_pending(user, organization):
    """Notify org owners when a new consultant requests membership."""
    try:
        from projects.models import Notification
        from projects.services.notification import send_notification

        owner_memberships = Membership.objects.filter(
            organization=organization,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
        ).select_related("user")

        display_name = user.get_full_name() or user.username

        for om in owner_memberships:
            notif = Notification.objects.create(
                recipient=om.user,
                type=Notification.Type.APPROVAL_REQUEST,
                title="새 멤버 가입 요청",
                body=f"{display_name}님이 조직 가입을 요청했습니다.",
            )
            send_notification(
                notif,
                text=f"새 멤버 가입 요청: {display_name}님이 조직 가입을 요청했습니다. 승인이 필요합니다.",
            )
    except Exception:
        pass  # Best-effort notification -- don't block onboarding flow


@login_required
def pending_approval_page(request):
    """승인 대기 화면."""
    try:
        membership = request.user.membership
        if membership.status == "active":
            return redirect("dashboard")
        if membership.status == "rejected":
            return redirect("rejected")
    except Membership.DoesNotExist:
        return redirect("invite_code")

    return render(request, "accounts/pending_approval.html")


@login_required
def rejected_page(request):
    """거절 안내 화면."""
    try:
        membership = request.user.membership
        if membership.status == "active":
            return redirect("dashboard")
        if membership.status == "pending":
            return redirect("pending_approval")
    except Membership.DoesNotExist:
        return redirect("invite_code")

    return render(request, "accounts/rejected.html")
```

- [ ] **Step 8: Update accounts/urls.py**

Remove the `home` path from accounts/urls.py (moved to main/urls.py) and add new onboarding URLs:

```python
from django.urls import path

from . import views

urlpatterns = [
    # Note: home is now in main/urls.py as root entry point
    path("accounts/login/", views.login_page, name="login"),
    path("accounts/kakao/login/", views.kakao_login, name="kakao_login"),
    path("accounts/kakao/callback/", views.kakao_callback, name="kakao_callback"),
    path("accounts/settings/", views.settings_page, name="settings"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    # Onboarding
    path("accounts/invite/", views.invite_code_page, name="invite_code"),
    path("accounts/pending/", views.pending_approval_page, name="pending_approval"),
    path("accounts/rejected/", views.rejected_page, name="rejected"),
    # P18: Gmail integration
    path("accounts/email/connect/", views.email_connect, name="email_connect"),
    path("accounts/email/callback/", views.email_oauth_callback, name="email_callback"),
    path("accounts/email/settings/", views.email_settings, name="email_settings"),
    path("accounts/email/disconnect/", views.email_disconnect, name="email_disconnect"),
]
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `uv run pytest tests/accounts/test_onboarding.py -v`
Expected: All 13 tests PASS (12 original + 1 new pending redirect test)

- [ ] **Step 10: Run full test suite**

Run: `uv run pytest -v`
Expected: No regressions. 기존 test_rbac.py, test_invite_code.py도 통과 확인.

- [ ] **Step 11: Commit**

```bash
git add main/urls.py accounts/views.py accounts/urls.py \
  accounts/templates/accounts/invite_code.html \
  accounts/templates/accounts/pending_approval.html \
  accounts/templates/accounts/rejected.html \
  tests/accounts/test_onboarding.py
git commit -m "feat(accounts): add invite code, pending approval, and rejection onboarding flow"
```

---

## Tempering Rulings Applied

| ID | Severity | Issue | Action |
|----|----------|-------|--------|
| I-R1-01 | CRITICAL | Root URL routing mismatch | ACCEPTED — main/urls.py 루트를 home으로 변경 (Step 6) |
| I-R1-02 | CRITICAL | Pending user IntegrityError | ACCEPTED — invite_code_page에 pending guard 추가 (Step 7) |
| I-R1-03 | MAJOR | /dashboard/ direct access 404 | REBUTTED — t04 범위 |
| I-R1-04 | MAJOR | Non-atomic redemption | PARTIAL — transaction.atomic() 추가 (Step 7) |
| I-R1-05 | MAJOR | Owner notification missing | ACCEPTED — _notify_owners_new_pending() 추가 (Step 7) |
| I-R1-06 | MINOR | Commit missing files | ACCEPTED — git add에 전체 파일 포함 (Step 11) |

<!-- forge:t03:구현담금질:complete:2026-04-12T06:30:00+09:00 -->
