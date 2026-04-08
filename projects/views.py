from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import Organization

from .forms import ProjectForm
from .models import Project, ProjectStatus

PAGE_SIZE = 20


def _get_org(request):
    """Return the current user's Organization via Membership, or 404."""
    return get_object_or_404(Organization, memberships__user=request.user)


@login_required
def project_list(request):
    """List projects with scope/client/status filters, sorting, and pagination."""
    org = _get_org(request)
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

    # sorting: days_desc = oldest first (created_at asc), days_asc = newest first (created_at desc)
    sort = request.GET.get("sort", "days_desc")
    if sort == "days_asc":
        projects = projects.order_by("-created_at")
    elif sort == "created":
        projects = projects.order_by("-created_at")
    else:  # days_desc (default) — most elapsed days first = oldest created_at
        projects = projects.order_by("created_at")

    paginator = Paginator(projects, PAGE_SIZE)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "projects/project_list.html",
        {
            "page_obj": page_obj,
            "scope": scope,
            "current_client": client_id,
            "current_status": status,
            "current_sort": sort,
            "clients": org.clients.all(),
            "status_choices": ProjectStatus.choices,
        },
    )


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
