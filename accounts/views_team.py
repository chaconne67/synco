from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def team_view(request):
    return render(request, "accounts/team.html")
