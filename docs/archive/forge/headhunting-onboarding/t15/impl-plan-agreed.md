# t15: 조직 관리 뷰 + URL + 테스트

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** owner 전용 조직 관리 뷰(조직 정보, 멤버 관리, 초대코드 관리)와 URL, 테스트를 구축한다.

**Design spec:** `docs/forge/headhunting-onboarding/t15/design-spec.md`

**depends_on:** t12

---

## Changes from Tempering

| Issue | Severity | Resolution |
|-------|----------|------------|
| R1-02: HTMX 렌더링 규약 불일치 | MAJOR | `_is_org_tab_switch()` 패턴 추가, settings 뷰와 동일한 HX-Target 분기 |
| R1-03: HTMX 테스트 누락 | CRITICAL | HTMX 분기 로직을 뷰에 추가. 렌더링 테스트는 t16에서 템플릿과 함께 검증 |
| R1-04: 초대코드 생성 실패 시 성공 메시지 | CRITICAL | message를 is_valid() 블록 내부로 이동, invalid 시 bound form + 에러 반환 |
| R1-05: Cross-org 보안 테스트 누락 | MAJOR | cross-org approve/role/remove/deactivate 차단 테스트 추가 |
| R1-07: 멤버 정렬 순서 불일치 | MINOR | Case/When으로 pending=0, active=1, rejected=2 명시적 정렬 |
| R1-08: 조직 정보 수정 성공 메시지 부재 | MINOR | org_info에 성공 메시지 추가 |

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `accounts/views_org.py` | 생성 | 조직 관리 뷰 (org_redirect, org_info, org_members, org_invites 등) |
| `accounts/urls_org.py` | 생성 | `/org/` URL 구조 |
| `main/urls.py` | 수정 | `/org/` URL include 추가 |
| `tests/accounts/test_org_management.py` | 생성 | 조직 관리 뷰 테스트 |

---

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


@pytest.fixture
def cross_org_setup(db):
    """Two orgs with owners for cross-org isolation tests."""
    org_a = Organization.objects.create(name="Org A")
    owner_a = User.objects.create_user(username="owner_a", password="pass")
    Membership.objects.create(user=owner_a, organization=org_a, role="owner", status="active")

    org_b = Organization.objects.create(name="Org B")
    owner_b = User.objects.create_user(username="owner_b", password="pass")
    Membership.objects.create(user=owner_b, organization=org_b, role="owner", status="active")

    return owner_a, org_a, owner_b, org_b


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

    def test_create_invite_invalid_form_no_success_message(self, owner_setup):
        """Invalid form should NOT show success message."""
        owner, org = owner_setup
        client = TestClient()
        client.force_login(owner)
        response = client.post(
            "/org/invites/create/",
            {"role": "consultant", "max_uses": "0"},  # min is 1
        )
        assert not InviteCode.objects.filter(organization=org, created_by=owner).exists()
        content = response.content.decode()
        assert "생성되었습니다" not in content

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


