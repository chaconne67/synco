from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.decorators import level_required
from accounts.models import User


@login_required
@level_required(1)
def team_list(request):
    members = User.objects.filter(level__gte=1).order_by("level", "date_joined")
    return render(request, "accounts/team_list.html", {"members": members})
