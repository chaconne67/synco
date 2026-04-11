# RBAC + 온보딩 구현 계획 (Plan 1/3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 역할 기반 접근 제어(RBAC)와 초대코드 기반 온보딩을 도입하여, 로그인→대시보드 404 문제를 해결하고, owner/consultant 역할에 따른 메뉴·기능 접근을 제어한다.

**Architecture:** accounts 앱에 InviteCode 모델과 Membership.status 필드를 추가한다. 카카오 로그인 플로우를 수정하여 Membership 없는 사용자를 초대코드 입력 화면으로 보낸다. `role_required` 데코레이터로 view 단 접근 제어를 하고, 사이드바 템플릿에서 역할별 메뉴를 필터링한다. context processor로 membership 정보를 모든 템플릿에 주입한다.

**Tech Stack:** Django 5.2, HTMX, Tailwind CSS, pytest

**Design spec:** `docs/designs/2026-04-11-ux-gap-rbac-onboarding-design.md`

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `accounts/models.py` | 수정 | InviteCode 모델 추가, Membership.status 필드 추가 |
| `accounts/admin.py` | 수정 | InviteCode admin 등록 |
| `accounts/views.py` | 수정 | kakao_callback 수정, invite_code/pending 뷰 추가 |
| `accounts/urls.py` | 수정 | 초대코드/승인대기 URL 추가 |
| `accounts/decorators.py` | 생성 | role_required, membership_required 데코레이터 |
| `accounts/context_processors.py` | 생성 | membership context processor |
| `main/settings.py` | 수정 | context_processors에 membership 추가 |
| `templates/common/nav_sidebar.html` | 수정 | 역할별 메뉴 필터링 |
| `templates/common/nav_bottom.html` | 수정 | 역할별 메뉴 필터링 (모바일) |
| `accounts/templates/accounts/invite_code.html` | 생성 | 초대코드 입력 화면 |
| `accounts/templates/accounts/pending_approval.html` | 생성 | 승인 대기 화면 |
| `projects/views.py` | 수정 | _get_org 수정, 권한 데코레이터 적용 |
| `clients/views.py` | 수정 | 권한 데코레이터 적용 |
| `tests/conftest.py` | 수정 | Membership.status='active' 추가 |
| `tests/accounts/test_invite_code.py` | 생성 | InviteCode 모델 테스트 |
| `tests/accounts/test_onboarding.py` | 생성 | 온보딩 플로우 테스트 |
| `tests/accounts/test_rbac.py` | 생성 | 역할별 접근 제어 테스트 |

---

### Task 1: InviteCode 모델 + Membership.status 추가

**Files:**
- Modify: `accounts/models.py`
- Modify: `accounts/admin.py`
- Test: `tests/accounts/test_invite_code.py`

- [ ] **Step 1: Write failing test for InviteCode model**

```python
# tests/accounts/test_invite_code.py
import pytest
from django.utils import timezone
from datetime import timedelta

from accounts.models import InviteCode, Membership, Organization

User = __import__("django.contrib.auth", fromlist=["get_user_model"]).get_user_model()


@pytest.mark.django_db
class TestInviteCode:
    def test_create_invite_code(self):
        org = Organization.objects.create(name="Test Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            max_uses=10,
        )
        assert code.code  # auto-generated
        assert len(code.code) == 8
        assert code.is_active is True
        assert code.used_count == 0

    def test_is_valid_active_code(self):
        org = Organization.objects.create(name="Test Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            max_uses=5,
        )
        assert code.is_valid is True

    def test_is_valid_expired(self):
        org = Organization.objects.create(name="Test Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        assert code.is_valid is False

    def test_is_valid_max_uses_reached(self):
        org = Organization.objects.create(name="Test Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            max_uses=1,
            used_count=1,
        )
        assert code.is_valid is False

    def test_is_valid_deactivated(self):
        org = Organization.objects.create(name="Test Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            is_active=False,
        )
        assert code.is_valid is False

    def test_use_increments_count(self):
        org = Organization.objects.create(name="Test Org")
        code = InviteCode.objects.create(
            organization=org,
            role="consultant",
            max_uses=5,
        )
        code.use()
        assert code.used_count == 1


@pytest.mark.django_db
class TestMembershipStatus:
    def test_default_status_is_active(self):
        org = Organization.objects.create(name="Test Org")
        user = User.objects.create_user(username="test", password="pass")
        m = Membership.objects.create(user=user, organization=org)
        assert m.status == "active"

    def test_pending_status(self):
        org = Organization.objects.create(name="Test Org")
        user = User.objects.create_user(username="test", password="pass")
        m = Membership.objects.create(
            user=user, organization=org, status="pending"
        )
        assert m.status == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_invite_code.py -v`
