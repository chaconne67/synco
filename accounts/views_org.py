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
    return render(
        request,
        "accounts/org_base.html",
        {
            **context,
            "tab_template": "accounts/partials/org_info.html",
        },
    )


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
    return render(
        request,
        "accounts/org_base.html",
        {
            **context,
            "tab_template": "accounts/partials/org_members.html",
        },
    )


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
    return render(
        request,
        "accounts/partials/org_members.html",
        {
            "org": org,
            "members": members,
            "active_tab": "members",
            "message": message,
        },
    )


@login_required
@role_required("owner")
@require_POST
def org_member_approve(request, pk):
    """POST /org/members/<pk>/approve/ — 멤버 승인."""
    org = _get_org(request)
    membership = get_object_or_404(
        Membership, pk=pk, organization=org, status="pending"
    )
    membership.status = "active"
    membership.save(update_fields=["status", "updated_at"])

    return _render_members_partial(
        request,
        org,
        f"{membership.user.first_name or membership.user.username}님이 승인되었습니다.",
    )


@login_required
@role_required("owner")
@require_POST
def org_member_reject(request, pk):
    """POST /org/members/<pk>/reject/ — 멤버 거절."""
    org = _get_org(request)
    membership = get_object_or_404(
        Membership, pk=pk, organization=org, status="pending"
    )
    membership.status = "rejected"
    membership.save(update_fields=["status", "updated_at"])

    return _render_members_partial(
        request,
        org,
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
        request,
        org,
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
            return HttpResponseBadRequest(
                "조직에 owner가 1명뿐이면 제거할 수 없습니다."
            )

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
    return render(
        request,
        "accounts/org_base.html",
        {
            **context,
            "tab_template": "accounts/partials/org_invites.html",
        },
    )


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
    return render(
        request,
        "accounts/partials/org_invites.html",
        {
            "org": org,
            "codes": codes,
            "form": form,
            "active_tab": "invites",
            "message": message,
        },
    )


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
    return render(
        request,
        "accounts/partials/org_invites.html",
        {
            "org": org,
            "codes": codes,
            "form": form,
            "active_tab": "invites",
            "message": "초대코드가 비활성화되었습니다.",
        },
    )
