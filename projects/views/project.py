"""Project lifecycle CRUD + tab views."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db import models as db_models
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.decorators import level_required
from accounts.services.scope import get_scoped_object_or_404
from clients.models import Client
from projects.views._helpers import (
    _build_overview_context,
    _build_tab_context,
    _filter_params_string,
)
from projects.forms import ProjectCloseForm, ProjectForm
from projects.models import (
    ActionItem,
    ActionItemStatus,
    Application,
    Interview,
    Project,
    ProjectApproval,
    ProjectPhase,
    ProjectStatus,
    ResumeUpload,
    Submission,
)

@login_required
@level_required(1)
def project_list(request):
    """List projects as 2-phase kanban (searching / screening / closed)."""
    from projects.services.dashboard import get_project_kanban_cards

    # Role-based filtering (existing pattern preserved)
    is_owner = request.user.is_superuser or request.user.level >= 2

    # Filter query parameters (Owner만 consultant 필터 허용. Consultant는 본인 배정만 강제)
    consultant_filter = (
        request.GET.get("consultant") if is_owner else str(request.user.id)
    )
    client_filter = request.GET.get("client") or None
    search_filter = request.GET.get("q") or None
    phase_filter = request.GET.get("phase")  # legacy, 사용 안 함

    # 컬럼별 정렬 방향 (기본: open=asc 오래된 것 상단, closed=desc 최근 먼저)
    sort_searching = request.GET.get("sort_searching", "asc")
    sort_screening = request.GET.get("sort_screening", "asc")
    sort_closed = request.GET.get("sort_closed", "desc")

    cards = get_project_kanban_cards(
        consultant_id=consultant_filter or None,
        client_id=client_filter,
        search=search_filter,
        sort_searching=sort_searching,
        sort_screening=sort_screening,
        sort_closed=sort_closed,
    )

    # 정렬 토글 URL 계산 (현재 방향 반대로 세팅)
    def _flip(column, current):
        params = request.GET.copy()
        params[f"sort_{column}"] = "desc" if current == "asc" else "asc"
        return f"?{params.urlencode()}"

    sort_directions = {
        "searching": sort_searching,
        "screening": sort_screening,
        "closed": sort_closed,
    }
    sort_toggle_urls = {
        col: _flip(col, direction) for col, direction in sort_directions.items()
    }

    # 상단 헤더 요약 — 진행 중 · 이달 마감
    now = timezone.now()
    active_count = len(cards[ProjectPhase.SEARCHING]) + len(
        cards[ProjectPhase.SCREENING]
    )
    this_month_deadline_count = Project.objects.filter(
        status=ProjectStatus.OPEN,
        deadline__year=now.year,
        deadline__month=now.month,
    ).count()

    # Owner 는 필터 바에서 컨설턴트 선택 가능.
    from accounts.models import User as _User

    if is_owner:
        org_consultants = list(_User.objects.filter(level__gte=1).order_by("username"))
    else:
        org_consultants = []

    context = {
        "kanban": cards,
        "phase_filter": phase_filter,
        "consultant_filter": consultant_filter,
        "client_filter": client_filter,
        "search_filter": search_filter,
        "sort_directions": sort_directions,
        "sort_toggle_urls": sort_toggle_urls,
        "is_owner": is_owner,
        "clients": Client.objects.all(),
        "org_consultants": org_consultants,
        "scope": request.GET.get("scope", "mine"),
        "view_type": "board",
        "status_choices": ProjectStatus.choices,
        "filter_params": _filter_params_string(request),
        "active_count": active_count,
        "this_month_deadline_count": this_month_deadline_count,
    }

    # HTMX tab switch -> partial only
    if request.headers.get("HX-Request") and request.GET.get("tab_switch"):
        return render(request, "projects/partials/view_board.html", context)

    context["view_template"] = "projects/partials/view_board.html"
    return render(request, "projects/project_list.html", context)

@login_required
@level_required(1)
@require_http_methods(["POST"])
def project_check_collision(request):
    """HTMX endpoint: check for collision when client + title are provided."""
    client_id = request.POST.get("client_id")
    title = request.POST.get("title", "").strip()

    if not client_id or not title:
        return HttpResponse("")

    from projects.services.collision import detect_collisions

    collisions = detect_collisions(client_id, title)

    high_collisions = [c for c in collisions if c["conflict_type"] == "높은중복"]
    medium_collisions = [c for c in collisions if c["conflict_type"] == "참고정보"]

    return render(
        request,
        "projects/partials/collision_warning.html",
        {
            "high_collisions": high_collisions,
            "medium_collisions": medium_collisions,
            "has_blocking_collision": len(high_collisions) > 0,
        },
    )

@login_required
@level_required(1)
def project_create(request):
    """Create a new project. GET=form, POST=save with collision detection."""
    if request.method == "POST":
        form = ProjectForm(request.POST, request.FILES)
        if form.is_valid():
            from django.contrib import messages as django_messages
            from django.db import transaction

            from accounts.models import User as _User
            from projects.services.collision import detect_collisions

            client_id = form.cleaned_data["client"].pk
            title = form.cleaned_data["title"]
            collisions = detect_collisions(client_id, title)

            high_collisions = [
                c for c in collisions if c["conflict_type"] == "높은중복"
            ]

            with transaction.atomic():
                project = form.save(commit=False)
                project.created_by = request.user

                if high_collisions:
                    # Collision detected -> create with OPEN + approval record
                    project.save()
                    form.save_m2m()
                    if not project.assigned_consultants.exists():
                        project.assigned_consultants.add(request.user)

                    top_collision = high_collisions[0]
                    approval = ProjectApproval.objects.create(
                        project=project,
                        requested_by=request.user,
                        conflict_project=top_collision["project"],
                        conflict_score=top_collision["score"],
                        conflict_type=top_collision["conflict_type"],
                        message=request.POST.get("approval_message", ""),
                    )

                    # A1: Send Telegram approval notification to level-2 users
                    from projects.models import Notification
                    from projects.services.notification import send_notification
                    from projects.telegram.formatters import format_approval_request
                    from projects.telegram.keyboards import build_approval_keyboard

                    owners = _User.objects.filter(level__gte=2)

                    for owner in owners:
                        notif = Notification.objects.create(
                            recipient=owner,
                            type=Notification.Type.APPROVAL_REQUEST,
                            title=f"프로젝트 승인 요청: {project.title}",
                            body=(
                                f"{request.user.get_full_name() or request.user.username}"
                                f" → {project.title}"
                            ),
                            callback_data={
                                "action": "approval",
                                "approval_id": str(approval.pk),
                            },
                        )
                        text = format_approval_request(
                            requester_name=(
                                request.user.get_full_name() or request.user.username
                            ),
                            project_title=project.title,
                            conflict_info=(
                                f"{top_collision['project'].title}"
                                f" ({top_collision['project'].get_status_display()})"
                            ),
                            message=request.POST.get("approval_message", ""),
                        )
                        short_id = str(notif.pk).replace("-", "")[:8]
                        send_notification(
                            notif,
                            text=text,
                            reply_markup=build_approval_keyboard(short_id),
                        )

                    django_messages.success(
                        request,
                        f"'{project.title}' 프로젝트의 승인 요청이 제출되었습니다. "
                        "관리자 승인 후 활성화됩니다.",
                    )
                    return redirect("projects:project_list")
                else:
                    # No blocking collision -> normal create
                    project.save()
                    form.save_m2m()
                    if not project.assigned_consultants.exists():
                        project.assigned_consultants.add(request.user)
                    return redirect("projects:project_detail", pk=project.pk)
    else:
        form = ProjectForm()

    return render(
        request,
        "projects/project_form.html",
        {"form": form, "is_edit": False},
    )

@login_required
@level_required(1)
def project_detail(request, pk):
    """Project detail — Application-based view."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    applications = (
        Application.objects.filter(project=project)
        .select_related("candidate")
        .prefetch_related("action_items__action_type")
        .order_by(
            db_models.Case(
                db_models.When(dropped_at__isnull=True, hired_at__isnull=True, then=0),
                db_models.When(hired_at__isnull=False, then=1),
                default=2,
            ),
            "-created_at",
        )
    )

    # Phase C Task 7: 배치 제출 대기 후보자 (current_stage == "client_submit")
    pending_for_submission = [
        app for app in applications if app.current_stage == "client_submit"
    ]

    return render(
        request,
        "projects/project_detail.html",
        {
            "project": project,
            "applications": applications,
            "pending_for_submission": pending_for_submission,
        },
    )