Expected: FAIL — `ImportError: cannot import name 'InviteCode'` and `TypeError` on `status` field

- [ ] **Step 3: Add InviteCode model and Membership.status to accounts/models.py**

Add after the `Membership` class (after line 78):

```python
import secrets
import string


class InviteCode(BaseModel):
    """초대코드 — Organization 가입용."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        CONSULTANT = "consultant", "Consultant"
        VIEWER = "viewer", "Viewer"

    code = models.CharField(max_length=20, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="invite_codes",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CONSULTANT,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_invite_codes",
    )
    max_uses = models.PositiveIntegerField(default=1)
    used_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.code} ({self.organization.name}, {self.role})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_code() -> str:
        chars = string.ascii_uppercase + string.digits
        while True:
            code = "".join(secrets.choice(chars) for _ in range(8))
            if not InviteCode.objects.filter(code=code).exists():
                return code

    @property
    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        if self.expires_at:
            from django.utils import timezone
            if self.expires_at <= timezone.now():
                return False
        return True

    def use(self) -> None:
        self.used_count += 1
        self.save(update_fields=["used_count", "updated_at"])
```

Add `status` field to `Membership` class (after `role` field, around line 72):

```python
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PENDING = "pending", "Pending"

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
```

- [ ] **Step 4: Register InviteCode in admin**

Add to `accounts/admin.py`:

```python
from .models import InviteCode

@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "organization", "role", "used_count", "max_uses", "is_active", "expires_at")
    list_filter = ("role", "is_active", "organization")
    search_fields = ("code", "organization__name")
    readonly_fields = ("code", "used_count")
```

Update `MembershipAdmin` to include status:

```python
@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "status")
    list_filter = ("role", "status")
    search_fields = ("user__username", "organization__name")
```

- [ ] **Step 5: Create and run migration**

Run: `uv run python manage.py makemigrations accounts && uv run python manage.py migrate`
Expected: Migration created and applied successfully

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/accounts/test_invite_code.py -v`
Expected: All 8 tests PASS

- [ ] **Step 7: Commit**

```bash
git add accounts/models.py accounts/admin.py accounts/migrations/ tests/accounts/
git commit -m "feat(accounts): add InviteCode model and Membership.status field"
```

---

### Task 2: 데코레이터 + context processor

**Files:**
- Create: `accounts/decorators.py`
- Create: `accounts/context_processors.py`
- Modify: `main/settings.py:88`
- Test: `tests/accounts/test_rbac.py`

- [ ] **Step 1: Write failing test for decorators**

```python
# tests/accounts/test_rbac.py
import pytest
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.http import HttpResponse

from accounts.decorators import role_required, membership_required
from accounts.models import Membership, Organization

User = get_user_model()


def dummy_view(request):
    return HttpResponse("OK")


@pytest.mark.django_db
class TestMembershipRequired:
    def test_active_member_passes(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="u1", password="p")
        Membership.objects.create(user=user, organization=org, status="active")

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        view = membership_required(dummy_view)
        response = view(request)
        assert response.status_code == 200

    def test_pending_member_redirects(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="u2", password="p")
        Membership.objects.create(user=user, organization=org, status="pending")

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        view = membership_required(dummy_view)
        response = view(request)
        assert response.status_code == 302
        assert "pending" in response.url

    def test_no_membership_redirects(self):
        user = User.objects.create_user(username="u3", password="p")

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        view = membership_required(dummy_view)
        response = view(request)
        assert response.status_code == 302
        assert "invite" in response.url


