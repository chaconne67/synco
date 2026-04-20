import json
import os
import uuid
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import models as db_models
from django.db.models import Max
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.decorators import membership_required, role_required
from accounts.helpers import _get_org
from accounts.models import Membership

from projects.services import posting as posting_service
from projects.services.dashboard import get_dashboard_context
from projects.services.action_lifecycle import (
    complete_action as complete_action_item,
    create_action as create_action_item,
    propose_next as propose_next_actions,
    reschedule_action as reschedule_action_item,
    skip_action as skip_action_item,
)
from projects.services.application_lifecycle import (
    create_application,
    drop as drop_application,
    hire as hire_application,
    restore as restore_application,
)
from projects.services.resume.linker import link_resume_to_candidate
from projects.services.resume.transitions import transition_status
from projects.services.resume.uploader import (
    FileValidationError,
    create_upload,
    process_pending_upload,
)

from .forms import (
    ActionItemCompleteForm,
    ActionItemCreateForm,
    ActionItemRescheduleForm,
    ActionItemSkipForm,
    ApplicationCreateForm,
    ApplicationDropForm,
    ContactCompleteForm,
    InterviewForm,
    InterviewResultForm,
    PostingEditForm,
    PostingSiteForm,
    ProjectCloseForm,
    ProjectForm,
    SubmissionFeedbackForm,
    SubmissionForm,
)
from .models import (
    ActionItem,
    ActionItemStatus,
    ActionType,
    Application,
    DEFAULT_MASKING_CONFIG,
    DraftStatus,
    DropReason,
    Interview,
    OutputLanguage,
    PostingSite,
    Project,
    ProjectApproval,
    ProjectPhase,
    ProjectStatus,
    ResumeUpload,
    Submission,
    SubmissionDraft,
)

PAGE_SIZE = 20

# days_elapsed thresholds for list view urgency
URGENCY_RED_DAYS = 20
URGENCY_YELLOW_DAYS = 10


def _has_pending_approval(project):
    """Check if the project has a pending approval (replaces PENDING_APPROVAL status)."""
    return ProjectApproval.objects.filter(
        project=project, status=ProjectApproval.Status.PENDING
    ).exists()


def _filter_params_string(request, exclude=None):
    """Build query string from current filter params (scope, client, status, sort)."""
    exclude = exclude or []
    params = []
    for key in ("scope", "client", "status", "sort"):
        if key in exclude:
            continue
        val = request.GET.get(key, "")
        if val:
            params.append(f"{key}={val}")
    return "&".join(params)