@login_required
@level_required(1)
def project_applications_partial(request, pk):
    """HTMX partial: application list for a project. R1-11: explicit prefetch."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    applications = (
        Application.objects.filter(project=project)
        .select_related("candidate")
        .prefetch_related("action_items__action_type")
        .order_by(
            db_models.Case(
                db_models.When(dropped_at__isnull=True, hired_at__isnull=True, then=0),
                db_models.When(hired_at__isnull=False, then=1),
                default=2,
            ),
            "-created_at",
        )
    )

    return render(
        request,
        "projects/partials/project_applications_list.html",
        {
            "project": project,
            "applications": applications,
        },
    )

@login_required
@level_required(1)
def project_timeline_partial(request, pk):
    """HTMX partial: action timeline for a project."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    actions = (
        ActionItem.objects.filter(application__project=project)
        .select_related("application__candidate", "action_type", "assigned_to")
        .order_by("-created_at")[:100]
    )
    return render(
        request,
        "projects/partials/project_timeline.html",
        {"project": project, "actions": actions},
    )

@login_required
@level_required(1)
def project_update(request, pk):
    """Update an existing project."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    # Block edit if pending approval exists
    has_pending_approval = ProjectApproval.objects.filter(
        project=project, status=ProjectApproval.Status.PENDING
    ).exists()
    if has_pending_approval:
        return HttpResponse(status=403)

    if request.method == "POST":
        form = ProjectForm(request.POST, request.FILES, instance=project)
        if form.is_valid():
            form.save()
            return redirect("projects:project_detail", pk=project.pk)
    else:
        form = ProjectForm(instance=project)

    return render(
        request,
        "projects/project_form.html",
        {"form": form, "project": project, "is_edit": True},
    )

@login_required
@level_required(2)
def project_delete(request, pk):
    """Delete a project. Block if applications or submissions exist."""
    if request.method != "POST":
        return HttpResponse(status=405)

    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    # Block delete if pending approval exists
    has_pending_approval = ProjectApproval.objects.filter(
        project=project, status=ProjectApproval.Status.PENDING
    ).exists()
    if has_pending_approval:
        return HttpResponse(status=403)

    # Check for related applications or submissions
    has_applications = project.applications.exists()
    has_submissions = project.submissions.exists()

    if has_applications or has_submissions:
        tab_counts, tab_latest = _build_tab_context(project)
        return render(
            request,
            "projects/project_detail.html",
            {
                "project": project,
                "tab_counts": tab_counts,
                "tab_latest": tab_latest,
                "active_tab": "overview",
                "error_message": "지원 또는 제출 이력이 있어 삭제할 수 없습니다.",
            },
        )

    project.delete()
    return redirect("projects:project_list")


# ---------------------------------------------------------------------------
# Phase 3a: Project close / reopen
# ---------------------------------------------------------------------------

@login_required
@level_required(1)
def project_close(request, pk):
    """GET: render close modal form. POST: close the project."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    # Permission: owner or assigned consultant
    is_owner = request.user.is_superuser or request.user.level >= 2
    is_assigned = project.assigned_consultants.filter(pk=request.user.pk).exists()
    if not (is_owner or is_assigned):
        return HttpResponseForbidden("권한이 없습니다.")

    # R1-03: GET handler for modal form
    if request.method == "GET":
        form = ProjectCloseForm()
        active_count = Application.objects.filter(
            project=project, dropped_at__isnull=True, hired_at__isnull=True
        ).count()
        return render(
            request,
            "projects/partials/project_close_modal.html",
            {"form": form, "project": project, "active_count": active_count},
        )

    # POST
    form = ProjectCloseForm(request.POST)
    if not form.is_valid():
        active_count = Application.objects.filter(
            project=project, dropped_at__isnull=True, hired_at__isnull=True
        ).count()
        return render(
            request,
            "projects/partials/project_close_modal.html",
            {"form": form, "project": project, "active_count": active_count},
        )

    # Set status and closed_at together (CHECK constraint: open implies no closed_at)
    project.closed_at = timezone.now()
    project.status = ProjectStatus.CLOSED
    project.result = form.cleaned_data["result"]
    project.note = form.cleaned_data["note"]
    project.save(update_fields=["closed_at", "status", "result", "note", "updated_at"])

    # Cancel all pending ActionItems (prevent dashboard residuals)
    ActionItem.objects.filter(
        application__project=project,
        status=ActionItemStatus.PENDING,
    ).update(status=ActionItemStatus.CANCELLED)

    # R1-03: HTMX requests use HX-Redirect for full page navigation
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = reverse("projects:project_detail", args=[project.pk])
        return response
    return redirect("projects:project_detail", pk=project.pk)