@pytest.mark.django_db
class TestRoleRequired:
    def test_owner_passes_owner_required(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="u4", password="p")
        Membership.objects.create(
            user=user, organization=org, role="owner", status="active"
        )

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        view = role_required("owner")(dummy_view)
        response = view(request)
        assert response.status_code == 200

    def test_consultant_blocked_from_owner_required(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="u5", password="p")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        view = role_required("owner")(dummy_view)
        response = view(request)
        assert response.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_rbac.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'accounts.decorators'`

- [ ] **Step 3: Create accounts/decorators.py**

```python
# accounts/decorators.py
from functools import wraps

from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from accounts.models import Membership


def membership_required(view_func):
    """Ensure user has an active Membership. Redirect otherwise."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            membership = request.user.membership
        except Membership.DoesNotExist:
            return redirect("invite_code")

        if membership.status == "pending":
            return redirect("pending_approval")

        return view_func(request, *args, **kwargs)

    return wrapper


def role_required(*roles):
    """Ensure user has one of the specified roles. Returns 403 otherwise."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            try:
                membership = request.user.membership
            except Membership.DoesNotExist:
                return redirect("invite_code")

            if membership.status != "active":
                return redirect("pending_approval")

            if membership.role not in roles:
                return HttpResponseForbidden(
                    "이 페이지에 접근할 권한이 없습니다."
                )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
```

- [ ] **Step 4: Create accounts/context_processors.py**

```python
# accounts/context_processors.py
from accounts.models import Membership


def membership(request):
    """Inject current user's membership into template context."""
    if not request.user.is_authenticated:
        return {"membership": None}

    try:
        m = request.user.membership
        if m.status != "active":
            return {"membership": None}
        return {"membership": m}
    except Membership.DoesNotExist:
        return {"membership": None}
```

- [ ] **Step 5: Register context processor in settings**

In `main/settings.py`, add to context_processors list (after line 89):

```python
"accounts.context_processors.membership",
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/accounts/test_rbac.py -v`
Expected: All 5 tests PASS

- [ ] **Step 7: Commit**

```bash
git add accounts/decorators.py accounts/context_processors.py main/settings.py tests/accounts/test_rbac.py
git commit -m "feat(accounts): add role_required decorator and membership context processor"
```

---

### Task 3: 카카오 로그인 플로우 수정 + 온보딩 화면

**Files:**
- Modify: `accounts/views.py:34-79`
- Modify: `accounts/urls.py`
- Create: `accounts/templates/accounts/invite_code.html`
- Create: `accounts/templates/accounts/pending_approval.html`
- Test: `tests/accounts/test_onboarding.py`

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/accounts/test_onboarding.py -v`
Expected: FAIL — URLs not found, views not defined

- [ ] **Step 3: Create invite_code.html template**

```html
{# accounts/templates/accounts/invite_code.html #}
{% load static %}
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>synco — 초대코드 입력</title>
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
  <title>synco — 승인 대기</title>
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

- [ ] **Step 5: Add invite/pending views to accounts/views.py**

Add imports at top of `accounts/views.py`:

```python
from .models import InviteCode, Membership, User
```

Replace the `home` function and add new views after it:

```python
@login_required
def home(request):
    """Root redirect — route by membership status."""
    try:
        membership = request.user.membership
        if membership.status == "pending":
            return redirect("pending_approval")
        return redirect("dashboard")
    except Membership.DoesNotExist:
        return redirect("invite_code")


@login_required
def invite_code_page(request):
    """초대코드 입력 화면."""
    # Already has active membership — go to dashboard
    try:
        if request.user.membership.status == "active":
            return redirect("dashboard")
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
    except Membership.DoesNotExist:
        return redirect("invite_code")

    return render(request, "accounts/pending_approval.html")
