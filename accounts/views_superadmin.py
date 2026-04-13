"""SuperAdmin 뷰 — 슈퍼유저 전용 업체 등록/초대코드 발급."""

from django.http import Http404
from django.shortcuts import redirect, render

from .models import InviteCode, Organization


def _superuser_only(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not request.user.is_superuser:
            raise Http404()
        return view_func(request, *args, **kwargs)

    return wrapper


@_superuser_only
def companies_page(request):
    error = None
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            error = "업체명을 입력해주세요."
        else:
            org = Organization.objects.create(name=name)
            InviteCode.objects.create(
                organization=org,
                role=InviteCode.Role.OWNER,
                created_by=request.user,
            )
            return redirect("superadmin_companies")

    orgs = (
        Organization.objects.all()
        .order_by("-created_at")
        .prefetch_related("invite_codes")
    )
    rows = []
    for org in orgs:
        owner_invites = [
            ic for ic in org.invite_codes.all() if ic.role == InviteCode.Role.OWNER
        ]
        latest_owner_invite = owner_invites[0] if owner_invites else None
        rows.append(
            {
                "org": org,
                "invite": latest_owner_invite,
            }
        )

    return render(
        request,
        "accounts/superadmin_companies.html",
        {"error": error, "rows": rows},
    )
