"""Submission + draft workflow views."""
from __future__ import annotations

import json
import os
import uuid

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.decorators import level_required
from accounts.services.scope import get_scoped_object_or_404
from projects.views._helpers import _get_draft_context, _has_pending_approval
from projects.views.project import project_tab_submissions
from projects.forms import SubmissionFeedbackForm, SubmissionForm
from projects.models import (
    ActionItem,
    ActionItemStatus,
    ActionType,
    Application,
    DraftStatus,
    OutputLanguage,
    Project,
    Submission,
)

ALLOWED_AUDIO_EXTENSIONS = {".webm", ".mp4", ".m4a", ".ogg", ".wav", ".mp3"}
MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25MB (Whisper API limit)


@login_required
@level_required(1)
def submission_create(request, pk):
    """추천 서류 등록."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    if _has_pending_approval(project):
        return HttpResponse(status=403)

    if request.method == "POST":
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.project = project
            submission.consultant = request.user
            submission.save()

            # 프로젝트 status 자동 전환
            from projects.services.submission import maybe_advance_project_status

            maybe_advance_project_status(project)

            # 추천 탭 파셜을 직접 렌더링하여 반환 (자동 탭 전환)
            response = project_tab_submissions(request, pk)
            response["HX-Retarget"] = "#tab-content"
            response["HX-Reswap"] = "innerHTML"
            response["HX-Trigger"] = json.dumps(
                {
                    "tabChanged": {"activeTab": "submissions"},
                    "submissionChanged": {},
                }
            )
            return response
    else:
        form = SubmissionForm()

    # 프리필: query param으로 candidate 전달 시
    candidate_id = request.GET.get("candidate")
    if candidate_id and request.method != "POST":
        form.initial["candidate"] = candidate_id

    return render(
        request,
        "projects/partials/submission_form.html",
        {
            "form": form,
            "project": project,
            "is_edit": False,
        },
    )


@login_required
@level_required(1)
@require_http_methods(["POST"])
def submission_batch_create(request, pk):
    """선택한 여러 Application 을 한 batch_id 로 묶어 Submission 생성."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    app_ids = request.POST.getlist("application_ids")
    if not app_ids:
        return HttpResponseBadRequest("application_ids required")

    applications = (
        Application.objects.filter(
            pk__in=app_ids,
            project=project,
            dropped_at__isnull=True,
            hired_at__isnull=True,
        )
        .select_related("candidate")
        .prefetch_related("action_items__action_type")
    )

    # Stage validation — only apps ready for client submission can be batched.
    applications = [app for app in applications if app.current_stage == "client_submit"]
    if not applications:
        return HttpResponseBadRequest("No applications ready for client submission")

    submit_type = ActionType.objects.get(code="submit_to_client")
    batch_id = uuid.uuid4()

    for app in applications:
        ai = ActionItem.objects.create(
            application=app,
            action_type=submit_type,
            title="이력서 고객사 제출",
            status=ActionItemStatus.DONE,
            completed_at=timezone.now(),
            created_by=request.user,
        )
        Submission.objects.create(
            action_item=ai,
            consultant=request.user,
            batch_id=batch_id,
            submitted_at=timezone.now(),
        )

    return redirect("projects:project_detail", pk=project.pk)


@login_required
@level_required(1)
def submission_update(request, pk, sub_pk):
    """추천 서류 수정."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    submission = get_scoped_object_or_404(
        Submission, request.user, pk=sub_pk, action_item__application__project=project
    )

    if request.method == "POST":
        form = SubmissionForm(
            request.POST,
            request.FILES,
            instance=submission,
        )
        if form.is_valid():
            form.save()
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "submissionChanged"},
            )
    else:
        form = SubmissionForm(
            instance=submission,
        )

    return render(
        request,
        "projects/partials/submission_form.html",
        {
            "form": form,
            "project": project,
            "submission": submission,
            "is_edit": True,
        },
    )


@login_required
@level_required(1)
@require_http_methods(["POST"])
def submission_delete(request, pk, sub_pk):
    """추천 서류 삭제. 면접/오퍼 존재 시 차단."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    submission = get_scoped_object_or_404(
        Submission, request.user, pk=sub_pk, action_item__application__project=project
    )

    # 삭제 보호: 면접 존재 시 차단
    if submission.interviews.exists():
        return HttpResponse(
            "면접 이력이 있어 삭제할 수 없습니다.",
            status=400,
        )

    submission.delete()
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "submissionChanged"},
    )


