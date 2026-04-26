from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.decorators import level_required
from accounts.services.scope import get_scoped_object_or_404
from projects.forms import ContactCompleteForm
from projects.models import (
    ActionItem,
    ActionItemStatus,
    ActionType,
    Application,
    DropReason,
    Submission,
)


@login_required
@level_required(1)
@require_http_methods(["POST"])
def stage_contact_complete(request, pk):
    """접촉 단계 완료 — 응답 기록."""
    app = get_scoped_object_or_404(Application, request.user, pk=pk)

    form = ContactCompleteForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_text())

    response = form.cleaned_data["response"]
    note = form.cleaned_data["note"]

    if response == "negative":
        app.dropped_at = timezone.now()
        app.drop_reason = DropReason.CANDIDATE_DECLINED
        app.drop_note = note
        app.save(update_fields=["dropped_at", "drop_reason", "drop_note"])
    else:
        reach_out = ActionType.objects.get(code="reach_out")
        ActionItem.objects.create(
            application=app,
            action_type=reach_out,
            title="연락 — 의사 확인",
            status=ActionItemStatus.DONE,
            completed_at=timezone.now(),
            note=f"응답: {response}. {note}".strip(),
            created_by=request.user,
        )

    return redirect("projects:project_detail", pk=app.project.pk)


@login_required
@level_required(1)
@require_http_methods(["POST"])
def stage_pre_meeting_schedule(request, pk):
    """사전 미팅 일정 확정."""
    from projects.forms import PreMeetingScheduleForm
    from projects.models import ActionItem, ActionItemStatus, ActionType

    app = get_scoped_object_or_404(Application, request.user, pk=pk)

    form = PreMeetingScheduleForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_text())

    schedule_type = ActionType.objects.get(code="schedule_pre_meet")
    ActionItem.objects.create(
        application=app,
        action_type=schedule_type,
        title=f"사전 미팅 일정 ({form.cleaned_data['channel']})",
        status=ActionItemStatus.DONE,
        scheduled_at=form.cleaned_data["scheduled_at"],
        channel=form.cleaned_data["channel"],
        note=form.cleaned_data.get("location", ""),
        completed_at=timezone.now(),
        created_by=request.user,
    )
    return redirect("projects:project_detail", pk=app.project.pk)


@login_required
@level_required(1)
@require_http_methods(["POST"])
def stage_pre_meeting_record(request, pk):
    """사전 미팅 결과 기록 — pre_meeting ActionItem DONE + (선택) MeetingRecord 오디오."""
    from projects.forms import PreMeetingRecordForm
    from projects.models import (
        ActionItem,
        ActionItemStatus,
        ActionType,
        MeetingRecord,
    )

    app = get_scoped_object_or_404(Application, request.user, pk=pk)

    form = PreMeetingRecordForm(request.POST, request.FILES)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_text())

    pre_meeting_type = ActionType.objects.get(code="pre_meeting")
    ai = ActionItem.objects.create(
        application=app,
        action_type=pre_meeting_type,
        title="사전 미팅 진행",
        status=ActionItemStatus.DONE,
        result=form.cleaned_data["summary"],
        completed_at=timezone.now(),
        created_by=request.user,
    )
    audio = form.cleaned_data.get("audio")
    if audio:
        MeetingRecord.objects.create(
            action_item=ai,
            audio_file=audio,
            status=MeetingRecord.Status.UPLOADED,
            created_by=request.user,
        )
    return redirect("projects:project_detail", pk=app.project.pk)


@login_required
@level_required(1)
@require_http_methods(["POST"])
def stage_prep_submission_confirm(request, pk):
    """이력서 작성(제출용) 단계 — 컨설턴트 컨펌."""
    app = get_scoped_object_or_404(Application, request.user, pk=pk)

    at = ActionType.objects.get(code="submit_to_pm")
    ActionItem.objects.create(
        application=app,
        action_type=at,
        title="제출용 이력서 컨펌",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
        note="컨설턴트 컨펌 완료 (자동 생성 템플릿 미구현 — 수동 컨펌)",
        created_by=request.user,
    )
    return redirect("projects:project_detail", pk=app.project.pk)


@login_required
@level_required(1)
@require_http_methods(["POST"])
def stage_client_submit_single(request, pk):
    """이력서 제출 단계 — 이 후보자만 단독 제출."""
    app = get_scoped_object_or_404(Application, request.user, pk=pk)

    at = ActionType.objects.get(code="submit_to_client")
    ai = ActionItem.objects.create(
        application=app,
        action_type=at,
        title="이력서 고객사 제출 (개별)",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
        created_by=request.user,
    )
    Submission.objects.create(
        action_item=ai,
        consultant=request.user,
        batch_id=None,
        submitted_at=timezone.now(),
    )
    return redirect("projects:project_detail", pk=app.project.pk)


@login_required
@level_required(1)
@require_http_methods(["POST"])
def stage_interview_complete(request, pk):
    """면접 단계 완료 — 결과 + (선택) After Interview Review."""
    from projects.models import ActionItem, ActionItemStatus, ActionType, DropReason

    app = get_scoped_object_or_404(Application, request.user, pk=pk)

    result = request.POST.get("result", "")
    review = request.POST.get("review", "").strip()

    if result not in ("passed", "failed", "pending"):
        return HttpResponseBadRequest("invalid result")

    if result == "failed":
        app.dropped_at = timezone.now()
        app.drop_reason = DropReason.CLIENT_REJECTED
        app.drop_note = review
        app.save(update_fields=["dropped_at", "drop_reason", "drop_note"])
        return redirect("projects:project_detail", pk=app.project.pk)

    at = ActionType.objects.get(code="interview_round")
    ActionItem.objects.create(
        application=app,
        action_type=at,
        title="면접 결과 수령",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
        result=review,
        note=f"결과: {result}",
        created_by=request.user,
    )
    return redirect("projects:project_detail", pk=app.project.pk)