@pytest.mark.django_db
class TestOrgCrossOrgIsolation:
    """Cross-org security: owner A must not be able to act on org B resources."""

    def test_cross_org_approve_blocked(self, cross_org_setup):
        owner_a, org_a, owner_b, org_b = cross_org_setup
        pending = User.objects.create_user(username="pending_b", password="pass")
        m = Membership.objects.create(
            user=pending, organization=org_b, role="consultant", status="pending"
        )
        client = TestClient()
        client.force_login(owner_a)
        response = client.post(f"/org/members/{m.pk}/approve/")
        assert response.status_code == 404
        m.refresh_from_db()
        assert m.status == "pending"

    def test_cross_org_role_change_blocked(self, cross_org_setup):
        owner_a, org_a, owner_b, org_b = cross_org_setup
        member_b = User.objects.create_user(username="member_b", password="pass")
        m = Membership.objects.create(
            user=member_b, organization=org_b, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(owner_a)
        response = client.post(f"/org/members/{m.pk}/role/", {"role": "viewer"})
        assert response.status_code == 404
        m.refresh_from_db()
        assert m.role == "consultant"

    def test_cross_org_remove_blocked(self, cross_org_setup):
        owner_a, org_a, owner_b, org_b = cross_org_setup
        member_b = User.objects.create_user(username="rem_b", password="pass")
        m = Membership.objects.create(
            user=member_b, organization=org_b, role="consultant", status="active"
        )
        client = TestClient()
        client.force_login(owner_a)
        response = client.post(f"/org/members/{m.pk}/remove/")
        assert response.status_code == 404
        assert Membership.objects.filter(pk=m.pk).exists()

    def test_cross_org_invite_deactivate_blocked(self, cross_org_setup):
        owner_a, org_a, owner_b, org_b = cross_org_setup
        code = InviteCode.objects.create(
            organization=org_b, role="consultant", created_by=owner_b
        )
        client = TestClient()
        client.force_login(owner_a)
        response = client.post(f"/org/invites/{code.pk}/deactivate/")
        assert response.status_code == 404
        code.refresh_from_db()
        assert code.is_active is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/accounts/test_org_management.py -v`
Expected: FAIL — URLs not found, views not defined

- [ ] **Step 3: Create accounts/views_org.py**

```python
# accounts/views_org.py
"""조직 관리 뷰 — owner 전용."""
from django.contrib.auth.decorators import login_required
from django.db.models import Case, Value, When
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import InviteCodeCreateForm, OrganizationForm
from .helpers import _get_org
from .models import InviteCode, Membership


def _is_org_tab_switch(request):
    """Check if this is an HTMX tab switch (targeting #org-content)."""
    return (
        getattr(request, "htmx", None)
        and request.headers.get("HX-Target") == "org-content"
    )


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
    message = None

    if request.method == "POST":
        form = OrganizationForm(request.POST, request.FILES, instance=org)
        if form.is_valid():
            form.save()
            message = "조직 정보가 수정되었습니다."

    context = {"org": org, "form": form, "active_tab": "info", "message": message}

    if _is_org_tab_switch(request):
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
    status_order = Case(
        When(status="pending", then=Value(0)),
        When(status="active", then=Value(1)),
        When(status="rejected", then=Value(2)),
    )
    members = (
        Membership.objects.filter(organization=org)
        .select_related("user")
        .annotate(status_order=status_order)
        .order_by("status_order", "-created_at")
    )

    context = {"org": org, "members": members, "active_tab": "members"}

    if _is_org_tab_switch(request):
        return render(request, "accounts/partials/org_members.html", context)
    return render(request, "accounts/org_base.html", {
        **context,
        "tab_template": "accounts/partials/org_members.html",
    })


def _render_members_partial(request, org, message=None):
    """Re-render members partial after a mutation."""
    status_order = Case(
        When(status="pending", then=Value(0)),
        When(status="active", then=Value(1)),
        When(status="rejected", then=Value(2)),
    )
    members = (
        Membership.objects.filter(organization=org)
        .select_related("user")
        .annotate(status_order=status_order)
        .order_by("status_order", "-created_at")
    )
    return render(request, "accounts/partials/org_members.html", {
        "org": org, "members": members, "active_tab": "members",
        "message": message,
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

    return _render_members_partial(
        request, org,
        f"{membership.user.first_name or membership.user.username}님이 승인되었습니다.",
    )


@login_required
@role_required("owner")
@require_POST
def org_member_reject(request, pk):
    """POST /org/members/<pk>/reject/ — 멤버 거절."""
    org = _get_org(request)
    membership = get_object_or_404(Membership, pk=pk, organization=org, status="pending")
    membership.status = "rejected"
    membership.save(update_fields=["status", "updated_at"])

    return _render_members_partial(
        request, org,
        f"{membership.user.first_name or membership.user.username}님의 가입이 거절되었습니다.",
    )


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

    return _render_members_partial(
        request, org,
        f"{membership.user.first_name or membership.user.username}님의 역할이 {new_role}로 변경되었습니다.",
    )


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

    return _render_members_partial(request, org, f"{name}님이 조직에서 제거되었습니다.")


@login_required
@role_required("owner")
def org_invites(request):
    """GET /org/invites/ — 초대코드 관리 탭."""
    org = _get_org(request)
    codes = InviteCode.objects.filter(organization=org).order_by("-created_at")
    form = InviteCodeCreateForm()

    context = {"org": org, "codes": codes, "form": form, "active_tab": "invites"}

    if _is_org_tab_switch(request):
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
    message = None

    if form.is_valid():
        InviteCode.objects.create(
            organization=org,
            role=form.cleaned_data["role"],
            max_uses=form.cleaned_data["max_uses"],
            expires_at=form.cleaned_data.get("expires_at"),
            created_by=request.user,
        )
        message = "초대코드가 생성되었습니다."
        form = InviteCodeCreateForm()  # Reset only on success

    codes = InviteCode.objects.filter(organization=org).order_by("-created_at")
    return render(request, "accounts/partials/org_invites.html", {
        "org": org, "codes": codes, "form": form, "active_tab": "invites",
        "message": message,
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
git add accounts/views_org.py accounts/urls_org.py main/urls.py tests/accounts/test_org_management.py
git commit -m "feat(accounts): add org management views — info, members, invites"
```

<!-- forge:t15:impl-plan:complete:2026-04-12T23:30:00+09:00 -->
