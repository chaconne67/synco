from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required
from django.db import models as db_models
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import level_required
from accounts.services.scope import get_scoped_object_or_404
from projects.views._helpers import _create_receive_resume_action
from projects.forms import ApplicationCreateForm, ApplicationDropForm
from projects.models import Application, ActionItemStatus, Project
from projects.services.application_lifecycle import (
    create_application,
    drop as drop_application,
    hire as hire_application,
    restore as restore_application,
)


@level_required(1)
def project_add_candidate(request, pk):
    """POST /projects/<pk>/add_candidate/ — Application 생성.
    GET: 후보자 추가 모달 폼 렌더링.
    POST (candidate_id): 서칭 페이지의 "프로젝트에 추가" 버튼 — 단건 직접 추가.
    POST (form): 모달 폼을 통한 추가 (기존 방식).
    """
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    if request.method == "GET":
        form = ApplicationCreateForm()
        return render(
            request,
            "projects/partials/add_candidate_modal.html",
            {"form": form, "project": project},
        )

    # POST — 직접 candidate_id 전달 (서칭 페이지 "프로젝트에 추가" 버튼)
    candidate_id = request.POST.get("candidate_id")
    if candidate_id and "candidate" not in request.POST:
        from candidates.models import Candidate
        from projects.services.searching import add_candidates_to_project

        try:
            candidate_uuid = uuid.UUID(candidate_id)
        except (ValueError, AttributeError):
            return HttpResponseBadRequest("유효하지 않은 candidate_id")

        candidate = Candidate.objects.filter(pk=candidate_uuid).first()
        if candidate is None:
            return HttpResponseBadRequest("후보자를 찾을 수 없습니다")

        add_candidates_to_project(project, [candidate_uuid], created_by=request.user)

        if request.headers.get("HX-Request"):
            response = HttpResponse("")
            response["HX-Trigger"] = "applicationChanged"
            return response
        return redirect("projects:project_detail", pk=project.pk)

    # POST — 모달 폼 (기존 방식)
    form = ApplicationCreateForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/add_candidate_modal.html",
            {"form": form, "project": project},
            status=400,
        )

    try:
        create_application(
            project=project,
            candidate=form.cleaned_data["candidate"],
            actor=request.user,
            notes=form.cleaned_data.get("notes", ""),
        )
    except ValueError as e:
        form.add_error(None, str(e))
        return render(
            request,
            "projects/partials/add_candidate_modal.html",
            {"form": form, "project": project},
            status=400,
        )

    if request.headers.get("HX-Request"):
        response = HttpResponse("")
        response["HX-Trigger"] = "applicationChanged"
        return response
    return redirect("projects:project_detail", pk=project.pk)


@level_required(1)
def application_drop(request, pk):
    """GET: 드롭 사유 모달 렌더링. POST: Application 드롭."""
    application = get_scoped_object_or_404(
        Application,
        request.user,
        pk=pk,
    )

    if request.method == "GET":
        form = ApplicationDropForm()
        return render(
            request,
            "projects/partials/drop_application_modal.html",
            {"form": form, "application": application},
        )

    # POST
    form = ApplicationDropForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/drop_application_modal.html",
            {"form": form, "application": application},
            status=400,
        )
    try:
        drop_application(
            application,
            reason=form.cleaned_data["drop_reason"],
            actor=request.user,
            note=form.cleaned_data.get("drop_note", ""),
        )
    except ValueError as e:
        form.add_error(None, str(e))
        return render(
            request,
            "projects/partials/drop_application_modal.html",
            {"form": form, "application": application},
            status=400,
        )

    if request.headers.get("HX-Request"):
        response = HttpResponse("")
        response["HX-Trigger"] = "applicationChanged"
        return response
    return redirect("projects:project_detail", pk=application.project.pk)


@level_required(1)
@require_POST
def application_restore(request, pk):
    """POST: Application 드롭 복구."""
    application = get_scoped_object_or_404(
        Application,
        request.user,
        pk=pk,
    )
    try:
        restore_application(application, actor=request.user)
    except ValueError as e:
        if request.headers.get("HX-Request"):
            return HttpResponse(str(e), status=400)
        return HttpResponseBadRequest(str(e))

    if request.headers.get("HX-Request"):
        response = render(
            request,
            "projects/partials/application_card.html",
            {"application": application},
        )
        response["HX-Trigger"] = "applicationChanged"
        return response
    return redirect("projects:project_detail", pk=application.project.pk)


@level_required(1)
@require_POST
def application_hire(request, pk):
    """POST: 입사 확정. Signal이 프로젝트 자동 종료 + 나머지 드롭."""
    application = get_scoped_object_or_404(
        Application,
        request.user,
        pk=pk,
    )
    try:
        hire_application(application, actor=request.user)
    except ValueError as e:
        if request.headers.get("HX-Request"):
            return HttpResponse(str(e), status=409)
        return HttpResponseBadRequest(str(e))

    # Hire changes entire project state -> full page redirect
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = f"/projects/{application.project.pk}/"
        return response
    return redirect("projects:project_detail", pk=application.project.pk)


