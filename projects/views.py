import json
import os
import uuid

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.decorators import membership_required, role_required
from accounts.helpers import _get_org
from accounts.models import Organization

from projects.services import posting as posting_service
from projects.services.resume.linker import link_resume_to_candidate
from projects.services.resume.transitions import transition_status
from projects.services.resume.uploader import (
    FileValidationError,
    create_upload,
    process_pending_upload,
)

from .forms import (
    ContactForm,
    InterviewForm,
    InterviewResultForm,
    OfferForm,
    PostingEditForm,
    PostingSiteForm,
    ProjectForm,
    SubmissionFeedbackForm,
    SubmissionForm,
)
from .models import (
    Contact,
    DEFAULT_MASKING_CONFIG,
    DraftStatus,
    Interview,
    Offer,
    OutputLanguage,
    PostingSite,
    Project,
    ProjectApproval,
    ProjectStatus,
    ResumeUpload,
    Submission,
    SubmissionDraft,
)

from accounts.models import Membership

PAGE_SIZE = 20

# days_elapsed thresholds for list view urgency
URGENCY_RED_DAYS = 20
URGENCY_YELLOW_DAYS = 10



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
    """List projects with scope/client/status filters, sorting, and multi-view."""
    org = _get_org(request)
    view_type = request.GET.get("view", "board")
    if view_type not in ("board", "list", "table"):
        view_type = "board"

    # Role-based filtering: consultant/viewer see only assigned projects
    membership = request.user.membership
    if membership.role == "owner":
        projects = Project.objects.filter(organization=org)
    else:
        projects = Project.objects.filter(
            organization=org, assigned_consultants=request.user
        )

    # scope filter (default: mine)
    scope = request.GET.get("scope", "mine")
    if scope == "mine":
        projects = projects.filter(
            Q(assigned_consultants=request.user) | Q(created_by=request.user)
        ).distinct()

    # client filter
    client_id = request.GET.get("client", "")
    if client_id:
        projects = projects.filter(client_id=client_id)

    # status filter
    status = request.GET.get("status", "")
    if status:
        projects = projects.filter(status=status)

    # sorting: days_desc = oldest first (created_at asc), days_asc = newest first
    sort = request.GET.get("sort", "days_desc")
    if sort == "days_asc":
        projects = projects.order_by("-created_at")
    elif sort == "created":
        projects = projects.order_by("-created_at")
    else:  # days_desc (default) -- most elapsed days first = oldest created_at
        projects = projects.order_by("created_at")

    context = {
        "scope": scope,
        "current_client": client_id,
        "current_status": status,
        "current_sort": sort,
        "clients": org.clients.all(),
        "status_choices": ProjectStatus.choices,
        "view_type": view_type,
        "filter_params": _filter_params_string(request),
    }

    if view_type == "board":
        # Group projects by status -- all 10 statuses shown
        status_groups = {}
        for status_value, status_label in ProjectStatus.choices:
            status_groups[status_value] = {
                "label": status_label,
                "projects": list(projects.filter(status=status_value)),
            }
        context["status_groups"] = status_groups

    elif view_type == "list":
        # Urgency groups based on days_elapsed
        from django.utils import timezone

        now = timezone.now()
        threshold_red = now - timezone.timedelta(days=URGENCY_RED_DAYS)
        threshold_yellow = now - timezone.timedelta(days=URGENCY_YELLOW_DAYS)

        red = projects.filter(created_at__lte=threshold_red)
        yellow = projects.filter(
            created_at__gt=threshold_red, created_at__lte=threshold_yellow
        )
        green = projects.filter(created_at__gt=threshold_yellow)

        context["urgency_groups"] = [
            {"level": "red", "label": "긴급", "projects": list(red)},
            {"level": "yellow", "label": "이번 주", "projects": list(yellow)},
            {"level": "green", "label": "정상 진행", "projects": list(green)},
        ]

    elif view_type == "table":
        # Annotate counts + paginate
        projects = projects.annotate(
            contact_count=Count("contacts", distinct=True),
            submission_count=Count("submissions", distinct=True),
            interview_count=Count("submissions__interviews", distinct=True),
        )
        paginator = Paginator(projects, PAGE_SIZE)
        context["page_obj"] = paginator.get_page(request.GET.get("page"))

    template = f"projects/partials/view_{view_type}.html"

    # HTMX tab switch -> partial only
    if request.headers.get("HX-Request") and request.GET.get("tab_switch"):
        return render(request, template, context)

    context["view_template"] = template
    return render(request, "projects/project_list.html", context)