```

- [ ] **Step 6: Add URLs to accounts/urls.py**

Add to urlpatterns:

```python
path("accounts/invite/", views.invite_code_page, name="invite_code"),
path("accounts/pending/", views.pending_approval_page, name="pending_approval"),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/accounts/test_onboarding.py -v`
Expected: All 8 tests PASS

- [ ] **Step 8: Commit**

```bash
git add accounts/views.py accounts/urls.py accounts/templates/accounts/
git commit -m "feat(accounts): add invite code and pending approval onboarding flow"
```

---

### Task 4: _get_org 수정 + dashboard 보호

**Files:**
- Modify: `projects/views.py:59-61`
- Modify: `projects/views.py:2358-2398` (dashboard)
- Modify: `tests/conftest.py`

- [ ] **Step 1: Update test fixtures to include Membership.status**

In `tests/conftest.py`, update the `user` fixture (line 19):

```python
@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="consultant1", password="testpass123")
    Membership.objects.create(user=u, organization=org, status="active")
    return u
```

Update `other_user` fixture (line 26):

```python
@pytest.fixture
def other_user(db, org):
    u = User.objects.create_user(username="consultant2", password="testpass123")
    Membership.objects.create(user=u, organization=org, status="active")
    return u
```

Update `other_org_user` fixture (line 34):

```python
@pytest.fixture
def other_org_user(db):
    other_org = Organization.objects.create(name="Other Org")
    u = User.objects.create_user(username="outsider", password="testpass123")
    Membership.objects.create(user=u, organization=other_org, status="active")
    return u
```

- [ ] **Step 2: Modify _get_org to filter by active status**

In `projects/views.py`, replace lines 59-61:

```python
def _get_org(request):
    """Return the current user's Organization via active Membership, or 404."""
    return get_object_or_404(
        Organization,
        memberships__user=request.user,
        memberships__status="active",
    )
```

- [ ] **Step 3: Add membership_required to dashboard view**

In `projects/views.py`, add import at top:

```python
from accounts.decorators import membership_required
```

Update the dashboard function (line 2358):

```python
@login_required
@membership_required
def dashboard(request):
```

- [ ] **Step 4: Run existing tests to verify nothing breaks**

Run: `uv run pytest -v --timeout=30`
Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/views.py tests/conftest.py
git commit -m "feat(projects): update _get_org to require active membership"
```

---

### Task 5: 기존 view에 권한 데코레이터 적용

**Files:**
- Modify: `projects/views.py` — owner-only views에 `@role_required("owner")` 추가
- Modify: `clients/views.py` — create/update/delete에 `@role_required("owner")` 추가
- Modify: `clients/views.py` — _get_org 수정
- Test: `tests/accounts/test_rbac.py` (기존 파일에 추가)

- [ ] **Step 1: Write failing integration test**

Append to `tests/accounts/test_rbac.py`:

```python
@pytest.mark.django_db
class TestViewPermissions:
    def test_consultant_cannot_create_client(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = __import__("django.test", fromlist=["Client"]).Client()
        client.force_login(user)

        response = client.get("/clients/new/")
        assert response.status_code == 403

    def test_owner_can_create_client(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="own", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="owner", status="active"
        )
        client = __import__("django.test", fromlist=["Client"]).Client()
        client.force_login(user)

        response = client.get("/clients/new/")
        assert response.status_code == 200

    def test_consultant_cannot_create_project(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con2", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = __import__("django.test", fromlist=["Client"]).Client()
        client.force_login(user)

        response = client.get("/projects/new/")
        assert response.status_code == 403

    def test_consultant_can_read_client_list(self):
        org = Organization.objects.create(name="Org")
        user = User.objects.create_user(username="con3", password="pass")
        Membership.objects.create(
            user=user, organization=org, role="consultant", status="active"
        )
        client = __import__("django.test", fromlist=["Client"]).Client()
        client.force_login(user)

        response = client.get("/clients/")
        assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_rbac.py::TestViewPermissions -v`