@login_required
@level_required(1)
def application_skip_stage(request, pk):
    """현재 단계 건너뛰기. GET=모달, POST=stage_skipped ActionItem 생성."""
    from projects.models import (
        ActionItem,
        ActionItemStatus,
        ActionType,
        STAGE_SKIPPED_ACTION_CODE,
        STAGES_ORDER,
    )
    from django.utils import timezone

    application = get_scoped_object_or_404(
        Application,
        request.user,
        pk=pk,
    )
    current_id = application.current_stage
    if current_id in (None, "hired"):
        return HttpResponseBadRequest("건너뛸 수 있는 단계가 없습니다.")

    stages_dict = dict(STAGES_ORDER)
    current_label = stages_dict.get(current_id, "")
    # 다음 단계 찾기 (UI 표시용)
    order_keys = [s for s, _ in STAGES_ORDER]
    try:
        next_id = order_keys[order_keys.index(current_id) + 1]
    except (ValueError, IndexError):
        next_id = None
    next_label = stages_dict.get(next_id, "") if next_id else ""

    if request.method == "POST":
        reason = (request.POST.get("reason") or "").strip()
        if not reason:
            reason = "사유 미입력"
        try:
            at = ActionType.objects.get(code=STAGE_SKIPPED_ACTION_CODE)
        except ActionType.DoesNotExist:
            return HttpResponseBadRequest(
                "stage_skipped ActionType이 없습니다. update_action_labels 커맨드 실행 필요."
            )
        now = timezone.now()
        ActionItem.objects.create(
            application=application,
            action_type=at,
            title=f"{current_label} 단계 건너뛰기",
            result=current_id,  # 스킵한 stage id (current_stage 파생 시 사용)
            note=reason,
            status=ActionItemStatus.DONE,
            completed_at=now,
            scheduled_at=now,
            due_at=now,
            assigned_to=request.user,
            created_by=request.user,
        )
        # 이벤트 trigger — 상세 페이지 리로드
        response = HttpResponse("")
        response["HX-Trigger"] = "applicationChanged"
        return response

    return render(
        request,
        "projects/partials/stage_skip_modal.html",
        {
            "application": application,
            "current_stage_id": current_id,
            "current_stage_label": current_label,
            "next_stage_label": next_label,
        },
    )


@login_required
@level_required(1)
@require_POST
def application_resume_use_db(request, pk):
    """Phase B — DB에 있는 기존 이력서 사용. receive_resume 즉시 완료."""
    application = get_scoped_object_or_404(
        Application,
        request.user,
        pk=pk,
    )
    current = application.candidate.current_resume
    if not current:
        return HttpResponse(
            "이 후보자에게 DB 이력서가 없습니다. 다른 방법을 선택하세요.",
            status=400,
        )
    _create_receive_resume_action(
        application,
        request.user,
        done=True,
        note=f"DB 기존 이력서 재사용 (파일: {current.filename or current.pk})",
    )
    response = HttpResponse("")
    response["HX-Trigger"] = "applicationChanged"
    return response


@login_required
@level_required(1)
def application_resume_request_email(request, pk):
    """Phase B — 이메일로 이력서 요청. GET=폼 모달, POST=pending 액션 생성."""
    application = get_scoped_object_or_404(
        Application,
        request.user,
        pk=pk,
    )
    if request.method == "POST":
        body = (request.POST.get("body") or "").strip() or "(본문 미입력)"
        _create_receive_resume_action(
            application,
            request.user,
            done=False,
            note=f"이메일 요청 보냄\n\n{body}",
        )
        response = HttpResponse("")
        response["HX-Trigger"] = "applicationChanged"
        return response
    return render(
        request,
        "projects/partials/resume_email_request_modal.html",
        {"application": application},
    )


@login_required
@level_required(1)
def application_resume_upload(request, pk):
    """Phase B — 직접 받은 이력서 파일 업로드. GET=업로드 모달, POST=Resume+ActionItem 생성."""
    application = get_scoped_object_or_404(
        Application,
        request.user,
        pk=pk,
    )
    if request.method == "POST":
        file = request.FILES.get("resume_file")
        if not file:
            return HttpResponse("파일을 선택하세요.", status=400)
        from candidates.models import Resume

        resume = Resume.objects.create(
            candidate=application.candidate,
            filename=file.name,
            file=file,
        )
        if not application.candidate.current_resume:
            application.candidate.current_resume = resume
            application.candidate.save(update_fields=["current_resume"])
        _create_receive_resume_action(
            application,
            request.user,
            done=True,
            note=f"직접 업로드 — {file.name}",
        )
        response = HttpResponse("")
        response["HX-Trigger"] = "applicationChanged"
        return response
    return render(
        request,
        "projects/partials/resume_upload_modal.html",
        {"application": application},
    )


@level_required(1)
def application_actions_partial(request, pk):
    """GET: Application의 ActionItem 목록. R1-11/R1-12: prefetch + ordering."""
    application = get_scoped_object_or_404(
        Application,
        request.user,
        pk=pk,
    )
    actions = application.action_items.select_related(
        "action_type", "assigned_to"
    ).order_by(
        db_models.Case(
            db_models.When(status=ActionItemStatus.PENDING, then=0),
            default=1,
        ),
        "due_at",
        "created_at",
    )
    return render(
        request,
        "projects/partials/application_actions_list.html",
        {"application": application, "actions": actions},
    )
