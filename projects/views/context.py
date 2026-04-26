"""Work-continuity context views."""
from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from accounts.decorators import level_required
from accounts.services.scope import get_scoped_object_or_404
from projects.models import Project
from projects.services.context import (
    discard_context,
    get_active_context,
    get_resume_url,
    save_context,
    validate_draft_data,
)


@login_required
@level_required(1)
@require_http_methods(["GET"])
def project_context(request, pk):
    """GET: Return active context banner partial."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    ctx = get_active_context(project, request.user)
    return render(
        request,
        "projects/partials/context_banner.html",
        {
            "project": project,
            "context": ctx,
            "resume_url": get_resume_url(ctx) if ctx else None,
        },
    )


@login_required
@level_required(1)
@require_http_methods(["POST"])
def project_context_save(request, pk):
    """POST: Save/update context (autosave endpoint)."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    content_type = request.content_type or ""
    if "application/json" in content_type:
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return HttpResponse(status=400)
    else:
        raw = request.POST.get("data", request.body.decode("utf-8", errors="replace"))
        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return HttpResponse(status=400)

    last_step = body.get("last_step", "")
    pending_action = body.get("pending_action", "")
    draft_data = body.get("draft_data", {})

    if not validate_draft_data(draft_data):
        return HttpResponse(status=400)

    save_context(
        project=project,
        user=request.user,
        last_step=last_step,
        pending_action=pending_action,
        draft_data=draft_data,
    )
    return HttpResponse(status=204)


@login_required
@level_required(1)
@require_http_methods(["POST"])
def project_context_resume(request, pk):
    """POST: Resume from context → redirect to target form."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    ctx = get_active_context(project, request.user)
    if not ctx:
        return HttpResponse(status=404)
    resume_url = get_resume_url(ctx)
    if not resume_url:
        return HttpResponse(status=404)
    response = HttpResponse(status=200)
    response["HX-Redirect"] = resume_url
    return response


@login_required
@level_required(1)
@require_http_methods(["POST"])
def project_context_discard(request, pk):
    """POST: Discard the active context."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    discard_context(project, request.user)
    return render(
        request,
        "projects/partials/context_banner.html",
        {
            "project": project,
            "context": None,
            "resume_url": None,
        },
    )
