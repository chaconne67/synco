"""Interview CRUD views."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from accounts.decorators import level_required
from accounts.services.scope import get_scoped_object_or_404
from projects.views._helpers import _has_pending_approval
from projects.forms import InterviewForm, InterviewResultForm
from projects.models import Interview, Project


@login_required
@level_required(1)
def interview_create(request, pk):
    """면접 등록."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    if _has_pending_approval(project):
        return HttpResponse(status=403)

    if request.method == "POST":
        form = InterviewForm(request.POST, project=project)
        if form.is_valid():
            form.save()

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "interviewChanged"},
            )
    else:
        form = InterviewForm(project=project)

    # 프리필: query param으로 submission 전달 시
    submission_id = request.GET.get("submission")
    if submission_id and request.method != "POST":
        form.initial["submission"] = submission_id
        # round 자동 계산: 해당 submission의 max round + 1
        max_round = (
            Interview.objects.filter(submission_id=submission_id)
            .order_by("-round")
            .values_list("round", flat=True)
            .first()
        ) or 0
        form.initial["round"] = max_round + 1

    # 추천 탭에서 "면접 등록 →" 클릭 시: 면접 탭 + 폼을 함께 반환
    hx_target = request.headers.get("HX-Target", "")
    if hx_target == "tab-content":
        from itertools import groupby

        interviews = (
            Interview.objects.filter(submission__project=project)
            .select_related("submission__candidate", "submission__consultant")
            .order_by("submission__candidate__name", "round")
        )
        grouped = []
        for candidate, group in groupby(
            interviews, key=lambda i: i.submission.candidate
        ):
            grouped.append({"candidate": candidate, "interviews": list(group)})
        return render(
            request,
            "projects/partials/tab_interviews_with_form.html",
            {
                "form": form,
                "project": project,
                "is_edit": False,
                "grouped_interviews": grouped,
                "total_count": interviews.count(),
            },
        )

    return render(
        request,
        "projects/partials/interview_form.html",
        {
            "form": form,
            "project": project,
            "is_edit": False,
        },
    )


@login_required
@level_required(1)
def interview_update(request, pk, interview_pk):
    """면접 수정."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    interview = get_scoped_object_or_404(
        Interview,
        request.user,
        pk=interview_pk,
        action_item__application__project=project,
    )

    if request.method == "POST":
        form = InterviewForm(request.POST, instance=interview, project=project)
        if form.is_valid():
            form.save()
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "interviewChanged"},
            )
    else:
        form = InterviewForm(instance=interview, project=project)

    return render(
        request,
        "projects/partials/interview_form.html",
        {
            "form": form,
            "project": project,
            "interview": interview,
            "is_edit": True,
        },
    )


@login_required
@level_required(1)
@require_http_methods(["POST"])
def interview_delete(request, pk, interview_pk):
    """면접 삭제."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    interview = get_scoped_object_or_404(
        Interview,
        request.user,
        pk=interview_pk,
        action_item__application__project=project,
    )

    interview.delete()
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "interviewChanged"},
    )


@login_required
@level_required(1)
def interview_result(request, pk, interview_pk):
    """면접 결과 입력 (대기 → 합격/보류/탈락)."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    interview = get_scoped_object_or_404(
        Interview,
        request.user,
        pk=interview_pk,
        action_item__application__project=project,
    )

    if request.method == "POST":
        form = InterviewResultForm(request.POST)
        if form.is_valid():
            from projects.services.action_lifecycle import (
                InvalidTransition,
                apply_interview_result,
            )

            try:
                apply_interview_result(
                    interview,
                    form.cleaned_data["result"],
                    form.cleaned_data["feedback"],
                )
            except InvalidTransition as e:
                return HttpResponse(str(e), status=400)

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "interviewChanged"},
            )
    else:
        form = InterviewResultForm()

    return render(
        request,
        "projects/partials/interview_result_form.html",
        {
            "form": form,
            "project": project,
            "interview": interview,
        },
    )