@login_required
@membership_required
def project_list(request):
    """List projects as 2-phase kanban (searching / screening / closed)."""
    org = _get_org(request)

    from projects.services.dashboard import get_project_kanban_cards

    # Role-based filtering (existing pattern preserved)
    membership = request.user.membership
    is_owner = membership.role == "owner"

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
        org,
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
        organization=org,
        status=ProjectStatus.OPEN,
        deadline__year=now.year,
        deadline__month=now.month,
    ).count()

    # Owner 는 필터 바에서 컨설턴트 선택 가능. 조직 멤버 리스트 필요.
    from accounts.models import Membership

    if is_owner:
        org_consultants = [
            m.user
            for m in Membership.objects.filter(
                organization=org, status="active"
            ).select_related("user")
        ]
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
        "clients": org.clients.all(),
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
@membership_required
@require_http_methods(["POST"])
def project_check_collision(request):
    """HTMX endpoint: check for collision when client + title are provided."""
    org = _get_org(request)
    client_id = request.POST.get("client_id")
    title = request.POST.get("title", "").strip()

    if not client_id or not title:
        return HttpResponse("")

    from projects.services.collision import detect_collisions

    collisions = detect_collisions(client_id, title, org)

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
@membership_required
def project_create(request):
    """Create a new project. GET=form, POST=save with collision detection."""
    org = _get_org(request)

    if request.method == "POST":
        form = ProjectForm(request.POST, request.FILES, organization=org)
        if form.is_valid():
            from django.contrib import messages as django_messages
            from django.db import transaction

            from projects.services.collision import detect_collisions

            client_id = form.cleaned_data["client"].pk
            title = form.cleaned_data["title"]
            collisions = detect_collisions(client_id, title, org)

            high_collisions = [
                c for c in collisions if c["conflict_type"] == "높은중복"
            ]

            with transaction.atomic():
                project = form.save(commit=False)
                project.organization = org
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

                    # A1: Send Telegram approval notification to org owners
                    from projects.models import Notification
                    from projects.services.notification import send_notification
                    from projects.telegram.formatters import format_approval_request
                    from projects.telegram.keyboards import build_approval_keyboard

                    owner_memberships = Membership.objects.filter(
                        organization=org,
                        role=Membership.Role.OWNER,
                    ).select_related("user")

                    for m in owner_memberships:
                        notif = Notification.objects.create(
                            recipient=m.user,
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
        form = ProjectForm(organization=org)

    return render(
        request,
        "projects/project_form.html",
        {"form": form, "is_edit": False},
    )


def _build_tab_context(project):
    """Build tab_counts and tab_latest for project detail template.

    Submission은 Application 경유(related_name 'submission' 단수). Project에서 직접 역참조 불가.
    """
    submissions_qs = Submission.objects.filter(application__project=project)
    tab_counts = {
        "applications": Application.objects.filter(project=project).count(),
        "submissions": submissions_qs.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
    }
    tab_latest = {
        "applications": Application.objects.filter(project=project).aggregate(
            latest=Max("created_at")
        )["latest"],
        "submissions": submissions_qs.aggregate(latest=Max("created_at"))["latest"],
        "interviews": Interview.objects.filter(submission__project=project).aggregate(
            latest=Max("created_at")
        )["latest"],
    }
    return tab_counts, tab_latest


@login_required
@membership_required
def project_detail(request, pk):
    """Project detail — Application-based view."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

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
@membership_required
def project_applications_partial(request, pk):
    """HTMX partial: application list for a project. R1-11: explicit prefetch."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
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
@membership_required
def project_timeline_partial(request, pk):
    """HTMX partial: action timeline for a project."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
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
@membership_required
def project_update(request, pk):
    """Update an existing project."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # Block edit if pending approval exists
    has_pending_approval = ProjectApproval.objects.filter(
        project=project, status=ProjectApproval.Status.PENDING
    ).exists()
    if has_pending_approval:
        return HttpResponse(status=403)

    if request.method == "POST":
        form = ProjectForm(
            request.POST, request.FILES, instance=project, organization=org
        )
        if form.is_valid():
            form.save()
            return redirect("projects:project_detail", pk=project.pk)
    else:
        form = ProjectForm(instance=project, organization=org)

    return render(
        request,
        "projects/project_form.html",
        {"form": form, "project": project, "is_edit": True},
    )


@login_required
@role_required("owner")
def project_delete(request, pk):
    """Delete a project. Block if applications or submissions exist."""
    if request.method != "POST":
        return HttpResponse(status=405)

    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

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
@membership_required
def project_close(request, pk):
    """GET: render close modal form. POST: close the project."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # Permission: owner or assigned consultant
    membership = request.user.membership
    is_owner = membership.role == "owner"
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
@membership_required
@require_http_methods(["POST"])
def project_reopen(request, pk):
    """Reopen a closed project."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # Permission: owner or assigned consultant
    membership = request.user.membership
    is_owner = membership.role == "owner"
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


def _build_overview_context(project):
    """개요 탭 공통 컨텍스트 (Application-based)."""
    active_apps = Application.objects.filter(
        project=project, dropped_at__isnull=True, hired_at__isnull=True
    )
    funnel = {
        "applications": Application.objects.filter(project=project).count(),
        "active": active_apps.count(),
        "submissions": project.submissions.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
    }

    recent_applications = (
        Application.objects.filter(project=project)
        .select_related("candidate")
        .order_by("-created_at")[:3]
    )
    recent_submissions = project.submissions.select_related(
        "candidate", "consultant"
    ).order_by("-created_at")[:2]

    consultants = project.assigned_consultants.all()

    # P10: posting data
    posting_sites = project.posting_sites.filter(is_active=True)
    total_applicants = sum(s.applicant_count for s in posting_sites)

    return {
        "funnel": funnel,
        "recent_applications": recent_applications,
        "recent_submissions": recent_submissions,
        "consultants": consultants,
        "posting_sites": posting_sites,
        "total_applicants": total_applicants,
    }


@login_required
@membership_required
def project_tab_overview(request, pk):
    """개요: JD 요약, 퍼널, 담당자, 최근 진행 현황."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
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
@membership_required
def project_tab_search(request, pk):
    """서칭: 매칭 결과 + Application 상태 표시."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    results = []
    if project.requirements:
        from projects.services.candidate_matching import match_candidates

        results = match_candidates(project.requirements, organization=org, limit=50)

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
@membership_required
def project_tab_submissions(request, pk):
    """추천 탭: 상태별 그룹핑 목록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
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
@membership_required
def project_tab_interviews(request, pk):
    """면접 탭: 후보자별 그룹핑, 차수 순 정렬."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

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


# ---------------------------------------------------------------------------
# P03a: JD Analysis views
# ---------------------------------------------------------------------------


@login_required
@membership_required
@require_http_methods(["POST"])
def analyze_jd(request, pk):
    """JD 분석 트리거. 파일 업로드 시 텍스트 추출 후 AI 분석."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    from projects.services.jd_analysis import (
        analyze_jd as run_analysis,
        extract_text_from_file,
    )

    # 파일 업로드 소스인 경우: 파일에서 텍스트 추출
    if project.jd_source == "upload" and project.jd_file:
        if not project.jd_raw_text:
            try:
                project.jd_raw_text = extract_text_from_file(project.jd_file)
                project.save(update_fields=["jd_raw_text"])
            except (ValueError, RuntimeError) as e:
                return render(
                    request,
                    "projects/partials/jd_analysis_error.html",
                    {"error": str(e), "project": project},
                )

    # AI 분석 실행
    try:
        result = run_analysis(project)
    except ValueError as e:
        return render(
            request,
            "projects/partials/jd_analysis_error.html",
            {"error": str(e), "project": project},
        )
    except RuntimeError as e:
        return render(
            request,
            "projects/partials/jd_analysis_error.html",
            {"error": str(e), "project": project},
        )

    # 분석 결과 partial 반환
    return render(
        request,
        "projects/partials/jd_analysis_result.html",
        {"project": project, "analysis": result},
    )


@login_required
@membership_required
def jd_results(request, pk):
    """JD 분석 결과 표시 (HTMX partial)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    return render(
        request,
        "projects/partials/jd_analysis_result.html",
        {
            "project": project,
            "analysis": {
                "requirements": project.requirements,
                "full_analysis": project.jd_analysis,
            },
        },
    )


@login_required
@membership_required
def drive_picker(request, pk):
    """Drive 파일 선택 UI. GET=파일 목록, POST=파일 선택+텍스트 추출."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

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


@login_required
@membership_required
@require_http_methods(["POST"])
def start_search_session(request, pk):
    """프로젝트 requirements → SearchSession 생성 → 후보자 검색으로 redirect."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if not project.requirements:
        return render(
            request,
            "projects/partials/jd_analysis_error.html",
            {"error": "JD 분석이 먼저 필요합니다.", "project": project},
        )

    from candidates.models import SearchSession

    from projects.services.jd_analysis import requirements_to_search_filters

    filters = requirements_to_search_filters(project.requirements)

    session = SearchSession.objects.create(
        user=request.user,
        current_filters=filters,
    )

    return redirect(f"/candidates/?session_id={session.pk}")


@login_required
@membership_required
def jd_matching_results(request, pk):
    """프로젝트 상세 내 후보자 매칭 결과 목록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if not project.requirements:
        return render(
            request,
            "projects/partials/jd_matching_empty.html",
            {"project": project},
        )

    from projects.services.candidate_matching import match_candidates

    results = match_candidates(project.requirements, limit=50)

    return render(
        request,
        "projects/partials/jd_matching_results.html",
        {"project": project, "results": results},
    )


# ---------------------------------------------------------------------------
# P07: Submission Management
# ---------------------------------------------------------------------------


@login_required
@membership_required
def submission_create(request, pk):
    """추천 서류 등록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if _has_pending_approval(project):
        return HttpResponse(status=403)

    if request.method == "POST":
        form = SubmissionForm(
            request.POST, request.FILES, organization=org, project=project
        )
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
        form = SubmissionForm(organization=org, project=project)

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
@membership_required
@require_http_methods(["POST"])
def submission_batch_create(request, pk):
    """선택한 여러 Application 을 한 batch_id 로 묶어 Submission 생성."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
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
@membership_required
def submission_update(request, pk, sub_pk):
    """추천 서류 수정."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submission = get_object_or_404(Submission, pk=sub_pk, project=project)

    if request.method == "POST":
        form = SubmissionForm(
            request.POST,
            request.FILES,
            instance=submission,
            organization=org,
            project=project,
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
            organization=org,
            project=project,
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
@membership_required
@require_http_methods(["POST"])
def submission_delete(request, pk, sub_pk):
    """추천 서류 삭제. 면접/오퍼 존재 시 차단."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submission = get_object_or_404(Submission, pk=sub_pk, project=project)

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
@membership_required
@require_http_methods(["POST"])
def submission_submit(request, pk, sub_pk):
    """고객사에 제출 (작성중 → 제출)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submission = get_object_or_404(Submission, pk=sub_pk, project=project)

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
@membership_required
def submission_feedback(request, pk, sub_pk):
    """고객사 피드백 입력 (제출 → 통과/탈락)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submission = get_object_or_404(Submission, pk=sub_pk, project=project)

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
@membership_required
def submission_download(request, pk, sub_pk):
    """첨부파일 다운로드. 파일 없으면 404."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submission = get_object_or_404(Submission, pk=sub_pk, project=project)

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


# ---------------------------------------------------------------------------
# P08: AI Document Pipeline
# ---------------------------------------------------------------------------

ALLOWED_AUDIO_EXTENSIONS = {".webm", ".mp4", ".m4a", ".ogg", ".wav", ".mp3"}
MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25MB (Whisper API limit)


def _get_draft_context(request, pk, sub_pk):
    """Draft 뷰 공통: org 검증 + project + submission + draft(get_or_create)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submission = get_object_or_404(Submission, pk=sub_pk, project=project)
    draft, _created = SubmissionDraft.objects.get_or_create(
        submission=submission,
        defaults={"masking_config": DEFAULT_MASKING_CONFIG.copy()},
    )
    return org, project, submission, draft


@login_required
@membership_required
def submission_draft(request, pk, sub_pk):
    """초안 작업 메인 화면. 현재 상태에 따라 적절한 단계 표시."""
    _org, project, submission, draft = _get_draft_context(request, pk, sub_pk)
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
@membership_required
@require_http_methods(["POST"])
def draft_generate(request, pk, sub_pk):
    """AI 초안 생성. Gemini API 호출."""
    _org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

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
@membership_required
def draft_consultation(request, pk, sub_pk):
    """상담 내용 직접 입력."""
    _org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

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
@membership_required
@require_http_methods(["POST"])
def draft_consultation_audio(request, pk, sub_pk):
    """녹음 파일 업로드 + Whisper 딕테이션."""
    _org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

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
@membership_required
@require_http_methods(["POST"])
def draft_finalize(request, pk, sub_pk):
    """AI 최종 정리: 초안 + 상담 병합."""
    _org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

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
@membership_required
def draft_review(request, pk, sub_pk):
    """컨설턴트가 final_content_json을 직접 수정."""
    _org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

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
@membership_required
@require_http_methods(["POST"])
def draft_convert(request, pk, sub_pk):
    """제출용 Word 파일 변환 + 마스킹."""
    _org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

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
@membership_required
def draft_preview(request, pk, sub_pk):
    """현재 단계의 데이터를 미리보기."""
    _org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

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


# ---------------------------------------------------------------------------
# P09: Interview CRUD
# ---------------------------------------------------------------------------


@login_required
@membership_required
def interview_create(request, pk):
    """면접 등록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

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
@membership_required
def interview_update(request, pk, interview_pk):
    """면접 수정."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    interview = get_object_or_404(
        Interview,
        pk=interview_pk,
        submission__project=project,
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
@membership_required
@require_http_methods(["POST"])
def interview_delete(request, pk, interview_pk):
    """면접 삭제."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    interview = get_object_or_404(
        Interview,
        pk=interview_pk,
        submission__project=project,
    )

    interview.delete()
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "interviewChanged"},
    )


