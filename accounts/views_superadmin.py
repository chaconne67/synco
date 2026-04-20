from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from accounts.decorators import level_required
from accounts.models import User


@login_required
@level_required(2)
def pending_users_list(request):
    users = User.objects.filter(level=0).order_by("-date_joined")
    return render(
        request,
        "accounts/superadmin/pending_users.html",
        {"users": users},
    )


@login_required
@level_required(2)
@require_POST
def approve_user(request, user_id):
    new_level = int(request.POST.get("level", 1))
    if new_level not in (1, 2):
        new_level = 1
    User.objects.filter(pk=user_id, level=0).update(level=new_level)
    return redirect("pending_users_list")