@login_required
@level_required(1)
@require_http_methods(["POST"])
def submission_submit(request, pk, sub_pk):
    """고객사에 제출 (작성중 → 제출)."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    submission = get_scoped_object_or_404(
        Submission, request.user, pk=sub_pk, action_item__application__project=project
    )

    from projects.services.submission import InvalidTransition, submit_to_client

    try:
        submit_to_client(submission)
    except InvalidTransition as e:
        return HttpResponse(str(e), status=400)

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "submissionChanged"},
    )


@login_required
@level_required(1)
def submission_feedback(request, pk, sub_pk):
    """고객사 피드백 입력 (제출 → 통과/탈락)."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    submission = get_scoped_object_or_404(
        Submission, request.user, pk=sub_pk, action_item__application__project=project
    )

    if request.method == "POST":
        form = SubmissionFeedbackForm(request.POST)
        if form.is_valid():
            from projects.services.submission import (
                InvalidTransition,
                apply_client_feedback,
            )

            try:
                apply_client_feedback(
                    submission,
                    form.cleaned_data["result"],
                    form.cleaned_data["feedback"],
                )
            except InvalidTransition as e:
                return HttpResponse(str(e), status=400)

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "submissionChanged"},
            )
    else:
        form = SubmissionFeedbackForm()

    return render(
        request,
        "projects/partials/submission_feedback.html",
        {
            "form": form,
            "project": project,
            "submission": submission,
        },
    )