@login_required
@membership_required
def interview_result(request, pk, interview_pk):
    """면접 결과 입력 (대기 → 합격/보류/탈락)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    interview = get_object_or_404(
        Interview,
        pk=interview_pk,
        submission__project=project,
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


# ---------------------------------------------------------------------------
# P10: Posting Management
# ---------------------------------------------------------------------------


@login_required
@membership_required
@require_http_methods(["POST"])
def posting_generate(request, pk):
    """AI 공지 초안 생성. overwrite=true 필요 시 기존 내용 보호."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # I-07: 덮어쓰기 보호 — 기존 내용 있으면 overwrite 파라미터 필요
    if project.posting_text and request.POST.get("overwrite") != "true":
        posting_sites = project.posting_sites.filter(is_active=True)
        total_applicants = sum(s.applicant_count for s in posting_sites)
        return render(
            request,
            "projects/partials/posting_section.html",
            {
                "project": project,
                "posting_sites": posting_sites,
                "total_applicants": total_applicants,
                "confirm_overwrite": True,
            },
        )

    try:
        text = posting_service.generate_posting(project)
    except ValueError as e:
        return render(
            request,
            "projects/partials/posting_section.html",
            {"project": project, "error": str(e)},
        )
    except RuntimeError as e:
        return render(
            request,
            "projects/partials/posting_section.html",
            {"project": project, "error": str(e)},
        )

    project.posting_text = text
    project.posting_file_name = posting_service.get_posting_filename(
        project, request.user
    )
    project.save(update_fields=["posting_text", "posting_file_name", "updated_at"])

    posting_sites = project.posting_sites.filter(is_active=True)
    total_applicants = sum(s.applicant_count for s in posting_sites)

    return render(
        request,
        "projects/partials/posting_section.html",
        {
            "project": project,
            "posting_sites": posting_sites,
            "total_applicants": total_applicants,
        },
    )


