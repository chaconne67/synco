"""Posting management views."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from accounts.decorators import level_required
from accounts.services.scope import get_scoped_object_or_404
from projects.forms import PostingEditForm, PostingSiteForm
from projects.models import PostingSite, Project
from projects.services import posting as posting_service


@login_required
@level_required(1)
@require_http_methods(["POST"])
def posting_generate(request, pk):
    """AI 공지 초안 생성. overwrite=true 필요 시 기존 내용 보호."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

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
@level_required(1)
def posting_edit(request, pk):
    """공지 내용 편집. GET=폼, POST=저장."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

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
@level_required(1)
def posting_download(request, pk):
    """공지 파일 다운로드 (.txt)."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

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
@level_required(1)
def posting_sites(request, pk):
    """포스팅 사이트 목록 (HTMX partial)."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

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
@level_required(1)
@require_http_methods(["GET", "POST"])
def posting_site_add(request, pk):
    """포스팅 사이트 추가."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

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
@level_required(1)
@require_http_methods(["GET", "POST"])
def posting_site_update(request, pk, site_pk):
    """포스팅 사이트 수정."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
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
@level_required(1)
@require_http_methods(["POST"])
def posting_site_delete(request, pk, site_pk):
    """포스팅 사이트 비활성화 (소프트 삭제)."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)
    site = get_object_or_404(PostingSite, pk=site_pk, project=project)

    site.is_active = False
    site.save(update_fields=["is_active", "updated_at"])

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "postingSiteChanged"},
    )