@login_required
@level_required(1)
def submission_download(request, pk, sub_pk):
    """첨부파일 다운로드. 파일 없으면 404."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    submission = get_scoped_object_or_404(
        Submission, request.user, pk=sub_pk, action_item__application__project=project
    )

    if not submission.document_file:
        from django.http import Http404

        raise Http404("첨부파일이 없습니다.")

    from django.http import FileResponse

    response = FileResponse(
        submission.document_file.open("rb"),
        as_attachment=True,
        filename=os.path.basename(submission.document_file.name),
    )
    return response


@login_required
@level_required(1)
def submission_draft(request, pk, sub_pk):
    """초안 작업 메인 화면. 현재 상태에 따라 적절한 단계 표시."""
    project, submission, draft = _get_draft_context(request, pk, sub_pk)
    return render(
        request,
        "projects/submission_draft.html",
        {
            "project": project,
            "submission": submission,
            "draft": draft,
            "candidate": submission.candidate,
        },
    )


@login_required
@level_required(1)
@require_http_methods(["POST"])
def draft_generate(request, pk, sub_pk):
    """AI 초안 생성. Gemini API 호출."""
    project, submission, draft = _get_draft_context(request, pk, sub_pk)

    if draft.status not in (DraftStatus.PENDING, DraftStatus.DRAFT_GENERATED):
        return HttpResponse("이미 초안 생성이 완료되었습니다.", status=400)

    from projects.services.draft_generator import generate_draft

    try:
        generate_draft(draft)
    except Exception as e:
        return render(
            request,
            "projects/partials/draft_error.html",
            {"error": str(e), "draft": draft},
        )

    return render(
        request,
        "projects/partials/draft_step_generated.html",
        {"draft": draft, "project": project, "submission": submission},
    )


@login_required
@level_required(1)
def draft_consultation(request, pk, sub_pk):
    """상담 내용 직접 입력."""
    project, submission, draft = _get_draft_context(request, pk, sub_pk)

    if request.method == "POST":
        draft.consultation_input = request.POST.get("consultation_input", "")
        draft.save(update_fields=["consultation_input", "updated_at"])

        # AI 상담 정리
        from projects.services.draft_consultation import summarize_consultation

        try:
            summarize_consultation(draft)
        except Exception:
            pass  # 정리 실패해도 입력은 저장됨

        from projects.services.draft_pipeline import transition_draft

        if draft.status == DraftStatus.DRAFT_GENERATED:
            transition_draft(draft, DraftStatus.CONSULTATION_ADDED)

        return render(
            request,
            "projects/partials/draft_step_consultation.html",
            {"draft": draft, "project": project, "submission": submission},
        )

    return render(
        request,
        "projects/partials/draft_step_consultation.html",
        {"draft": draft, "project": project, "submission": submission},
    )


@login_required
@level_required(1)
@require_http_methods(["POST"])
def draft_consultation_audio(request, pk, sub_pk):
    """녹음 파일 업로드 + Whisper 딕테이션."""
    project, submission, draft = _get_draft_context(request, pk, sub_pk)

    audio_file = request.FILES.get("audio_file")
    if not audio_file:
        return HttpResponse("오디오 파일이 필요합니다.", status=400)

    # 파일 검증
    ext = os.path.splitext(audio_file.name)[1].lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        return HttpResponse(
            f"지원하지 않는 오디오 형식입니다. ({', '.join(ALLOWED_AUDIO_EXTENSIONS)})",
            status=400,
        )
    if audio_file.size > MAX_AUDIO_SIZE:
        return HttpResponse("오디오 파일은 25MB 이하만 가능합니다.", status=400)
    if audio_file.size == 0:
        return HttpResponse("빈 오디오 파일입니다.", status=400)

    # 저장 + 딕테이션
    draft.consultation_audio = audio_file
    draft.save(update_fields=["consultation_audio", "updated_at"])

    from candidates.services.whisper import transcribe_audio

    try:
        transcript = transcribe_audio(audio_file)
        draft.consultation_transcript = transcript
        draft.save(update_fields=["consultation_transcript", "updated_at"])
    except RuntimeError as e:
        return render(
            request,
            "projects/partials/draft_error.html",
            {"error": str(e), "draft": draft},
        )

    # AI 상담 정리 (transcript 포함)
    from projects.services.draft_consultation import summarize_consultation

    try:
        summarize_consultation(draft)
    except Exception:
        pass  # 정리 실패해도 transcript는 저장됨

    from projects.services.draft_pipeline import transition_draft

    if draft.status == DraftStatus.DRAFT_GENERATED:
        transition_draft(draft, DraftStatus.CONSULTATION_ADDED)

    return render(
        request,
        "projects/partials/draft_step_consultation.html",
        {"draft": draft, "project": project, "submission": submission},
    )


@login_required
@level_required(1)
@require_http_methods(["POST"])
def draft_finalize(request, pk, sub_pk):
    """AI 최종 정리: 초안 + 상담 병합."""
    project, submission, draft = _get_draft_context(request, pk, sub_pk)

    allowed_statuses = {
        DraftStatus.DRAFT_GENERATED,
        DraftStatus.CONSULTATION_ADDED,
        DraftStatus.REVIEWED,  # 회귀: 재정리
    }
    if draft.status not in allowed_statuses:
        return HttpResponse("현재 상태에서는 AI 정리를 실행할 수 없습니다.", status=400)

    from projects.services.draft_finalizer import finalize_draft

    try:
        finalize_draft(draft)
    except Exception as e:
        return render(
            request,
            "projects/partials/draft_error.html",
            {"error": str(e), "draft": draft},
        )

    from projects.services.draft_pipeline import transition_draft

    transition_draft(draft, DraftStatus.FINALIZED)

    return render(
        request,
        "projects/partials/draft_step_review.html",
        {"draft": draft, "project": project, "submission": submission},
    )


@login_required
@level_required(1)
def draft_review(request, pk, sub_pk):
    """컨설턴트가 final_content_json을 직접 수정."""
    project, submission, draft = _get_draft_context(request, pk, sub_pk)

    if request.method == "POST":
        try:
            updated_content = json.loads(request.POST.get("final_content", "{}"))
        except json.JSONDecodeError:
            return HttpResponse("유효하지 않은 데이터 형식입니다.", status=400)

        draft.final_content_json = updated_content
        draft.save(update_fields=["final_content_json", "updated_at"])

        from projects.services.draft_pipeline import transition_draft

        if draft.status == DraftStatus.FINALIZED:
            transition_draft(draft, DraftStatus.REVIEWED)

        return render(
            request,
            "projects/partials/draft_step_review.html",
            {"draft": draft, "project": project, "submission": submission},
        )

    return render(
        request,
        "projects/partials/draft_step_review.html",
        {"draft": draft, "project": project, "submission": submission},
    )


@login_required
@level_required(1)
@require_http_methods(["POST"])
def draft_convert(request, pk, sub_pk):
    """제출용 Word 파일 변환 + 마스킹."""
    project, submission, draft = _get_draft_context(request, pk, sub_pk)

    allowed_statuses = {DraftStatus.REVIEWED, DraftStatus.CONVERTED}
    if draft.status not in allowed_statuses:
        return HttpResponse("검토 완료 후 변환할 수 있습니다.", status=400)

    # 마스킹/언어 설정 업데이트
    masking_str = request.POST.get("masking_config", "")
    if masking_str:
        try:
            draft.masking_config = json.loads(masking_str)
        except json.JSONDecodeError:
            pass
    output_language = request.POST.get("output_language", draft.output_language)
    if output_language in dict(OutputLanguage.choices):
        draft.output_language = output_language
    draft.save(update_fields=["masking_config", "output_language", "updated_at"])

    from projects.services.draft_converter import convert_to_word

    try:
        convert_to_word(draft)
    except Exception as e:
        return render(
            request,
            "projects/partials/draft_error.html",
            {"error": str(e), "draft": draft},
        )

    # output_file → Submission.document_file 복사
    if draft.output_file:
        submission.document_file = draft.output_file
        submission.save(update_fields=["document_file", "updated_at"])

    from projects.services.draft_pipeline import transition_draft

    if draft.status != DraftStatus.CONVERTED:
        transition_draft(draft, DraftStatus.CONVERTED)

    return render(
        request,
        "projects/partials/draft_step_converted.html",
        {"draft": draft, "project": project, "submission": submission},
    )


@login_required
@level_required(1)
def draft_preview(request, pk, sub_pk):
    """현재 단계의 데이터를 미리보기."""
    project, submission, draft = _get_draft_context(request, pk, sub_pk)

    # final_content_json이 있으면 최종, 없으면 auto_draft_json
    preview_data = draft.final_content_json or draft.auto_draft_json

    return render(
        request,
        "projects/partials/draft_preview.html",
        {
            "draft": draft,
            "project": project,
            "submission": submission,
            "preview_data": preview_data,
        },
    )