@login_required
@membership_required
def posting_edit(request, pk):
    """공지 내용 편집. GET=폼, POST=저장."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if request.method == "POST":
        form = PostingEditForm(request.POST)
        if form.is_valid():
            project.posting_text = form.cleaned_data["posting_text"]
            project.save(update_fields=["posting_text", "updated_at"])

            posting_sites = project.posting_sites.filter(is_active=True)
            total_applicants = sum(s.applicant_count for s in posting_sites)

            return render(
                request,
                "projects/partials/posting_section.html",
                {
                    "project": project,
                    "posting_sites": posting_sites,
                    "total_applicants": total_applicants,
                },
            )
    else:
        form = PostingEditForm(initial={"posting_text": project.posting_text})

    return render(
        request,
        "projects/partials/posting_edit.html",
        {"project": project, "form": form},
    )


@login_required
@membership_required
def posting_download(request, pk):
    """공지 파일 다운로드 (.txt)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if not project.posting_text:
        return HttpResponse(status=404)

    filename = project.posting_file_name or "posting.txt"

    response = HttpResponse(
        project.posting_text,
        content_type="text/plain; charset=utf-8",
    )
    # RFC 5987 encoded filename for Korean characters
    from urllib.parse import quote

    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return response


@login_required
@membership_required
def posting_sites(request, pk):
    """포스팅 사이트 목록 (HTMX partial)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    sites = project.posting_sites.filter(is_active=True)
    total_applicants = sum(s.applicant_count for s in sites)

    return render(
        request,
        "projects/partials/posting_sites.html",
        {
            "project": project,
            "posting_sites": sites,
            "total_applicants": total_applicants,
        },
    )


@login_required
@membership_required
@require_http_methods(["GET", "POST"])
def posting_site_add(request, pk):
    """포스팅 사이트 추가."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if request.method == "POST":
        form = PostingSiteForm(request.POST)
        if form.is_valid():
            site_choice = form.cleaned_data["site"]
            # I-04: 비활성 레코드 재활성화
            existing = PostingSite.objects.filter(
                project=project, site=site_choice, is_active=False
            ).first()
            if existing:
                # Reactivate existing soft-deleted record
                for field in [
                    "posted_at",
                    "applicant_count",
                    "url",
                    "notes",
                    "is_active",
                ]:
                    setattr(
                        existing,
                        field,
                        form.cleaned_data.get(field, getattr(existing, field)),
                    )
                existing.is_active = True
                existing.save()
            else:
                site = form.save(commit=False)
                site.project = project
                try:
                    site.save()
                except Exception:
                    # UniqueConstraint violation (active duplicate)
                    form.add_error("site", "이미 등록된 사이트입니다.")
                    return render(
                        request,
                        "projects/partials/posting_site_form.html",
                        {"form": form, "project": project, "is_edit": False},
                    )
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "postingSiteChanged"},
            )
    else:
        form = PostingSiteForm()

    return render(
        request,
        "projects/partials/posting_site_form.html",
        {"form": form, "project": project, "is_edit": False},
    )