@login_required
@level_required(1)
@require_http_methods(["POST"])
def project_reopen(request, pk):
    """Reopen a closed project."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    # Permission: owner or assigned consultant
    is_owner = request.user.is_superuser or request.user.level >= 2
    is_assigned = project.assigned_consultants.filter(pk=request.user.pk).exists()
    if not (is_owner or is_assigned):
        return HttpResponseForbidden("권한이 없습니다.")

    project.closed_at = None
    project.status = ProjectStatus.OPEN
    project.result = ""
    project.save(update_fields=["closed_at", "status", "result", "updated_at"])

    # Recompute phase (signal only fires on ActionItem/Application changes)
    from projects.services.phase import compute_project_phase

    new_phase = compute_project_phase(project)
    if project.phase != new_phase:
        project.phase = new_phase
        project.save(update_fields=["phase"])

    return redirect("projects:project_detail", pk=project.pk)


# ---------------------------------------------------------------------------
# P05: Project Detail Tabs
# ---------------------------------------------------------------------------

@login_required
@level_required(1)
def project_tab_overview(request, pk):
    """개요: JD 요약, 퍼널, 담당자, 최근 진행 현황."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    context = _build_overview_context(project)
    context["project"] = project

    # P16: Work Continuity banners
    from projects.services.context import get_active_context, get_resume_url
    from projects.services.auto_actions import get_pending_actions

    ctx = get_active_context(project, request.user)
    context["context"] = ctx
    context["resume_url"] = get_resume_url(ctx) if ctx else None
    context["pending_actions"] = get_pending_actions(project)

    return render(request, "projects/partials/tab_overview.html", context)

