import json

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import Organization

from .forms import ContactForm, ProjectForm
from .models import Contact, Interview, Offer, Project, ProjectStatus

PAGE_SIZE = 20

# days_elapsed thresholds for list view urgency
URGENCY_RED_DAYS = 20
URGENCY_YELLOW_DAYS = 10


def _get_org(request):
    """Return the current user's Organization via Membership, or 404."""
    return get_object_or_404(Organization, memberships__user=request.user)


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
def project_list(request):
    """List projects with scope/client/status filters, sorting, and multi-view."""
    org = _get_org(request)
    view_type = request.GET.get("view", "board")
    if view_type not in ("board", "list", "table"):
        view_type = "board"

    projects = Project.objects.filter(organization=org)

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
@require_http_methods(["PATCH"])
def status_update(request, pk):
    """Update project status via PATCH (kanban drag-and-drop)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    data = json.loads(request.body)
    new_status = data.get("status")

    if new_status not in ProjectStatus.values:
        return JsonResponse({"error": "invalid status"}, status=400)

    project.status = new_status
    project.save(update_fields=["status"])
    return HttpResponse(status=204)


@login_required
def project_create(request):
    """Create a new project. GET=form, POST=save."""
    org = _get_org(request)

    if request.method == "POST":
        form = ProjectForm(request.POST, request.FILES, organization=org)
        if form.is_valid():
            project = form.save(commit=False)
            project.organization = org
            project.created_by = request.user
            project.save()
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
def project_update(request, pk):
    """Update an existing project."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

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
def project_delete(request, pk):
    """Delete a project. Block if contacts or submissions exist."""
    if request.method != "POST":
        return HttpResponse(status=405)

    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

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

    return {
        "funnel": funnel,
        "recent_contacts": recent_contacts,
        "recent_submissions": recent_submissions,
        "consultants": consultants,
    }


@login_required
def project_tab_overview(request, pk):
    """개요: JD 요약, 퍼널, 담당자, 최근 진행 현황."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    context = _build_overview_context(project)
    context["project"] = project
    return render(request, "projects/partials/tab_overview.html", context)


@login_required
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

    return render(
        request,
        "projects/partials/tab_search.html",
        {
            "project": project,
            "results": results,
            "has_requirements": bool(project.requirements),
        },
    )


@login_required
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

    return render(
        request,
        "projects/partials/tab_contacts.html",
        {
            "project": project,
            "completed_contacts": completed_contacts,
            "reserved_contacts": reserved_contacts,
            "can_release": request.user in project.assigned_consultants.all(),
        },
    )


@login_required
def project_tab_submissions(request, pk):
    """추천: Submission 목록 (기본). 후속 Phase에서 완성."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submissions = project.submissions.select_related(
        "candidate", "consultant"
    ).order_by("-created_at")
    return render(
        request,
        "projects/partials/tab_submissions.html",
        {"project": project, "submissions": submissions},
    )


@login_required
def project_tab_interviews(request, pk):
    """면접: Interview 목록 (기본). 후속 Phase에서 완성."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    interviews = (
        Interview.objects.filter(submission__project=project)
        .select_related("submission__candidate")
        .order_by("-scheduled_at")
    )
    return render(
        request,
        "projects/partials/tab_interviews.html",
        {"project": project, "interviews": interviews},
    )


@login_required
def project_tab_offers(request, pk):
    """오퍼: Offer 목록 (기본). 후속 Phase에서 완성."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    offers = (
        Offer.objects.filter(submission__project=project)
        .select_related("submission__candidate")
        .order_by("-created_at")
    )
    return render(
        request,
        "projects/partials/tab_offers.html",
        {"project": project, "offers": offers},
    )


# ---------------------------------------------------------------------------
# P03a: JD Analysis views
# ---------------------------------------------------------------------------


@login_required
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
def contact_create(request, pk):
    """컨택 기록 등록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

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
        form = ContactForm(organization=org)

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
