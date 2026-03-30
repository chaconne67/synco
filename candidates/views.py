from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render

from .models import Candidate, ExtractionLog

REVIEW_PAGE_SIZE = 20

STATUS_CHOICES = [
    ("needs_review", "검토 필요"),
    ("auto_confirmed", "자동 확인"),
    ("confirmed", "확인 완료"),
    ("failed", "실패"),
]


@login_required
def review_list(request):
    status_filter = request.GET.get("status", "needs_review")

    candidates = Candidate.objects.filter(
        validation_status=status_filter,
    ).select_related("primary_category")

    total = candidates.count()
    page = int(request.GET.get("page", 1))
    offset = (page - 1) * REVIEW_PAGE_SIZE
    page_candidates = candidates[offset : offset + REVIEW_PAGE_SIZE]
    has_more = candidates[
        offset + REVIEW_PAGE_SIZE : offset + REVIEW_PAGE_SIZE + 1
    ].exists()

    template = (
        "candidates/partials/review_list_content.html"
        if request.htmx
        else "candidates/review_list.html"
    )
    return render(
        request,
        template,
        {
            "candidates": page_candidates,
            "page": page,
            "has_more": has_more,
            "total": total,
            "status_filter": status_filter,
            "status_choices": STATUS_CHOICES,
        },
    )


@login_required
def review_detail(request, pk):
    candidate = get_object_or_404(Candidate, pk=pk)

    primary_resume = candidate.resumes.filter(is_primary=True).first()
    careers = candidate.careers.all()
    educations = candidate.educations.all()
    certifications = candidate.certifications.all()
    language_skills = candidate.language_skills.all()
    logs = candidate.extraction_logs.all()[:10]

    template = (
        "candidates/partials/review_detail_content.html"
        if request.htmx
        else "candidates/review_detail.html"
    )
    return render(
        request,
        template,
        {
            "candidate": candidate,
            "primary_resume": primary_resume,
            "careers": careers,
            "educations": educations,
            "certifications": certifications,
            "language_skills": language_skills,
            "logs": logs,
        },
    )


@login_required
def review_confirm(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    candidate = get_object_or_404(Candidate, pk=pk)
    candidate.validation_status = Candidate.ValidationStatus.CONFIRMED
    candidate.save(update_fields=["validation_status", "updated_at"])

    ExtractionLog.objects.create(
        candidate=candidate,
        action=ExtractionLog.Action.HUMAN_CONFIRM,
        note="사람이 검토 확인",
    )

    return HttpResponse(
        status=204,
        headers={"HX-Redirect": "/candidates/review/"},
    )


@login_required
def review_reject(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    candidate = get_object_or_404(Candidate, pk=pk)
    candidate.validation_status = Candidate.ValidationStatus.FAILED
    candidate.save(update_fields=["validation_status", "updated_at"])

    reason = request.POST.get("reason", "")
    ExtractionLog.objects.create(
        candidate=candidate,
        action=ExtractionLog.Action.HUMAN_REJECT,
        note=reason,
    )

    return HttpResponse(
        status=204,
        headers={"HX-Redirect": "/candidates/review/"},
    )