Expected: FAIL — consultant can currently access all views (200 instead of 403)

- [ ] **Step 3: Apply role_required to clients/views.py**

Add import at top:

```python
from accounts.decorators import membership_required, role_required
```

Add `@membership_required` to all views. Add `@role_required("owner")` to write views:

```python
# client_list — all roles can read
@login_required
@membership_required
def client_list(request):
    ...

# client_create — owner only
@login_required
@role_required("owner")
def client_create(request):
    ...

# client_detail — all roles can read
@login_required
@membership_required
def client_detail(request, pk):
    ...

# client_update — owner only
@login_required
@role_required("owner")
def client_update(request, pk):
    ...

# client_delete — owner only
@login_required
@role_required("owner")
def client_delete(request, pk):
    ...

# contract_create — owner only
@login_required
@role_required("owner")
def contract_create(request, pk):
    ...

# contract_update — owner only
@login_required
@role_required("owner")
def contract_update(request, pk, contract_pk):
    ...

# contract_delete — owner only
@login_required
@role_required("owner")
def contract_delete(request, pk, contract_pk):
    ...
```

Apply `@role_required("owner")` to all reference views in `clients/views.py` (university/company/cert CRUD, import, export, autofill) — these are accessed via `/reference/` URLs defined in `clients/urls_reference.py`.

Also update `_get_org` in `clients/views.py` to filter by active status:

```python
def _get_org(request):
    return get_object_or_404(
        Organization,
        memberships__user=request.user,
        memberships__status="active",
    )
```

- [ ] **Step 4: Apply role_required to projects/views.py**

Add import at top:

```python
from accounts.decorators import membership_required, role_required
```

Apply to owner-only views:

```python
# project_create — owner only
@login_required
@role_required("owner")
def project_create(request):
    ...

# project_delete — owner only
@login_required
@role_required("owner")
def project_delete(request, pk):
    ...

# approval_queue — owner only
@login_required
@role_required("owner")
def approval_queue(request):
    ...

# approval_decide — owner only
@login_required
@role_required("owner")
def approval_decide(request, appr_pk):
    ...
```

Apply `@membership_required` to all remaining views (project_list, project_detail, all tab views, all CRUD views). The `@membership_required` goes after `@login_required` on every view function.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/accounts/test_rbac.py -v`
Expected: All tests PASS

Run: `uv run pytest -v --timeout=30`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add projects/views.py clients/views.py tests/accounts/test_rbac.py
git commit -m "feat: apply RBAC decorators to all client and project views"
```

---

### Task 6: 프로젝트 목록 consultant 필터링

**Files:**
- Modify: `projects/views.py:78-170` (project_list)

- [ ] **Step 1: Write failing test**

Append to `tests/accounts/test_rbac.py`:

```python
from clients.models import Client
from projects.models import Project, ProjectStatus


@pytest.mark.django_db
class TestProjectFiltering:
    def test_consultant_sees_only_assigned_projects(self):
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="owner", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        consultant = User.objects.create_user(username="con", password="p")
        Membership.objects.create(
            user=consultant, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Client", organization=org)

        # Project assigned to consultant
        p1 = Project.objects.create(
            title="Assigned",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )
        p1.consultants.add(consultant)

        # Project NOT assigned to consultant
        Project.objects.create(
            title="Not Assigned",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )

        test_client = __import__("django.test", fromlist=["Client"]).Client()
        test_client.force_login(consultant)

        response = test_client.get("/projects/")
        content = response.content.decode()
        assert "Assigned" in content
        assert "Not Assigned" not in content

    def test_owner_sees_all_projects(self):
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="owner2", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        client_co = Client.objects.create(name="Client", organization=org)

        Project.objects.create(
            title="Project1",
            client=client_co,
            organization=org,
            status=ProjectStatus.SEARCHING,
            created_by=owner,
        )

        test_client = __import__("django.test", fromlist=["Client"]).Client()
        test_client.force_login(owner)

        response = test_client.get("/projects/")
        content = response.content.decode()
        assert "Project1" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectFiltering -v`
