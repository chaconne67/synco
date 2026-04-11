# Task 3: 카카오 로그인 플로우 수정 + 온보딩 화면

**Goal:** 카카오 로그인 후 Membership 상태에 따라 적절한 화면(대시보드/초대코드/승인대기/거절)으로 라우팅하고, 초대코드 입력/승인대기/거절 화면을 구현한다.

**Design spec:** `docs/forge/headhunting-onboarding/t03/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료)

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `accounts/views.py:34-79` | 수정 | kakao_callback 수정, invite_code/pending/rejected 뷰 추가 |
| `accounts/urls.py` | 수정 | 초대코드/승인대기/거절 URL 추가 |
| `accounts/templates/accounts/invite_code.html` | 생성 | 초대코드 입력 화면 |
| `accounts/templates/accounts/pending_approval.html` | 생성 | 승인 대기 화면 |
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
      <a href="{% url 'logout' %}" class="text-gray-400 text-sm hover:text-gray-600">로그아웃</a>
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
      <p class="text-gray-500 text-[15px]">조직 관리자가 승인하면 서비스를 이용할 수 있습니다.</p>
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

- [ ] **Step 6: Add invite/pending/rejected views to accounts/views.py**

Add imports at top of `accounts/views.py`:

```python
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
    # Already has active membership -- go to dashboard
    try:
        m = request.user.membership
        if m.status == "active":
            return redirect("dashboard")
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
                return redirect("pending_approval")
        else:
            error = "유효하지 않은 초대코드입니다."

    return render(request, "accounts/invite_code.html", {"error": error})


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

- [ ] **Step 7: Add URLs to accounts/urls.py**

Add to urlpatterns:

```python
path("accounts/invite/", views.invite_code_page, name="invite_code"),
path("accounts/pending/", views.pending_approval_page, name="pending_approval"),
path("accounts/rejected/", views.rejected_page, name="rejected"),
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/accounts/test_onboarding.py -v`
Expected: All 12 tests PASS

- [ ] **Step 9: Commit**

```bash
git add accounts/views.py accounts/urls.py accounts/templates/accounts/
git commit -m "feat(accounts): add invite code, pending approval, and rejection onboarding flow"
```
