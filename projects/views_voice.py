"""P14: Voice agent endpoint views."""

from __future__ import annotations

import json
import logging
import threading

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import level_required
from accounts.services.scope import scope_work_qs
from candidates.models import Candidate
from projects.models import MeetingRecord, Project
from projects.services.voice.action_executor import confirm_action, preview_action
from projects.services.voice.context_resolver import resolve_context
from projects.services.voice.conversation import ConversationManager
from projects.services.voice.entity_resolver import (
    resolve_candidate,
    resolve_candidate_list,
)
from projects.services.voice.intent_parser import REQUIRED_ENTITIES, parse_intent
from projects.services.voice.meeting_analyzer import (
    analyze_meeting,
    apply_meeting_insights,
    validate_meeting_file,
)
from projects.services.voice.transcriber import TranscribeMode, transcribe

logger = logging.getLogger(__name__)


@login_required
@level_required(1)
@require_POST
def voice_transcribe(request):
    """POST /voice/transcribe/ — audio file -> text."""
    audio = request.FILES.get("audio")
    if not audio:
        return JsonResponse({"error": "음성 파일이 필요합니다."}, status=400)

    mode_str = request.POST.get("mode", "command")
    mode = TranscribeMode.MEETING if mode_str == "meeting" else TranscribeMode.COMMAND

    try:
        text = transcribe(audio, mode=mode)
    except RuntimeError as e:
        return JsonResponse({"error": str(e)}, status=500)

    mgr = ConversationManager(request.session)
    mgr.touch()
    if text:
        mgr.add_turn(role="user", text=text)

    return JsonResponse({"text": text, "empty": not text})


@login_required
@level_required(1)
@require_POST
def voice_intent(request):
    """POST /voice/intent/ — text -> intent + entities."""
    body = (
        json.loads(request.body)
        if request.content_type == "application/json"
        else request.POST
    )
    text = body.get("text", "")
    context_hint = (
        json.loads(body.get("context", "{}"))
        if isinstance(body.get("context"), str)
        else body.get("context", {})
    )

    ctx = resolve_context(user=request.user, context_hint=context_hint)

    # Amendment A4: multi-turn continuation
    mgr = ConversationManager(request.session)
    mgr.touch()
    conv = mgr.get_or_create()

    if conv["pending_intent"] and conv["missing_fields"]:
        # Follow-up answer — re-parse with context of pending intent
        result = parse_intent(
            text=text,
            context={
                **ctx,
                "pending_intent": conv["pending_intent"],
                "missing_fields": conv["missing_fields"],
            },
        )
        # Merge new entities into collected
        for k, v in result.entities.items():
            if v:
                conv["collected_entities"][k] = v
        # Recalculate missing
        required = REQUIRED_ENTITIES.get(conv["pending_intent"], [])
        still_missing = [f for f in required if not conv["collected_entities"].get(f)]
        conv["missing_fields"] = still_missing
        request.session.modified = True

        return JsonResponse(
            {
                "intent": conv["pending_intent"],
                "entities": conv["collected_entities"],
                "confidence": result.confidence,
                "missing_fields": still_missing,
            }
        )

    result = parse_intent(text=text, context=ctx)

    project = None
    if ctx["project_id"]:
        project = scope_work_qs(
            Project.objects.filter(pk=ctx["project_id"]), request.user
        ).first()

    # Entity resolution: candidate_name (singular)
    if result.entities.get("candidate_name"):
        resolution = resolve_candidate(
            name=result.entities["candidate_name"],
            project=project,
        )
        result.entities["_candidate_resolution"] = {
            "status": resolution.status,
            "candidate_id": str(resolution.candidate_id)
            if resolution.candidate_id
            else None,
            "candidates": resolution.candidates,
        }
        if resolution.candidate_id:
            result.entities["candidate_id"] = str(resolution.candidate_id)

    # Amendment A3: candidate_names (list) for contact_reserve
    if result.entities.get("candidate_names"):
        list_result = resolve_candidate_list(
            names=result.entities["candidate_names"],
            project=project,
        )
        result.entities["candidate_ids"] = list_result["resolved_ids"]
        result.entities["_candidate_list_resolution"] = list_result

    mgr.set_pending(
        intent=result.intent, entities=result.entities, missing=result.missing_fields
    )

    return JsonResponse(
        {
            "intent": result.intent,
            "entities": result.entities,
            "confidence": result.confidence,
            "missing_fields": result.missing_fields,
        }
    )


