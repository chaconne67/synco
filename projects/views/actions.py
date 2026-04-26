from __future__ import annotations

from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import level_required
from accounts.services.scope import get_scoped_object_or_404
from projects.forms import (
    ActionItemCompleteForm,
    ActionItemCreateForm,
    ActionItemRescheduleForm,
    ActionItemSkipForm,
)
from projects.models import ActionItem, ActionItemStatus, ActionType, Application
from projects.services.action_lifecycle import (
    complete_action as complete_action_item,
    create_action as create_action_item,
    propose_next as propose_next_actions,
    reschedule_action as reschedule_action_item,
    skip_action as skip_action_item,
)


@level_required(1)
def action_create(request, pk):
    """GET: 액션 생성 모달. POST: ActionItem 생성."""
    application = get_scoped_object_or_404(
        Application,
        request.user,
        pk=pk,
    )
    active_types = ActionType.objects.filter(is_active=True).order_by("sort_order")

    if request.method == "GET":
        # Phase A: preset 파라미터로 특정 ActionType 사전 선택 (단계 gate 시작 버튼에서 사용)
        preset_code = request.GET.get("preset")
        initial = {}
        preset_at = None
        if preset_code:
            preset_at = active_types.filter(code=preset_code).first()
            if preset_at:
                initial["action_type_id"] = str(preset_at.pk)
        form = ActionItemCreateForm(initial=initial)
        return render(
            request,
            "projects/partials/action_create_modal.html",
            {
                "form": form,
                "application": application,
                "action_types": active_types,
                "preset_action_type": preset_at,
            },
        )

    # POST
    form = ActionItemCreateForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/action_create_modal.html",
            {"form": form, "application": application, "action_types": active_types},
            status=400,
        )

    action_type = get_object_or_404(
        ActionType, pk=form.cleaned_data["action_type_id"], is_active=True
    )
    try:
        create_action_item(
            application,
            action_type,
            actor=request.user,
            title=form.cleaned_data.get("title", ""),
            channel=form.cleaned_data.get("channel", ""),
            scheduled_at=form.cleaned_data.get("scheduled_at"),
            due_at=form.cleaned_data.get("due_at"),
            note=form.cleaned_data.get("note", ""),
        )
    except ValueError as e:
        form.add_error(None, str(e))
        return render(
            request,
            "projects/partials/action_create_modal.html",
            {"form": form, "application": application, "action_types": active_types},
            status=400,
        )

    if request.headers.get("HX-Request"):
        # 빈 200으로 반환해 #modal-container innerHTML 이 비워지며 모달이 닫힌다.
        # (htmx 2.x 는 204 응답 시 swap 을 수행하지 않아 모달이 남아있다.)
        response = HttpResponse("")
        response["HX-Trigger"] = "actionChanged"
        return response
    return redirect("projects:project_detail", pk=application.project.pk)


@level_required(1)
def action_complete(request, pk):
    """GET: 완료 모달 렌더링. POST: ActionItem 완료 + 후속 제안."""
    action = get_scoped_object_or_404(
        ActionItem,
        request.user,
        pk=pk,
    )

    if request.method == "GET":
        form = ActionItemCompleteForm()
        suggestions = propose_next_actions(action) if action.status == "pending" else []
        return render(
            request,
            "projects/partials/action_complete_modal.html",
            {"form": form, "action": action, "suggestions": suggestions},
        )

    # POST
    form = ActionItemCompleteForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/action_complete_modal.html",
            {"form": form, "action": action},
            status=400,
        )

    try:
        complete_action_item(
            action,
            actor=request.user,
            result=form.cleaned_data.get("result", ""),
            note=form.cleaned_data.get("note", ""),
        )
    except ValueError as e:
        form.add_error(None, str(e))
        return render(
            request,
            "projects/partials/action_complete_modal.html",
            {"form": form, "action": action},
            status=400,
        )

    suggestions = propose_next_actions(action)
    if suggestions:
        response = render(
            request,
            "projects/partials/action_propose_next_modal.html",
            {"completed_action": action, "suggestions": suggestions},
        )
        response["HX-Trigger"] = "actionChanged"
        return response

    if request.headers.get("HX-Request"):
        response = HttpResponse("")
        response["HX-Trigger"] = "actionChanged"
        return response
    return redirect("projects:project_detail", pk=action.application.project.pk)