@login_required
@membership_required
@require_http_methods(["PATCH"])
def status_update(request, pk):
    """Update project status via PATCH (kanban drag-and-drop)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # Block any status change for pending_approval projects
    if project.status == ProjectStatus.PENDING_APPROVAL:
        return HttpResponse(status=403)

    data = json.loads(request.body)
    new_status = data.get("status")

    if new_status not in ProjectStatus.values:
        return JsonResponse({"error": "invalid status"}, status=400)

    # Block transition TO pending_approval
    if new_status == ProjectStatus.PENDING_APPROVAL:
        return JsonResponse({"error": "invalid status"}, status=400)

    project.status = new_status
    project.save(update_fields=["status"])
    return HttpResponse(status=204)


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
                    # Collision detected -> pending_approval
                    project.status = ProjectStatus.PENDING_APPROVAL
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
                    from projects.telegram.keyboards import build_approval_keyboard
                    from projects.telegram.formatters import format_approval_request

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
                                request.user.get_full_name()
                                or request.user.username
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


@login_required
@membership_required
def project_detail(request, pk):
    """Project detail — tab wrapper + overview tab inline."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # 탭 배지 카운트
    tab_counts = {
        "contacts": project.contacts.count(),
        "submissions": project.submissions.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
        "offers": Offer.objects.filter(submission__project=project).count(),
    }

    # 개요 탭 데이터 인라인 (초기 로드 시 추가 요청 없이)
    overview_context = _build_overview_context(project)

    return render(
        request,
        "projects/project_detail.html",
        {
            "project": project,
            "tab_counts": tab_counts,
            "active_tab": "overview",
            **overview_context,
        },
    )


