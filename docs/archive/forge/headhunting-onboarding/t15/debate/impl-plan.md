# t15: 조직 관리 뷰 + URL + 테스트

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** owner 전용 조직 관리 뷰(조직 정보, 멤버 관리, 초대코드 관리)와 URL, 테스트를 구축한다.

**Design spec:** `docs/forge/headhunting-onboarding/t15/design-spec.md`

**depends_on:** t12

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
