"""JD analysis and matching views."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from accounts.decorators import level_required
from accounts.services.scope import get_scoped_object_or_404
from projects.models import Project

@login_required
@level_required(1)
@require_http_methods(["POST"])
def analyze_jd(request, pk):
    """JD 분석 트리거. 파일 업로드 시 텍스트 추출 후 AI 분석."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

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
@level_required(1)
def jd_results(request, pk):
    """JD 분석 결과 표시 (HTMX partial)."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

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
@level_required(1)
@require_http_methods(["POST"])
def start_search_session(request, pk):
    """프로젝트 requirements → SearchSession 생성 → 후보자 검색으로 redirect."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

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
@level_required(1)
def jd_matching_results(request, pk):
    """프로젝트 상세 내 후보자 매칭 결과 목록."""
    project = get_scoped_object_or_404(Project, request.user, pk=pk)

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