@login_required
@membership_required
def project_update(request, pk):
    """Update an existing project."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if project.status == ProjectStatus.PENDING_APPROVAL:
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
    """Delete a project. Block if contacts or submissions exist."""
    if request.method != "POST":
        return HttpResponse(status=405)

    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if project.status == ProjectStatus.PENDING_APPROVAL:
        return HttpResponse(status=403)

    # Check for related contacts or submissions
    has_contacts = project.contacts.exists()
    has_submissions = project.submissions.exists()

    if has_contacts or has_submissions:
        tab_counts = {
            "contacts": project.contacts.count(),
            "submissions": project.submissions.count(),
            "interviews": Interview.objects.filter(submission__project=project).count(),
            "offers": Offer.objects.filter(submission__project=project).count(),
        }
        overview_context = _build_overview_context(project)
        return render(
            request,
            "projects/project_detail.html",
            {
                "project": project,
                "tab_counts": tab_counts,
                "active_tab": "overview",
                "error_message": "컨택 또는 제출 이력이 있어 삭제할 수 없습니다.",
                **overview_context,
            },
        )

    project.delete()
    return redirect("projects:project_list")


# ---------------------------------------------------------------------------
# P05: Project Detail Tabs
# ---------------------------------------------------------------------------


def _build_overview_context(project):
    """개요 탭 공통 컨텍스트."""
    funnel = {
        "contacts": project.contacts.count(),
        "submissions": project.submissions.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
        "offers": Offer.objects.filter(submission__project=project).count(),
    }

    recent_contacts = project.contacts.select_related(
        "candidate", "consultant"
    ).order_by("-contacted_at")[:3]
    recent_submissions = project.submissions.select_related(
        "candidate", "consultant"
    ).order_by("-created_at")[:2]

    consultants = project.assigned_consultants.all()

    # P10: posting data
    posting_sites = project.posting_sites.filter(is_active=True)
    total_applicants = sum(s.applicant_count for s in posting_sites)

    return {
        "funnel": funnel,
        "recent_contacts": recent_contacts,
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
    """서칭: 매칭 결과 + 컨택 상태 표시 + 예정 등록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # 만료 예정 건 해제
    from projects.services.contact import release_expired_reservations

    release_expired_reservations()

    results = []
    if project.requirements:
        from projects.services.candidate_matching import match_candidates

        results = match_candidates(project.requirements, organization=org, limit=50)

        from django.utils import timezone as tz

        now = tz.now()

        # 이 프로젝트의 컨택 이력
        project_contacts = {
            c.candidate_id: c
            for c in project.contacts.select_related("consultant").all()
        }

        # 다른 프로젝트의 컨택 이력 (같은 org)
        candidate_ids = [item["candidate"].pk for item in results]
        other_contacts = (
            Contact.objects.filter(candidate_id__in=candidate_ids)
            .exclude(project=project)
            .exclude(result=Contact.Result.RESERVED)
            .select_related("project", "consultant")
        )
        other_contacts_map: dict = {}
        for c in other_contacts:
            other_contacts_map.setdefault(c.candidate_id, []).append(c)

        for item in results:
            cid = item["candidate"].pk
            contact = project_contacts.get(cid)

            if contact:
                if contact.result == Contact.Result.RESERVED:
                    if contact.locked_until and contact.locked_until > now:
                        item["contact_status"] = "reserved"
                        item["reserved_by"] = contact.consultant
                        item["locked_until"] = contact.locked_until
                        item["disabled"] = contact.consultant != request.user
                    else:
                        item["contact_status"] = "expired"
                        item["disabled"] = False
                else:
                    item["contact_status"] = "contacted"
                    item["contact_result"] = contact.get_result_display()
                    item["disabled"] = True
            else:
                item["contact_status"] = None
                item["disabled"] = False

            item["other_project_contacts"] = other_contacts_map.get(cid, [])

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
def project_tab_contacts(request, pk):
    """컨택 탭: 완료 목록 + 예정 목록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # 만료 예정 건 잠금 해제
    from projects.services.contact import release_expired_reservations

    release_expired_reservations()

    from django.utils import timezone as tz

    now = tz.now()

    # 실제 컨택 완료 목록 (예정 제외)
    completed_contacts = (
        project.contacts.exclude(result=Contact.Result.RESERVED)
        .select_related("candidate", "consultant")
        .order_by("-contacted_at")
    )

    # 컨택 예정(잠금) 목록 — 유효한 것만
    reserved_contacts = (
        project.contacts.filter(result=Contact.Result.RESERVED, locked_until__gt=now)
        .select_related("candidate", "consultant")
        .order_by("-created_at")
    )

    # 이미 Submission이 있는 후보자 ID (추천 서류 작성 링크 표시 판단용)
    submitted_candidate_ids = set(
        project.submissions.values_list("candidate_id", flat=True)
    )

    return render(
        request,
        "projects/partials/tab_contacts.html",
        {
            "project": project,
            "completed_contacts": completed_contacts,
            "reserved_contacts": reserved_contacts,
            "can_release": request.user in project.assigned_consultants.all(),
            "submitted_candidate_ids": submitted_candidate_ids,
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


@login_required
@membership_required
def project_tab_offers(request, pk):
    """오퍼 탭: 목록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    offers = (
        Offer.objects.filter(submission__project=project)
        .select_related("submission__candidate", "submission__consultant")
        .order_by("-created_at")
    )
    return render(
        request,
        "projects/partials/tab_offers.html",
        {
            "project": project,
            "offers": offers,
            "total_count": offers.count(),
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
# P06: Contact Management
# ---------------------------------------------------------------------------


@login_required
@membership_required
def contact_create(request, pk):
    """컨택 기록 등록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if project.status == ProjectStatus.PENDING_APPROVAL:
        return HttpResponse(status=403)

    # P16: Resume support
    initial = {}
    resume_id = request.GET.get("resume")
    if resume_id:
        from projects.services.context import get_active_context

        ctx = get_active_context(project, request.user)
        if ctx and str(ctx.pk) == resume_id:
            initial = ctx.draft_data.get("fields", {})

    if request.method == "POST":
        form = ContactForm(request.POST, organization=org)
        if form.is_valid():
            # 중복 체크
            from projects.services.contact import check_duplicate

            dup = check_duplicate(project, form.cleaned_data["candidate"])
            if dup["blocked"]:
                return render(
                    request,
                    "projects/partials/contact_form.html",
                    {
                        "form": form,
                        "project": project,
                        "is_edit": False,
                        "duplicate_warnings": dup["warnings"],
                        "blocked": True,
                    },
                )

            contact = form.save(commit=False)
            contact.project = project
            contact.consultant = request.user
            contact.save()

            # 같은 후보자의 예정 건이 있으면 해제 (결과 기록 시 잠금 자동 해제)
            Contact.objects.filter(
                project=project,
                candidate=contact.candidate,
                result=Contact.Result.RESERVED,
            ).exclude(pk=contact.pk).update(
                locked_until=None,
            )

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "contactChanged"},
            )
    else:
        form = ContactForm(initial=initial, organization=org)

    # 프리필: query param으로 candidate 전달 시
    dup = None
    candidate_id = request.GET.get("candidate")
    if candidate_id and request.method != "POST":
        form.initial["candidate"] = candidate_id
        from candidates.models import Candidate
        from projects.services.contact import check_duplicate

        try:
            candidate_obj = Candidate.objects.get(pk=candidate_id, owned_by=org)
            dup = check_duplicate(project, candidate_obj)
        except Candidate.DoesNotExist:
            pass

    return render(
        request,
        "projects/partials/contact_form.html",
        {
            "form": form,
            "project": project,
            "is_edit": False,
            "duplicate_warnings": dup["warnings"] if dup else [],
            "other_project_contacts": dup["other_projects"] if dup else [],
            "blocked": dup["blocked"] if dup else False,
        },
    )


@login_required
@membership_required
def contact_update(request, pk, contact_pk):
    """컨택 기록 수정."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    contact = get_object_or_404(Contact, pk=contact_pk, project=project)

    if request.method == "POST":
        form = ContactForm(request.POST, instance=contact, organization=org)
        if form.is_valid():
            form.save()
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "contactChanged"},
            )
    else:
        form = ContactForm(instance=contact, organization=org)

    return render(
        request,
        "projects/partials/contact_form.html",
        {
            "form": form,
            "project": project,
            "contact": contact,
            "is_edit": True,
        },
    )