@login_required
@level_required(1)
@require_POST
def voice_preview(request):
    """POST /voice/preview/ — intent + entities -> preview (no DB change)."""
    body = (
        json.loads(request.body)
        if request.content_type == "application/json"
        else request.POST
    )
    intent = body.get("intent", "")
    entities = (
        json.loads(body.get("entities", "{}"))
        if isinstance(body.get("entities"), str)
        else body.get("entities", {})
    )
    project_id = body.get("project_id")

    project = None
    if project_id:
        project = scope_work_qs(
            Project.objects.filter(pk=project_id), request.user
        ).first()

    result = preview_action(
        intent=intent,
        entities=entities,
        project=project,
        user=request.user,
    )

    mgr = ConversationManager(request.session)
    token = mgr.generate_preview_token()
    result["preview_token"] = token

    return JsonResponse(result)


@login_required
@level_required(1)
@require_POST
def voice_confirm(request):
    """POST /voice/confirm/ — confirm with idempotent token."""
    body = (
        json.loads(request.body)
        if request.content_type == "application/json"
        else request.POST
    )
    token = body.get("preview_token", "")
    intent = body.get("intent", "")
    entities = (
        json.loads(body.get("entities", "{}"))
        if isinstance(body.get("entities"), str)
        else body.get("entities", {})
    )
    project_id = body.get("project_id")

    mgr = ConversationManager(request.session)
    if not mgr.consume_preview_token(token):
        return JsonResponse({"error": "이미 처리된 요청입니다."}, status=409)

    project = None
    if project_id:
        project = scope_work_qs(
            Project.objects.filter(pk=project_id), request.user
        ).first()

    result = confirm_action(
        intent=intent,
        entities=entities,
        project=project,
        user=request.user,
    )

    if result.get("ok"):
        mgr.add_turn(role="assistant", text=result.get("summary", "완료되었습니다."))
        conv = mgr.get_or_create()
        conv["pending_intent"] = None
        conv["collected_entities"] = {}
        conv["missing_fields"] = []
        request.session.modified = True

    return JsonResponse(result)


@login_required
@level_required(1)
@require_GET
def voice_context(request):
    """GET /voice/context/ — return verified context."""
    context_hint = {
        "page": request.GET.get("page", "unknown"),
        "project_id": request.GET.get("project_id", ""),
        "tab": request.GET.get("tab", ""),
    }
    ctx = resolve_context(user=request.user, context_hint=context_hint)
    if ctx.get("project_id"):
        ctx["project_id"] = str(ctx["project_id"])
    return JsonResponse(ctx)


@login_required
@level_required(1)
@require_GET
def voice_history(request):
    """GET /voice/history/ — return conversation turns."""
    mgr = ConversationManager(request.session)
    conv = mgr.get_or_create()
    return JsonResponse(
        {
            "id": conv["id"],
            "turns": conv["turns"],
            "pending_intent": conv["pending_intent"],
            "missing_fields": conv["missing_fields"],
        }
    )


@login_required
@level_required(1)
@require_POST
def voice_reset(request):
    """POST /voice/reset/ — clear conversation state. (Amendment A4)"""
    mgr = ConversationManager(request.session)
    mgr.reset()
    return JsonResponse({"ok": True})