Expected: FAIL — consultant currently sees all projects

- [ ] **Step 3: Modify project_list to filter by role**

In `projects/views.py`, within the `project_list` function, after `org = _get_org(request)`, add role-based filtering:

```python
@login_required
@membership_required
def project_list(request):
    org = _get_org(request)

    # Role-based filtering
    membership = request.user.membership
    if membership.role == "owner":
        qs = Project.objects.filter(organization=org)
    else:
        qs = Project.objects.filter(
            organization=org, consultants=request.user
        )

    # ... rest of existing filter/sort logic uses qs instead of Project.objects.filter(organization=org)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectFiltering -v`
Expected: All tests PASS

Run: `uv run pytest -v --timeout=30`
Expected: All existing tests still PASS

- [ ] **Step 5: Commit**

```bash
git add projects/views.py tests/accounts/test_rbac.py
git commit -m "feat(projects): filter project list by consultant assignment"
```

---

### Task 7: 사이드바 역할별 메뉴 필터링

**Files:**
- Modify: `templates/common/nav_sidebar.html`
- Modify: `templates/common/nav_bottom.html`

- [ ] **Step 1: Modify nav_sidebar.html**

Replace the entire content of `templates/common/nav_sidebar.html`:

```html
<div class="mb-8">
  <h1 class="text-heading font-bold text-primary">synco</h1>
</div>
<nav class="space-y-1 flex-1" id="sidebar-nav" aria-label="사이드바 네비게이션">
  <a href="/"
     hx-get="/" hx-target="#main-content" hx-push-url="true"
     data-nav="dashboard"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
    대시보드
  </a>
  <a href="/candidates/"
     hx-get="/candidates/" hx-target="#main-content" hx-push-url="true"
     data-nav="candidates"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
    후보자
  </a>
  <a href="/projects/"
     hx-get="/projects/" hx-target="#main-content" hx-push-url="true"
     data-nav="projects"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/></svg>
    프로젝트
  </a>
  <a href="/clients/"
     hx-get="/clients/" hx-target="#main-content" hx-push-url="true"
     data-nav="clients"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>
    고객사
  </a>
  {% if membership and membership.role == 'owner' %}
  <a href="/reference/"
     hx-get="/reference/" hx-target="#main-content" hx-push-url="true"
     data-nav="reference"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>
    레퍼런스
  </a>
  {% endif %}
  {% if membership and membership.role == 'owner' and pending_approval_count and pending_approval_count > 0 %}
  <a href="/projects/approvals/"
     hx-get="/projects/approvals/" hx-target="#main-content" hx-push-url="true"
     data-nav="approvals"
     class="sidebar-tab flex items-center justify-between px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <span class="flex items-center gap-3">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
      승인 요청
    </span>
    <span class="bg-red-500 text-white text-[12px] font-bold rounded-full px-2 py-0.5">{{ pending_approval_count }}</span>
  </a>
  {% endif %}
  <a href="/news/"
     hx-get="/news/" hx-target="#main-content" hx-push-url="true"
     data-nav="news"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z"/></svg>
    뉴스피드
    {% if has_new_news %}<span class="w-2 h-2 bg-red-500 rounded-full"></span>{% endif %}
  </a>
  {% if membership and membership.role == 'owner' %}
  <a href="/organization/"
     hx-get="/organization/" hx-target="#main-content" hx-push-url="true"
     data-nav="organization"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
    조직 관리
  </a>
  {% endif %}
  <a href="/accounts/settings/"
     hx-get="/accounts/settings/" hx-target="#main-content" hx-push-url="true"
     data-nav="settings"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
    설정
  </a>

<script>
function updateSidebar() {
  var path = window.location.pathname;
  document.querySelectorAll('.sidebar-tab').forEach(function(tab) {
    var key = tab.dataset.nav;
    var active = (key === 'dashboard' && (path === '/' || path.startsWith('/dashboard'))) ||
                 (key === 'candidates' && path.startsWith('/candidates')) ||
                 (key === 'projects' && path.startsWith('/projects')) ||
                 (key === 'clients' && path.startsWith('/clients')) ||
                 (key === 'reference' && path.startsWith('/reference')) ||
                 (key === 'approvals' && path.startsWith('/projects/approvals')) ||
                 (key === 'news' && path.startsWith('/news')) ||
                 (key === 'organization' && path.startsWith('/organization')) ||
                 (key === 'settings' && path.includes('/settings'));
    tab.className = 'sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] ' +
      (active ? 'bg-primary-light text-primary font-semibold' : 'text-gray-500 hover:bg-gray-50');
  });
}
updateSidebar();
document.body.addEventListener('htmx:pushedIntoHistory', updateSidebar);
document.body.addEventListener('htmx:replacedInHistory', updateSidebar);
</script>
</nav>
```