@login_required
@membership_required
@require_http_methods(["GET", "POST"])
def posting_site_update(request, pk, site_pk):
    """포스팅 사이트 수정."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    site = get_object_or_404(PostingSite, pk=site_pk, project=project)

    if request.method == "POST":
        form = PostingSiteForm(request.POST, instance=site)
        if form.is_valid():
            # I-03: IntegrityError 처리 (site 변경 시 중복 가능)
            try:
                form.save()
            except Exception:
                form.add_error("site", "이미 등록된 사이트입니다.")
                return render(
                    request,
                    "projects/partials/posting_site_form.html",
                    {
                        "form": form,
                        "project": project,
                        "site": site,
                        "is_edit": True,
                    },
                )
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "postingSiteChanged"},
            )
    else:
        form = PostingSiteForm(instance=site)

    return render(
        request,
        "projects/partials/posting_site_form.html",
        {"form": form, "project": project, "site": site, "is_edit": True},
    )


@login_required
@membership_required
@require_http_methods(["POST"])
def posting_site_delete(request, pk, site_pk):
    """포스팅 사이트 비활성화 (소프트 삭제)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    site = get_object_or_404(PostingSite, pk=site_pk, project=project)

    site.is_active = False
    site.save(update_fields=["is_active", "updated_at"])

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "postingSiteChanged"},
    )


# ---------------------------------------------------------------------------
# P11: Approval workflow views
# ---------------------------------------------------------------------------


def _is_owner(request):
    """Check if the current user has OWNER role in their organization."""
    try:
        return request.user.membership.role == Membership.Role.OWNER
    except Membership.DoesNotExist:
        return False