@level_required(1)
def action_skip(request, pk):
    """GET: 건너뛰기 사유 모달. POST: ActionItem 건너뛰기."""
    action = get_scoped_object_or_404(
        ActionItem,
        request.user,
        pk=pk,
    )

    if request.method == "GET":
        form = ActionItemSkipForm()
        return render(
            request,
            "projects/partials/action_skip_modal.html",
            {"form": form, "action": action},
        )

    # POST
    form = ActionItemSkipForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/action_skip_modal.html",
            {"form": form, "action": action},
            status=400,
        )

    try:
        skip_action_item(
            action, actor=request.user, note=form.cleaned_data.get("note", "")
        )
    except ValueError as e:
        form.add_error(None, str(e))
        return render(
            request,
            "projects/partials/action_skip_modal.html",
            {"form": form, "action": action},
            status=400,
        )

    if request.headers.get("HX-Request"):
        response = HttpResponse("")
        response["HX-Trigger"] = "actionChanged"
        return response
    return redirect("projects:project_detail", pk=action.application.project.pk)


@level_required(1)
def action_reschedule(request, pk):
    """GET: 일정 변경 모달. POST: ActionItem 일정 변경."""
    action = get_scoped_object_or_404(
        ActionItem,
        request.user,
        pk=pk,
    )

    if request.method == "GET":
        form = ActionItemRescheduleForm()
        return render(
            request,
            "projects/partials/action_reschedule_modal.html",
            {"form": form, "action": action},
        )

    # POST
    form = ActionItemRescheduleForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "projects/partials/action_reschedule_modal.html",
            {"form": form, "action": action},
            status=400,
        )

    try:
        reschedule_action_item(
            action,
            actor=request.user,
            new_due_at=form.cleaned_data.get("new_due_at"),
            new_scheduled_at=form.cleaned_data.get("new_scheduled_at"),
        )
    except ValueError as e:
        form.add_error(None, str(e))
        return render(
            request,
            "projects/partials/action_reschedule_modal.html",
            {"form": form, "action": action},
            status=400,
        )

    if request.headers.get("HX-Request"):
        response = HttpResponse("")
        response["HX-Trigger"] = "actionChanged"
        return response
    return redirect("projects:project_detail", pk=action.application.project.pk)


@level_required(1)
@require_POST
def action_propose_next(request, pk):
    """POST: 완료된 액션 다음에 컨설턴트가 선택한 후속 액션들을 생성.
    선택된 type IDs를 propose_next() 결과와 교차검증.
    """
    action = get_scoped_object_or_404(
        ActionItem,
        request.user,
        pk=pk,
    )

    # Guard: parent action must be completed
    if action.status != ActionItemStatus.DONE:
        if request.headers.get("HX-Request"):
            return HttpResponse("완료된 액션에서만 후속 생성이 가능합니다.", status=400)
        return HttpResponseBadRequest("완료된 액션에서만 후속 생성이 가능합니다.")

    selected_ids = request.POST.getlist("next_action_type_ids")
    if not selected_ids:
        if request.headers.get("HX-Request"):
            response = HttpResponse("")
            response["HX-Trigger"] = "actionChanged"
            return response
        return redirect("projects:project_detail", pk=action.application.project.pk)

    # Validate selected IDs against allowed suggestions
    allowed_types = propose_next_actions(action)
    allowed_ids = {str(at.pk) for at in allowed_types}
    invalid_ids = set(selected_ids) - allowed_ids
    if invalid_ids:
        if request.headers.get("HX-Request"):
            return HttpResponse("선택한 액션 유형이 허용 목록에 없습니다.", status=400)
        return HttpResponseBadRequest("선택한 액션 유형이 허용 목록에 없습니다.")

    # Atomic batch creation
    from django.db import transaction

    with transaction.atomic():
        for type_id in selected_ids:
            at = ActionType.objects.get(pk=type_id, is_active=True)
            create_action_item(
                action.application,
                at,
                actor=request.user,
                parent_action=action,
            )

    if request.headers.get("HX-Request"):
        # 빈 응답으로 modal-container 비우면서 actionChanged 트리거 → 본문 리프레시
        response = HttpResponse("")
        response["HX-Trigger"] = "actionChanged"
        return response
    return redirect("projects:project_detail", pk=action.application.project.pk)