@login_required
@level_required(1)
def project_tab_search(request, pk):
    """서칭: 매칭 결과 + Application 상태 표시."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    results = []
    if project.requirements:
        from projects.services.candidate_matching import match_candidates

        results = match_candidates(project.requirements, limit=50)

        # Application-based status lookup
        project_applications = {
            a.candidate_id: a
            for a in project.applications.select_related("candidate").all()
        }

        for item in results:
            cid = item["candidate"].pk
            app = project_applications.get(cid)

            if app:
                item["application_status"] = app.current_state
                item["disabled"] = True
            else:
                item["application_status"] = None
                item["disabled"] = False

    resume_uploads = ResumeUpload.objects.filter(project=project).exclude(
        status=ResumeUpload.Status.DISCARDED
    )

    return render(
        request,
        "projects/partials/tab_search.html",
        {
            "project": project,
            "results": results,
            "has_requirements": bool(project.requirements),
            "resume_uploads": resume_uploads,
        },
    )

@login_required
@level_required(1)
def project_tab_submissions(request, pk):
    """추천 탭: 상태별 그룹핑 목록."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    submissions = project.submissions.select_related(
        "candidate", "consultant"
    ).order_by("-created_at")

    # 상태별 그룹핑
    drafting = [s for s in submissions if s.status == Submission.Status.DRAFTING]
    submitted = [s for s in submissions if s.status == Submission.Status.SUBMITTED]
    passed = [s for s in submissions if s.status == Submission.Status.PASSED]
    rejected = [s for s in submissions if s.status == Submission.Status.REJECTED]

    return render(
        request,
        "projects/partials/tab_submissions.html",
        {
            "project": project,
            "drafting": drafting,
            "submitted": submitted,
            "passed": passed,
            "rejected": rejected,
            "total_count": submissions.count(),
        },
    )

@login_required
@level_required(1)
def project_tab_interviews(request, pk):
    """면접 탭: 후보자별 그룹핑, 차수 순 정렬."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    interviews = (
        Interview.objects.filter(submission__project=project)
        .select_related("submission__candidate", "submission__consultant")
        .order_by("submission__candidate__name", "round")
    )

    # 후보자별 그룹핑
    from itertools import groupby

    grouped = []
    for candidate, group in groupby(interviews, key=lambda i: i.submission.candidate):
        grouped.append(
            {
                "candidate": candidate,
                "interviews": list(group),
            }
        )

    return render(
        request,
        "projects/partials/tab_interviews.html",
        {
            "project": project,
            "grouped_interviews": grouped,
            "total_count": interviews.count(),
        },
    )

@login_required
@level_required(1)
def drive_picker(request, pk):
    """Drive 파일 선택 UI. GET=파일 목록, POST=파일 선택+텍스트 추출."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    if request.method == "POST":
        file_id = request.POST.get("file_id")
        if not file_id:
            return render(
                request,
                "projects/partials/jd_drive_picker.html",
                {"project": project, "error": "파일을 선택해주세요."},
            )

        from projects.services.jd_analysis import extract_text_from_drive

        try:
            raw_text = extract_text_from_drive(file_id)
        except (ValueError, RuntimeError) as e:
            return render(
                request,
                "projects/partials/jd_drive_picker.html",
                {"project": project, "error": str(e)},
            )

        project.jd_source = "drive"
        project.jd_drive_file_id = file_id
        project.jd_raw_text = raw_text
        # 기존 분석 리셋
        project.jd_analysis = {}
        project.requirements = {}
        project.save(
            update_fields=[
                "jd_source",
                "jd_drive_file_id",
                "jd_raw_text",
                "jd_analysis",
                "requirements",
            ]
        )

        return render(
            request,
            "projects/partials/jd_drive_picker.html",
            {"project": project, "success": True},
        )

    # GET: Drive 파일 목록
    from django.conf import settings as django_settings

    from data_extraction.services.drive import (
        get_drive_service,
        list_files_in_folder,
    )

    try:
        service = get_drive_service()
        parent_folder_id = getattr(django_settings, "GOOGLE_DRIVE_PARENT_FOLDER_ID", "")
        files = (
            list_files_in_folder(service, parent_folder_id) if parent_folder_id else []
        )
    except Exception:
        files = []

    return render(
        request,
        "projects/partials/jd_drive_picker.html",
        {"project": project, "drive_files": files},
    )