@login_required
@role_required("owner")
def approval_queue(request):
    """OWNER-only: list pending approval requests."""
    org = _get_org(request)

    approvals = (
        ProjectApproval.objects.filter(
            project__organization=org,
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
                    organization=org,
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
@role_required("owner")
@require_http_methods(["POST"])
def approval_decide(request, appr_pk):
    """OWNER-only: decide on an approval request."""
    org = _get_org(request)

    from .forms import ApprovalDecisionForm
    from .services.approval import (
        InvalidApprovalTransition,
        approve_project,
        merge_project,
        reject_project,
        send_admin_message,
    )

    approval = get_object_or_404(
        ProjectApproval,
        pk=appr_pk,
        project__organization=org,
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
                merge_target = get_object_or_404(
                    Project, pk=merge_target_id, organization=org
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
@membership_required
@require_http_methods(["POST"])
def approval_cancel(request, pk):
    """Requester cancels their approval request."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    approval = get_object_or_404(
        ProjectApproval,
        project=project,
        requested_by=request.user,
        status=ProjectApproval.Status.PENDING,
    )

    from .services.approval import cancel_approval

    cancel_approval(approval)

    return redirect("projects:project_list")


# ---------------------------------------------------------------------------
# P13: Dashboard (Phase 3a: rewritten with Application/ActionItem services)
# ---------------------------------------------------------------------------


@login_required
@membership_required
def dashboard(request):
    """대시보드 메인 화면 (Phase 2a: 실데이터 연결 진행 중)."""
    membership = request.user.membership
    ctx = get_dashboard_context(membership.organization, request.user, membership)
    if getattr(request, "htmx", None):
        return render(request, "projects/partials/dash_full.html", ctx)
    return render(request, "projects/dashboard.html", ctx)


# --- P16: Work Continuity ---

from projects.services.context import (
    discard_context,
    get_active_context,
    get_resume_url,
    save_context,
    validate_draft_data,
)
from projects.services.auto_actions import (
    apply_action,
    dismiss_action,
    get_pending_actions,
    ConflictError,
)
from .models import AutoAction


@login_required
@membership_required
@require_http_methods(["GET"])
def project_context(request, pk):
    """GET: Return active context banner partial."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
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
@membership_required
@require_http_methods(["POST"])
def project_context_save(request, pk):
    """POST: Save/update context (autosave endpoint)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

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
@membership_required
@require_http_methods(["POST"])
def project_context_resume(request, pk):
    """POST: Resume from context → redirect to target form."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
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
@membership_required
@require_http_methods(["POST"])
def project_context_discard(request, pk):
    """POST: Discard the active context."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
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


@login_required
@membership_required
@require_http_methods(["GET"])
def project_auto_actions(request, pk):
    """GET: List pending auto-actions."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
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
@membership_required
@require_http_methods(["POST"])
def auto_action_apply(request, pk, action_pk):
    """POST: Apply an auto-action."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
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
@membership_required
@require_http_methods(["POST"])
def auto_action_dismiss(request, pk, action_pk):
    """POST: Dismiss an auto-action."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
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


# ── P18: Resume Upload Views ──────────────────────────────────────────


@login_required
@membership_required
def resume_upload(request, pk):
    """POST: Upload resume files → create ResumeUpload(pending) per file."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if request.method != "POST":
        return HttpResponseBadRequest()

    batch_id = uuid.uuid4()
    uploads = []
    errors = []

    for f in request.FILES.getlist("files"):
        try:
            upload = create_upload(
                file=f,
                project=project,
                organization=org,
                user=request.user,
                upload_batch=batch_id,
            )
            uploads.append(upload)
        except FileValidationError as e:
            errors.append({"file": f.name, "error": str(e)})

    return render(
        request,
        "projects/partials/resume_status.html",
        {
            "uploads": uploads,
            "errors": errors,
            "batch_id": str(batch_id),
            "project": project,
        },
    )


@login_required
@membership_required
def resume_process_pending(request, pk):
    """POST: Process all pending uploads for batch. Runs extraction synchronously."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    batch_id = request.POST.get("batch_id")
    if not batch_id:
        return HttpResponseBadRequest("batch_id required")

    pending = ResumeUpload.objects.filter(
        project=project,
        upload_batch=batch_id,
        status=ResumeUpload.Status.PENDING,
    )
    for upload in pending:
        process_pending_upload(upload)

    uploads = ResumeUpload.objects.filter(
        project=project,
        upload_batch=batch_id,
    )
    return render(
        request,
        "projects/partials/resume_status.html",
        {
            "uploads": uploads,
            "project": project,
        },
    )


@login_required
@membership_required
def resume_upload_status(request, pk):
    """GET: HTMX polling endpoint for upload status."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    batch_id = request.GET.get("batch")
    uploads = ResumeUpload.objects.filter(
        project=project,
        created_by=request.user,
    )
    if batch_id:
        uploads = uploads.filter(upload_batch=batch_id)

    return render(
        request,
        "projects/partials/resume_status.html",
        {
            "uploads": uploads,
            "project": project,
        },
    )


@login_required
@membership_required
def resume_link_candidate(request, pk, resume_pk):
    """POST: Link extracted resume to candidate."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    upload = get_object_or_404(
        ResumeUpload.objects.filter(project=project),
        pk=resume_pk,
    )
    force_new = request.POST.get("force_new") == "true"

    try:
        link_resume_to_candidate(upload, user=request.user, force_new=force_new)
    except ValueError as e:
        return HttpResponseBadRequest(str(e))

    return render(
        request,
        "projects/partials/resume_status.html",
        {
            "uploads": [upload],
            "project": project,
        },
    )


@login_required
@membership_required
def resume_discard(request, pk, resume_pk):
    """POST: Discard resume upload + delete physical file."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    upload = get_object_or_404(
        ResumeUpload.objects.filter(project=project),
        pk=resume_pk,
    )

    transition_status(upload, ResumeUpload.Status.DISCARDED)
    if upload.file:
        upload.file.delete(save=False)

    return render(
        request,
        "projects/partials/resume_status.html",
        {
            "uploads": [upload],
            "project": project,
        },
    )


@login_required
@membership_required
def resume_retry(request, pk, resume_pk):
    """POST: Retry failed extraction (max 3 retries)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    upload = get_object_or_404(
        ResumeUpload.objects.filter(project=project),
        pk=resume_pk,
    )

    if upload.retry_count >= 3:
        return HttpResponseBadRequest("재시도 횟수를 초과했습니다.")

    upload.retry_count += 1
    upload.save(update_fields=["retry_count", "updated_at"])
    transition_status(upload, ResumeUpload.Status.PENDING)
    process_pending_upload(upload)

    return render(
        request,
        "projects/partials/resume_status.html",
        {
            "uploads": [upload],
            "project": project,
        },
    )


@login_required
@membership_required
def resume_unassigned(request):
    """GET: Org-scoped list of unassigned resume uploads (project=null)."""
    org = _get_org(request)
    uploads = ResumeUpload.objects.filter(
        organization=org,
        project__isnull=True,
    ).exclude(status=ResumeUpload.Status.DISCARDED)
    projects = Project.objects.filter(organization=org).exclude(
        status=ProjectStatus.CLOSED,
    )

    return render(
        request,
        "projects/resume_unassigned.html",
        {
            "uploads": uploads,
            "projects": projects,
        },
    )


@login_required
@membership_required
def resume_assign_project(request, resume_pk, project_pk):
    """POST: Assign an unassigned resume upload to a project."""
    org = _get_org(request)
    upload = get_object_or_404(
        ResumeUpload.objects.filter(organization=org, project__isnull=True),
        pk=resume_pk,
    )
    project = get_object_or_404(Project, pk=project_pk, organization=org)

    upload.project = project
    upload.save(update_fields=["project", "updated_at"])

    uploads = ResumeUpload.objects.filter(
        organization=org,
        project__isnull=True,
    ).exclude(status=ResumeUpload.Status.DISCARDED)

    return render(
        request,
        "projects/resume_unassigned.html",
        {
            "uploads": uploads,
        },
    )


# ===========================================================================
# Phase 3b: Application / ActionItem CRUD views
# ===========================================================================


@membership_required
def project_add_candidate(request, pk):
    """POST /projects/<pk>/add_candidate/ — Application 생성.
    GET: 후보자 추가 모달 폼 렌더링.
    POST (candidate_id): 서칭 페이지의 "프로젝트에 추가" 버튼 — 단건 직접 추가.
    POST (form): 모달 폼을 통한 추가 (기존 방식).
    """
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if request.method == "GET":
        form = ApplicationCreateForm(organization=org)
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
    form = ApplicationCreateForm(request.POST, organization=org)
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


@membership_required
def application_drop(request, pk):
    """GET: 드롭 사유 모달 렌더링. POST: Application 드롭."""
    org = _get_org(request)
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=org,
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


@membership_required
@require_POST
def application_restore(request, pk):
    """POST: Application 드롭 복구."""
    org = _get_org(request)
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=org,
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


@membership_required
@require_POST
def application_hire(request, pk):
    """POST: 입사 확정. Signal이 프로젝트 자동 종료 + 나머지 드롭."""
    org = _get_org(request)
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=org,
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
@membership_required
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

    org = _get_org(request)
    application = get_object_or_404(
        Application.objects.select_related("candidate", "project"),
        pk=pk,
        project__organization=org,
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


def _create_receive_resume_action(application, actor, *, done, note, due_days=0):
    """Phase B 헬퍼: receive_resume ActionType 으로 ActionItem 생성.

    ToDoList 모델: due_days=0 이면 마감 기한 없음 (대기 항목). done=True 면 즉시 완료.
    """
    from django.utils import timezone

    at = ActionType.objects.filter(code="receive_resume").first()
    if not at:
        return None
    now = timezone.now()
    due = now + timedelta(days=due_days) if due_days else None
    return ActionItem.objects.create(
        application=application,
        action_type=at,
        title=at.label_ko,
        note=note,
        status=ActionItemStatus.DONE if done else ActionItemStatus.PENDING,
        completed_at=now if done else None,
        scheduled_at=due,
        due_at=due,
        assigned_to=actor,
        created_by=actor,
    )


@login_required
@membership_required
@require_POST
def application_resume_use_db(request, pk):
    """Phase B — DB에 있는 기존 이력서 사용. receive_resume 즉시 완료."""
    org = _get_org(request)
    application = get_object_or_404(
        Application.objects.select_related("candidate", "project"),
        pk=pk,
        project__organization=org,
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
@membership_required
def application_resume_request_email(request, pk):
    """Phase B — 이메일로 이력서 요청. GET=폼 모달, POST=pending 액션 생성."""
    org = _get_org(request)
    application = get_object_or_404(
        Application.objects.select_related("candidate", "project"),
        pk=pk,
        project__organization=org,
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
@membership_required
def application_resume_upload(request, pk):
    """Phase B — 직접 받은 이력서 파일 업로드. GET=업로드 모달, POST=Resume+ActionItem 생성."""
    org = _get_org(request)
    application = get_object_or_404(
        Application.objects.select_related("candidate", "project"),
        pk=pk,
        project__organization=org,
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


@membership_required
def application_actions_partial(request, pk):
    """GET: Application의 ActionItem 목록. R1-11/R1-12: prefetch + ordering."""
    org = _get_org(request)
    application = get_object_or_404(
        Application.objects.select_related("candidate", "project"),
        pk=pk,
        project__organization=org,
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


@membership_required
def action_create(request, pk):
    """GET: 액션 생성 모달. POST: ActionItem 생성."""
    org = _get_org(request)
    application = get_object_or_404(
        Application,
        pk=pk,
        project__organization=org,
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


@membership_required
def action_complete(request, pk):
    """GET: 완료 모달 렌더링. POST: ActionItem 완료 + 후속 제안."""
    org = _get_org(request)
    action = get_object_or_404(
        ActionItem,
        pk=pk,
        application__project__organization=org,
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


@membership_required
def action_skip(request, pk):
    """GET: 건너뛰기 사유 모달. POST: ActionItem 건너뛰기."""
    org = _get_org(request)
    action = get_object_or_404(
        ActionItem,
        pk=pk,
        application__project__organization=org,
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


@membership_required
def action_reschedule(request, pk):
    """GET: 일정 변경 모달. POST: ActionItem 일정 변경."""
    org = _get_org(request)
    action = get_object_or_404(
        ActionItem,
        pk=pk,
        application__project__organization=org,
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


@membership_required
@require_POST
def action_propose_next(request, pk):
    """POST: 완료된 액션 다음에 컨설턴트가 선택한 후속 액션들을 생성.
    선택된 type IDs를 propose_next() 결과와 교차검증.
    """
    org = _get_org(request)
    action = get_object_or_404(
        ActionItem,
        pk=pk,
        application__project__organization=org,
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


@login_required
@membership_required
@require_http_methods(["POST"])
def stage_contact_complete(request, pk):
    """접촉 단계 완료 — 응답 기록."""
    app = get_object_or_404(Application, pk=pk)
    org = _get_org(request)
    if app.project.organization != org:
        return HttpResponseForbidden("cross-org access denied")

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
@membership_required
@require_http_methods(["POST"])
def stage_pre_meeting_schedule(request, pk):
    """사전 미팅 일정 확정."""
    from projects.forms import PreMeetingScheduleForm
    from projects.models import ActionItem, ActionItemStatus, ActionType

    app = get_object_or_404(Application, pk=pk)
    org = _get_org(request)
    if app.project.organization != org:
        return HttpResponseForbidden("cross-org access denied")

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
@membership_required
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

    app = get_object_or_404(Application, pk=pk)
    org = _get_org(request)
    if app.project.organization != org:
        return HttpResponseForbidden("cross-org access denied")

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
@membership_required
@require_http_methods(["POST"])
def stage_prep_submission_confirm(request, pk):
    """이력서 작성(제출용) 단계 — 컨설턴트 컨펌."""
    app = get_object_or_404(Application, pk=pk)
    org = _get_org(request)
    if app.project.organization != org:
        return HttpResponseForbidden("cross-org access denied")

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
@membership_required
@require_http_methods(["POST"])
def stage_client_submit_single(request, pk):
    """이력서 제출 단계 — 이 후보자만 단독 제출."""
    org = _get_org(request)
    app = get_object_or_404(Application, pk=pk)
    if app.project.organization != org:
        return HttpResponseForbidden("cross-org access denied")

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
@membership_required
@require_http_methods(["POST"])
def stage_interview_complete(request, pk):
    """면접 단계 완료 — 결과 + (선택) After Interview Review."""
    from projects.models import ActionItem, ActionItemStatus, ActionType, DropReason

    app = get_object_or_404(Application, pk=pk)
    org = _get_org(request)
    if app.project.organization != org:
        return HttpResponseForbidden("cross-org access denied")

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