@login_required
@membership_required
@require_http_methods(["POST"])
def contact_delete(request, pk, contact_pk):
    """컨택 기록 삭제."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    contact = get_object_or_404(Contact, pk=contact_pk, project=project)
    contact.delete()
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "contactChanged"},
    )


@login_required
@membership_required
@require_http_methods(["POST"])
def contact_reserve(request, pk):
    """컨택 예정 등록 (잠금). 서칭 탭에서 체크박스 선택 후 호출."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    candidate_ids = request.POST.getlist("candidate_ids")
    if not candidate_ids:
        return HttpResponse("후보자를 선택해주세요.", status=400)

    from projects.services.contact import reserve_candidates

    reserve_candidates(project, candidate_ids, request.user)

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "contactChanged"},
    )


@login_required
@membership_required
@require_http_methods(["POST"])
def contact_release_lock(request, pk, contact_pk):
    """잠금 해제. 담당 컨설턴트 또는 잠금 본인만 가능."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    contact = get_object_or_404(
        Contact,
        pk=contact_pk,
        project=project,
        result=Contact.Result.RESERVED,
    )

    # 권한 체크: 담당 컨설턴트이거나 잠금 본인
    if (
        request.user not in project.assigned_consultants.all()
        and request.user != contact.consultant
    ):
        return HttpResponse("잠금 해제 권한이 없습니다.", status=403)

    contact.locked_until = None
    contact.save(update_fields=["locked_until"])

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "contactChanged"},
    )


@login_required
@membership_required
def contact_check_duplicate(request, pk):
    """중복 체크 (HTMX partial). 후보자 드롭다운 변경 시 호출."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    candidate_id = request.GET.get("candidate")
    if not candidate_id:
        return HttpResponse("")

    from candidates.models import Candidate
    from projects.services.contact import check_duplicate

    try:
        candidate = Candidate.objects.get(pk=candidate_id, owned_by=org)
    except Candidate.DoesNotExist:
        return HttpResponse("")

    dup = check_duplicate(project, candidate)

    return render(
        request,
        "projects/partials/duplicate_check_result.html",
        {
            "duplicate": dup,
            "project": project,
        },
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

    if project.status == ProjectStatus.PENDING_APPROVAL:
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

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "submissionChanged"},
            )
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

    # 삭제 보호: 면접 또는 오퍼 존재 시 차단
    has_interviews = submission.interviews.exists()
    has_offer = hasattr(submission, "offer")
    try:
        submission.offer
        has_offer = True
    except Offer.DoesNotExist:
        has_offer = False

    if has_interviews or has_offer:
        return HttpResponse(
            "면접 또는 오퍼 이력이 있어 삭제할 수 없습니다.",
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

    if project.status == ProjectStatus.PENDING_APPROVAL:
        return HttpResponse(status=403)

    if request.method == "POST":
        form = InterviewForm(request.POST, project=project)
        if form.is_valid():
            form.save()

            # 프로젝트 status 자동 전환
            from projects.services.lifecycle import maybe_advance_to_interviewing

            maybe_advance_to_interviewing(project)

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
    """면접 삭제. 삭제 보호: Offer가 연결된 Submission의 Interview는 삭제 불가."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    interview = get_object_or_404(
        Interview,
        pk=interview_pk,
        submission__project=project,
    )

    # 삭제 보호: Offer가 연결된 Submission의 Interview는 삭제 불가
    if hasattr(interview.submission, "offer"):
        return HttpResponse(
            "오퍼가 등록된 추천 건의 면접은 삭제할 수 없습니다.",
            status=400,
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
            from projects.services.lifecycle import (
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
# P09: Offer CRUD
# ---------------------------------------------------------------------------


@login_required
@membership_required
def offer_create(request, pk):
    """오퍼 등록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if project.status == ProjectStatus.PENDING_APPROVAL:
        return HttpResponse(status=403)

    if request.method == "POST":
        form = OfferForm(request.POST, project=project)
        if form.is_valid():
            form.save()

            # 프로젝트 status 자동 전환
            from projects.services.lifecycle import maybe_advance_to_negotiating

            maybe_advance_to_negotiating(project)

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "offerChanged"},
            )
    else:
        form = OfferForm(project=project)

    return render(
        request,
        "projects/partials/offer_form.html",
        {
            "form": form,
            "project": project,
            "is_edit": False,
        },
    )


