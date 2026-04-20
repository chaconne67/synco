from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse


# 하드코딩 mockup. 실제 모델 매핑은 User(name/email/phone) + Membership(role/status)만.
# desk/joined_year/summary/top_clients 등은 mockup 표시용으로 templates/accounts/team.html에만 존재.
TEAM_MEMBERS = {
    "jeong": {
        "slug": "jeong",
        "name": "정호열",
        "email": "jeong@synco.kr",
        "phone": "",
        "role": "owner",
        "status": "active",
    },
    "kim": {
        "slug": "kim",
        "name": "김현정",
        "email": "kim@synco.kr",
        "phone": "",
        "role": "consultant",
        "status": "active",
    },
    "park-jeong-il": {
        "slug": "park-jeong-il",
        "name": "박정일",
        "email": "park.j@synco.kr",
        "phone": "",
        "role": "consultant",
        "status": "active",
    },
    "park-ji-young": {
        "slug": "park-ji-young",
        "name": "박지영",
        "email": "park.jy@synco.kr",
        "phone": "",
        "role": "consultant",
        "status": "active",
    },
    "jeon": {
        "slug": "jeon",
        "name": "전병권",
        "email": "jeon@synco.kr",
        "phone": "",
        "role": "consultant",
        "status": "active",
    },
    "lim": {
        "slug": "lim",
        "name": "임성민",
        "email": "lim@synco.kr",
        "phone": "",
        "role": "viewer",
        "status": "active",
    },
}


@login_required
def team_view(request):
    return render(request, "accounts/team.html")


@login_required
def team_member_edit(request, slug):
    member = TEAM_MEMBERS.get(slug)
    if member is None:
        raise Http404("Team member not found")
    if request.method == "POST":
        # Mockup: 저장 동작은 연결되지 않음. 실제 모델 연동 전까지 no-op 후 팀 페이지로 복귀.
        return HttpResponseRedirect(reverse("team"))
    return render(request, "accounts/team_member_edit.html", {"member": member})
