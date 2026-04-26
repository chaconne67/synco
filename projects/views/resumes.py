"""Resume upload views."""
from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render

from accounts.decorators import level_required
from accounts.services.scope import get_scoped_object_or_404, scope_work_qs
from projects.models import Project, ProjectStatus, ResumeUpload
from projects.services.resume.linker import (
    link_resume_to_candidate as link_resume_to_candidate,
)
from projects.services.resume.transitions import transition_status
from projects.services.resume.uploader import (
    FileValidationError,
    create_upload,
    process_pending_upload as process_pending_upload,
)


@login_required
@level_required(1)
def resume_upload(request, pk):
    """POST: Upload resume files → create ResumeUpload(pending) per file."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

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
@level_required(1)
def resume_process_pending(request, pk):
    """POST: Process all pending uploads for batch. Runs extraction synchronously."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

    batch_id = request.POST.get("batch_id")
    if not batch_id:
        return HttpResponseBadRequest("batch_id required")

    pending = ResumeUpload.objects.filter(
        project=project,
        upload_batch=batch_id,
        status=ResumeUpload.Status.PENDING,
    )
    for upload in pending:
        from projects import views

        views.process_pending_upload(upload)

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
@level_required(1)
def resume_upload_status(request, pk):
    """GET: HTMX polling endpoint for upload status."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

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
@level_required(1)
def resume_link_candidate(request, pk, resume_pk):
    """POST: Link extracted resume to candidate."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    upload = get_object_or_404(
        ResumeUpload.objects.filter(project=project),
        pk=resume_pk,
    )
    force_new = request.POST.get("force_new") == "true"

    try:
        from projects import views

        views.link_resume_to_candidate(upload, user=request.user, force_new=force_new)
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
@level_required(1)
def resume_discard(request, pk, resume_pk):
    """POST: Discard resume upload + delete physical file."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
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
@level_required(1)
def resume_retry(request, pk, resume_pk):
    """POST: Retry failed extraction (max 3 retries)."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    upload = get_object_or_404(
        ResumeUpload.objects.filter(project=project),
        pk=resume_pk,
    )

    if upload.retry_count >= 3:
        return HttpResponseBadRequest("재시도 횟수를 초과했습니다.")

    upload.retry_count += 1
    upload.save(update_fields=["retry_count", "updated_at"])
    transition_status(upload, ResumeUpload.Status.PENDING)
    from projects import views

    views.process_pending_upload(upload)

    return render(
        request,
        "projects/partials/resume_status.html",
        {
            "uploads": [upload],
            "project": project,
        },
    )


@login_required
@level_required(1)
def resume_unassigned(request):
    """GET: list of unassigned resume uploads (project=null)."""
    uploads = ResumeUpload.objects.filter(
        project__isnull=True,
    ).exclude(status=ResumeUpload.Status.DISCARDED)
    projects = scope_work_qs(Project.objects.all(), request.user).exclude(
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
@level_required(1)
def resume_assign_project(request, resume_pk, project_pk):
    """POST: Assign an unassigned resume upload to a project."""
    upload = get_object_or_404(
        ResumeUpload.objects.filter(project__isnull=True),
        pk=resume_pk,
    )
    project = get_scoped_object_or_404(Project, request.user, pk=project_pk)

    upload.project = project
    upload.save(update_fields=["project", "updated_at"])

    uploads = ResumeUpload.objects.filter(
        project__isnull=True,
    ).exclude(status=ResumeUpload.Status.DISCARDED)

    return render(
        request,
        "projects/resume_unassigned.html",
        {
            "uploads": uploads,
        },
    )