@login_required
@membership_required
def offer_update(request, pk, offer_pk):
    """오퍼 수정. 협상중 상태에서만."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    offer = get_object_or_404(
        Offer,
        pk=offer_pk,
        submission__project=project,
    )

    if request.method == "POST":
        form = OfferForm(request.POST, instance=offer, project=project)
        if form.is_valid():
            form.save()
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "offerChanged"},
            )
    else:
        form = OfferForm(instance=offer, project=project)

    return render(
        request,
        "projects/partials/offer_form.html",
        {
            "form": form,
            "project": project,
            "offer": offer,
            "is_edit": True,
        },
    )


@login_required
@membership_required
@require_http_methods(["POST"])
def offer_delete(request, pk, offer_pk):
    """오퍼 삭제. 수락/거절 상태에서는 삭제 불가."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    offer = get_object_or_404(
        Offer,
        pk=offer_pk,
        submission__project=project,
    )

    if offer.status != Offer.Status.NEGOTIATING:
        return HttpResponse(
            "수락 또는 거절된 오퍼는 삭제할 수 없습니다.",
            status=400,
        )

    offer.delete()
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "offerChanged"},
    )


@login_required
@membership_required
@require_http_methods(["POST"])
def offer_accept(request, pk, offer_pk):
    """오퍼 수락 (협상중 → 수락)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    offer = get_object_or_404(
        Offer,
        pk=offer_pk,
        submission__project=project,
    )

    from projects.services.lifecycle import (
        InvalidTransition,
        accept_offer,
        maybe_advance_to_closed_success,
    )

    try:
        accept_offer(offer)
    except InvalidTransition as e:
        return HttpResponse(str(e), status=400)

    # 프로젝트 status 자동 전환
    maybe_advance_to_closed_success(project)

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "offerChanged"},
    )


@login_required
@membership_required
@require_http_methods(["POST"])
def offer_reject(request, pk, offer_pk):
    """오퍼 거절 (협상중 → 거절)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    offer = get_object_or_404(
        Offer,
        pk=offer_pk,
        submission__project=project,
    )

    from projects.services.lifecycle import InvalidTransition, reject_offer

    try:
        reject_offer(offer)
    except InvalidTransition as e:
        return HttpResponse(str(e), status=400)

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "offerChanged"},
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
                    status__in=[
                        "closed_success",
                        "closed_fail",
                        "closed_cancel",
                        "pending_approval",
                    ],
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
# P13: Dashboard
# ---------------------------------------------------------------------------