- [ ] **Step 2: Update nav_bottom.html similarly**

Apply the same `{% if membership and membership.role == 'owner' %}` guards to the mobile bottom navigation for reference and organization links.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add templates/common/nav_sidebar.html templates/common/nav_bottom.html
git commit -m "feat(ui): filter sidebar and bottom nav menus by user role"
```

---

### Task 8: 프로젝트 생성 시 담당 컨설턴트 지정

**Files:**
- Modify: `projects/forms.py` (ProjectForm)
- Modify: `projects/views.py` (project_create, project_update)

- [ ] **Step 1: Write failing test**

Append to `tests/accounts/test_rbac.py`:

```python
@pytest.mark.django_db
class TestProjectConsultantAssignment:
    def test_owner_can_assign_consultants_on_create(self):
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="own_a", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        con = User.objects.create_user(username="con_a", password="p")
        Membership.objects.create(
            user=con, organization=org, role="consultant", status="active"
        )
        client_co = Client.objects.create(name="Co", organization=org)

        test_client = __import__("django.test", fromlist=["Client"]).Client()
        test_client.force_login(owner)

        response = test_client.post("/projects/new/", {
            "title": "New Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
            "consultants": [str(con.pk)],
        }, follow=True)
        project = Project.objects.get(title="New Project")
        assert con in project.consultants.all()

    def test_no_consultants_defaults_to_owner(self):
        org = Organization.objects.create(name="Org")
        owner = User.objects.create_user(username="own_b", password="p")
        Membership.objects.create(
            user=owner, organization=org, role="owner", status="active"
        )
        client_co = Client.objects.create(name="Co2", organization=org)

        test_client = __import__("django.test", fromlist=["Client"]).Client()
        test_client.force_login(owner)

        response = test_client.post("/projects/new/", {
            "title": "Solo Project",
            "client": str(client_co.pk),
            "jd_text": "Test JD",
        }, follow=True)
        project = Project.objects.get(title="Solo Project")
        assert owner in project.consultants.all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectConsultantAssignment -v`
Expected: FAIL

- [ ] **Step 3: Add consultants field to ProjectForm**

In `projects/forms.py`, add to `ProjectForm.Meta.fields` the `consultants` field, and add initialization to filter by organization:

```python
consultants = forms.ModelMultipleChoiceField(
    queryset=User.objects.none(),
    required=False,
    widget=forms.CheckboxSelectMultiple,
    label="담당 컨설턴트",
)

def __init__(self, *args, org=None, **kwargs):
    super().__init__(*args, **kwargs)
    if org:
        self.fields["consultants"].queryset = User.objects.filter(
            membership__organization=org,
            membership__status="active",
        )
```

- [ ] **Step 4: Update project_create view**

In `projects/views.py`, within `project_create`, pass org to form and handle default consultant:

```python
form = ProjectForm(request.POST or None, request.FILES or None, org=org)
if form.is_valid():
    project = form.save(commit=False)
    project.organization = org
    project.created_by = request.user
    project.save()
    form.save_m2m()
    # Default: if no consultants selected, assign creator
    if not project.consultants.exists():
        project.consultants.add(request.user)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/accounts/test_rbac.py::TestProjectConsultantAssignment -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add projects/forms.py projects/views.py tests/accounts/test_rbac.py
