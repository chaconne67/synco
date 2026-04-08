import json

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import Organization

from .forms import ProjectForm
from .models import Project, ProjectStatus

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
    """Project detail view."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    return render(
        request,
        "projects/project_detail.html",
        {"project": project},
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
        return render(
            request,
            "projects/project_detail.html",
            {
                "project": project,
                "error_message": "컨택 또는 제출 이력이 있어 삭제할 수 없습니다.",
            },
        )

    project.delete()
    return redirect("projects:project_list")


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