@login_required
@membership_required
def dashboard(request):
    """대시보드 메인 화면."""
    org = _get_org(request)
    user = request.user

    from projects.services.dashboard import (
        get_pending_approvals,
        get_pipeline_summary,
        get_recent_activities,
        get_team_summary,
        get_today_actions,
        get_weekly_schedule,
    )

    today_actions = get_today_actions(user, org)
    weekly_schedule = get_weekly_schedule(user, org)
    pipeline = get_pipeline_summary(user, org)
    activities = get_recent_activities(user, org, limit=10)

    is_owner = False
    try:
        is_owner = request.user.membership.role == "owner"
    except Exception:
        pass

    context = {
        "today_actions": today_actions,
        "weekly_schedule": weekly_schedule,
        "pipeline": pipeline,
        "activities": activities,
        "is_owner": is_owner,
    }

    if is_owner:
        context["pending_approvals"] = get_pending_approvals(org)
        context["team_summary"] = get_team_summary(user, org)

    if getattr(request, "htmx", None):
        return render(request, "projects/partials/dash_full.html", context)
    return render(request, "projects/dashboard.html", context)


@login_required
@membership_required
def dashboard_actions(request):
    """오늘의 액션 HTMX partial (새로고침용)."""
    org = _get_org(request)

    from projects.services.dashboard import get_today_actions

    today_actions = get_today_actions(request.user, org)
    return render(
        request,
        "projects/partials/dash_actions.html",
        {"today_actions": today_actions},
    )


@login_required
@role_required("owner")
def dashboard_team(request):
    """팀 현황 HTMX partial (OWNER 전용)."""
    org = _get_org(request)

    from projects.services.dashboard import get_pending_approvals, get_team_summary

    context = {
        "pending_approvals": get_pending_approvals(org),
        "team_summary": get_team_summary(request.user, org),
    }
    return render(request, "projects/partials/dash_admin.html", context)


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
        status__in=[
            ProjectStatus.CLOSED_SUCCESS,
            ProjectStatus.CLOSED_FAIL,
            ProjectStatus.CLOSED_CANCEL,
        ],
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