@login_required
@level_required(1)
def voice_meeting_upload(request):
    """POST /voice/meeting-upload/ — upload meeting recording.
    GET /voice/meeting-upload/ — return upload form HTML (Amendment A10)."""
    if request.method == "GET":
        # Amendment A10: return meeting upload form as partial HTML
        from django.template.loader import render_to_string

        projects = scope_work_qs(Project.objects.all(), request.user).order_by(
            "-created_at"
        )[:20]
        html = render_to_string(
            "projects/partials/meeting_upload.html",
            {
                "projects": projects,
            },
            request=request,
        )
        return JsonResponse({"html": html})

    # POST: handle file upload
    audio = request.FILES.get("audio")
    if not audio:
        return JsonResponse({"error": "파일이 필요합니다."}, status=400)

    errors = validate_meeting_file(audio)
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    project_id = request.POST.get("project_id")
    candidate_id = request.POST.get("candidate_id")

    if not project_id or not candidate_id:
        return JsonResponse({"error": "프로젝트와 후보자를 선택해주세요."}, status=400)

    project = scope_work_qs(Project.objects.filter(pk=project_id), request.user).first()
    if not project:
        return JsonResponse({"error": "프로젝트를 찾을 수 없습니다."}, status=404)

    # Amendment A8: Validate candidate exists
    try:
        Candidate.objects.get(pk=candidate_id)
    except Candidate.DoesNotExist:
        return JsonResponse({"error": "후보자를 찾을 수 없습니다."}, status=404)

    record = MeetingRecord.objects.create(
        project=project,
        candidate_id=candidate_id,
        audio_file=audio,
        created_by=request.user,
    )

    # Amendment A8: Start async processing
    def _run_analysis(record_id):
        try:
            analyze_meeting(record_id)
        except Exception:
            logger.exception("Async meeting analysis failed for %s", record_id)

    thread = threading.Thread(target=_run_analysis, args=(record.pk,), daemon=True)
    thread.start()

    return JsonResponse(
        {
            "ok": True,
            "meeting_id": str(record.pk),
            "status": record.status,
            "message": "업로드 완료. 분석을 시작합니다.",
        }
    )


@login_required
@level_required(1)
@require_GET
def voice_meeting_status(request, pk):
    """GET /voice/meeting-status/<uuid>/ — poll status."""
    try:
        record = MeetingRecord.objects.get(pk=pk)
    except MeetingRecord.DoesNotExist:
        return JsonResponse({"error": "미팅 녹음을 찾을 수 없습니다."}, status=404)

    data = {
        "meeting_id": str(record.pk),
        "status": record.status,
        "error_message": record.error_message,
    }
    if record.status == MeetingRecord.Status.READY:
        data["analysis"] = record.analysis_json
        data["transcript_preview"] = record.transcript[:500]
    elif record.status == MeetingRecord.Status.APPLIED:
        data["analysis"] = record.analysis_json
        data["applied_at"] = (
            record.applied_at.isoformat() if record.applied_at else None
        )

    return JsonResponse(data)


@login_required
@level_required(1)
@require_POST
def voice_meeting_apply(request):
    """POST /voice/meeting-apply/ — apply selected fields."""
    body = (
        json.loads(request.body)
        if request.content_type == "application/json"
        else request.POST
    )
    meeting_id = body.get("meeting_id")
    selected_fields = body.get("selected_fields", [])
    if isinstance(selected_fields, str):
        selected_fields = json.loads(selected_fields)
    edited = body.get("edited_json")
    if isinstance(edited, str):
        edited = json.loads(edited)

    try:
        record = MeetingRecord.objects.get(pk=meeting_id)
    except MeetingRecord.DoesNotExist:
        return JsonResponse({"error": "미팅 녹음을 찾을 수 없습니다."}, status=404)

    if record.status != MeetingRecord.Status.READY:
        return JsonResponse(
            {"error": "분석이 완료된 녹음만 반영할 수 있습니다."}, status=400
        )

    if edited:
        record.edited_json = edited
        record.save(update_fields=["edited_json"])

    apply_meeting_insights(
        record=record, selected_fields=selected_fields, user=request.user
    )

    return JsonResponse({"ok": True, "message": "선택한 항목이 반영되었습니다."})
