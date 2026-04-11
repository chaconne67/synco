# Phase 1 구현 계획: 모델 + 데코레이터 + 온보딩 플로우

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** InviteCode 모델과 Membership.status를 추가하고, role_required/membership_required 데코레이터와 context processor를 생성하고, 카카오 로그인 후 초대코드 입력 → 승인 대기 온보딩 플로우를 구현한다.

**Architecture:** accounts 앱에 InviteCode 모델과 Membership.status 필드를 추가한다. 카카오 로그인 플로우를 수정하여 Membership 없는 사용자를 초대코드 입력 화면으로 보낸다. `role_required` 데코레이터로 view 단 접근 제어를 하고, context processor로 membership 정보를 모든 템플릿에 주입한다.

**Tech Stack:** Django 5.2, HTMX, Tailwind CSS, pytest

**Design spec:** `docs/plans/headhunting-onboarding/phase1/design.md`

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `accounts/models.py` | 수정 | InviteCode 모델 추가, Membership.status 필드 추가 |
| `accounts/admin.py` | 수정 | InviteCode admin 등록 |
| `accounts/decorators.py` | 생성 | role_required, membership_required 데코레이터 |
| `accounts/context_processors.py` | 생성 | membership context processor |
| `main/settings.py` | 수정 | context_processors에 membership 추가 |
| `accounts/views.py` | 수정 | kakao_callback 수정, invite_code/pending 뷰 추가 |
| `accounts/urls.py` | 수정 | 초대코드/승인대기 URL 추가 |
| `accounts/templates/accounts/invite_code.html` | 생성 | 초대코드 입력 화면 |
| `accounts/templates/accounts/pending_approval.html` | 생성 | 승인 대기 화면 |
| `tests/accounts/test_invite_code.py` | 생성 | InviteCode 모델 테스트 |
| `tests/accounts/test_rbac.py` | 생성 | 역할별 접근 제어 테스트 |
| `tests/accounts/test_onboarding.py` | 생성 | 온보딩 플로우 테스트 |

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