git commit -m "feat(projects): add consultant assignment on project create/update"
```

---

### Task 9: 빈 화면 CTA (역할별 분기)

**Files:**
- Modify: `projects/templates/projects/partials/view_board.html` (or equivalent empty state)
- Modify: `clients/templates/clients/client_list.html`

- [ ] **Step 1: Update project list empty state**

In the project list template, find the empty state section and add role-based CTA:

```html
{% if not projects %}
<div class="flex flex-col items-center justify-center py-16 text-center">
  <svg class="w-12 h-12 text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
  </svg>
  {% if membership and membership.role == 'owner' %}
    <p class="text-gray-500 mb-4">프로젝트가 없습니다.</p>
    <a href="{% url 'projects:project_create' %}"
       class="px-4 py-2 bg-primary text-white rounded-lg text-sm">
      새 프로젝트 만들기
    </a>
  {% else %}
    <p class="text-gray-500">배정된 프로젝트가 없습니다.</p>
    <p class="text-gray-400 text-sm mt-1">관리자가 프로젝트를 배정하면 여기에 표시됩니다.</p>
  {% endif %}
</div>
{% endif %}
```

- [ ] **Step 2: Update client list empty state**

```html
{% if not clients %}
<div class="flex flex-col items-center justify-center py-16 text-center">
  {% if membership and membership.role == 'owner' %}
    <p class="text-gray-500 mb-4">등록된 고객사가 없습니다.</p>
    <a href="{% url 'clients:client_create' %}"
       class="px-4 py-2 bg-primary text-white rounded-lg text-sm">
      첫 고객사를 등록하세요
    </a>
  {% else %}
    <p class="text-gray-500">등록된 고객사가 없습니다.</p>
  {% endif %}
</div>
{% endif %}
```

- [ ] **Step 3: Update dashboard empty state**

In the dashboard template, add owner-specific CTA when no data:

```html
{% if not today_actions and not weekly_schedule %}
  {% if membership and membership.role == 'owner' %}
    <p class="text-gray-500 mb-4">아직 진행 중인 업무가 없습니다.</p>
    <a href="/clients/"
       hx-get="/clients/" hx-target="#main-content" hx-push-url="true"
       class="px-4 py-2 bg-primary text-white rounded-lg text-sm">
      고객사를 등록하고 첫 프로젝트를 시작하세요
    </a>
  {% else %}
    <p class="text-gray-500">배정된 프로젝트가 없습니다.</p>
    <p class="text-gray-400 text-sm mt-1">관리자가 프로젝트를 배정하면 여기에 표시됩니다.</p>
  {% endif %}
{% endif %}
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/templates/ clients/templates/
git commit -m "feat(ui): add role-based empty state CTAs for projects, clients, dashboard"
```

---

### Task 10: 전체 통합 검증

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 2: Run lint**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: No errors

- [ ] **Step 3: Check migrations**

Run: `uv run python manage.py makemigrations --check --dry-run`
Expected: "No changes detected"

- [ ] **Step 4: Manual verification checklist**

Start dev server: `./dev.sh`

1. 카카오 로그인 → Membership 없음 → 초대코드 입력 화면 표시
2. 유효한 owner 코드 입력 → 즉시 대시보드
3. 유효한 consultant 코드 입력 → 승인 대기 화면
4. Django admin에서 Membership.status=active 변경 → 대시보드 접근 가능
5. consultant로 로그인 → 사이드바에 레퍼런스/조직관리 메뉴 없음
6. consultant로 /clients/new/ 직접 접근 → 403
7. consultant로 프로젝트 목록 → 배정된 것만 표시
8. owner로 프로젝트 생성 → 담당 컨설턴트 선택 가능

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete RBAC + onboarding (Plan 1/3)"
```
