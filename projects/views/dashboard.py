"""Dashboard view."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.decorators import level_required
from projects.services.dashboard import get_dashboard_context


@login_required
@level_required(1)
def dashboard(request):
    """대시보드 메인 화면 (Phase 2a: 실데이터 연결 진행 중)."""
    ctx = get_dashboard_context(request.user)
    if getattr(request, "htmx", None):
        return render(request, "projects/partials/dash_full.html", ctx)
    return render(request, "projects/dashboard.html", ctx)
