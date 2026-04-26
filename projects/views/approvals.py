"""Approval workflow and project auto-action views."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.decorators import level_required
from accounts.services.scope import get_scoped_object_or_404
from projects.models import AutoAction, Project, ProjectApproval, ProjectStatus
from projects.services.auto_actions import (
    ConflictError,
    apply_action,
    dismiss_action,
    get_pending_actions,
)


@login_required
@level_required(2)
def approval_queue(request):
    """OWNER-only: list pending approval requests."""

    approvals = (
        ProjectApproval.objects.filter(
            status=ProjectApproval.Status.PENDING,
        )
        .select_related(
            "project",
            "project__client",
            "requested_by",
            "conflict_project",
            "conflict_project__client",
        )
        .order_by("-created_at")
    )

    # For each approval, compute merge target candidates
    for appr in approvals:
        if appr.project:
            appr.merge_candidates = (
                Project.objects.filter(
                    client=appr.project.client,
                )
                .exclude(
                    status=ProjectStatus.CLOSED,
                )
                .exclude(
                    pk=appr.project_id,
                )
            )
        else:
            appr.merge_candidates = Project.objects.none()

    return render(
        request,
        "projects/approval_queue.html",
        {"approvals": approvals, "approval_count": approvals.count()},
    )


@login_required
@level_required(2)
@require_http_methods(["POST"])
def approval_decide(request, appr_pk):
    """OWNER-only: decide on an approval request."""

    from projects.forms import ApprovalDecisionForm
    from projects.services.approval import (
        InvalidApprovalTransition,
        approve_project,
        merge_project,
        reject_project,
        send_admin_message,
    )

    approval = get_object_or_404(
        ProjectApproval,
        pk=appr_pk,
    )

    form = ApprovalDecisionForm(request.POST)
    if not form.is_valid():
        return redirect("projects:approval_queue")

    decision = form.cleaned_data["decision"]
    response_text = form.cleaned_data.get("response_text", "")
    merge_target_id = form.cleaned_data.get("merge_target")

    try:
        if decision == "승인":
            approve_project(approval, request.user)
        elif decision == "합류":
            merge_target = None
            if merge_target_id:
                merge_target = get_scoped_object_or_404(
                    Project, request.user, pk=merge_target_id
                )
            merge_project(approval, request.user, merge_target=merge_target)
        elif decision == "메시지":
            send_admin_message(approval, request.user, response_text)
        elif decision == "반려":
            reject_project(approval, request.user, response_text=response_text)
    except InvalidApprovalTransition:
        pass  # Already handled -- redirect back to queue

    return redirect("projects:approval_queue")


@login_required
@level_required(1)
@require_http_methods(["POST"])
def approval_cancel(request, pk):
    """Requester cancels their approval request."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    approval = get_object_or_404(
        ProjectApproval,
        project=project,
        requested_by=request.user,
        status=ProjectApproval.Status.PENDING,
    )

    from projects.services.approval import cancel_approval

    cancel_approval(approval)

    return redirect("projects:project_list")


@login_required
@level_required(1)
@require_http_methods(["GET"])
def project_auto_actions(request, pk):
    """GET: List pending auto-actions."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    actions = get_pending_actions(project)
    return render(
        request,
        "projects/partials/auto_actions_banner.html",
        {
            "project": project,
            "actions": actions,
        },
    )


@login_required
@level_required(1)
@require_http_methods(["POST"])
def auto_action_apply(request, pk, action_pk):
    """POST: Apply an auto-action."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    action = get_object_or_404(AutoAction, pk=action_pk, project=project)
    try:
        apply_action(action.pk, request.user)
    except ConflictError:
        return HttpResponse("이미 처리된 액션입니다.", status=409)
    actions = get_pending_actions(project)
    return render(
        request,
        "projects/partials/auto_actions_banner.html",
        {
            "project": project,
            "actions": actions,
        },
    )


@login_required
@level_required(1)
@require_http_methods(["POST"])
def auto_action_dismiss(request, pk, action_pk):
    """POST: Dismiss an auto-action."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    action = get_object_or_404(AutoAction, pk=action_pk, project=project)
    try:
        dismiss_action(action.pk, request.user)
    except ConflictError:
        return HttpResponse("이미 처리된 액션입니다.", status=409)
    actions = get_pending_actions(project)
    return render(
        request,
        "projects/partials/auto_actions_banner.html",
        {
            "project": project,
            "actions": actions,
        },
    )
