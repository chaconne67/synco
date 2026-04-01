from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from contacts.models import Contact

from .models import Brief, FortunateInsight, Match, RelationshipAnalysis


@login_required
def brief_detail(request, contact_pk):
    contact = get_object_or_404(Contact, pk=contact_pk, fc=request.user)
    brief = contact.briefs.first()

    template = (
        "intelligence/partials/brief_detail_content.html"
        if request.htmx
        else "intelligence/brief_detail.html"
    )
    return render(
        request,
        template,
        {
            "contact": contact,
            "brief": brief,
        },
    )


@login_required
def brief_generate(request, contact_pk):
    contact = get_object_or_404(Contact, pk=contact_pk, fc=request.user)

    # TODO: integrate real AI pipeline
    brief = Brief.objects.create(
        contact=contact,
        fc=request.user,
        company_analysis=f"{contact.company_name} 기업 분석이 준비 중입니다.",
        action_suggestion="AI 브리핑 기능이 곧 활성화됩니다.",
        insights={},
    )

    # If called from brief_detail page (hx-target=#main-content), return full detail
    if request.htmx and request.htmx.target == "main-content":
        return render(
            request,
            "intelligence/partials/brief_detail_content.html",
            {
                "contact": contact,
                "brief": brief,
            },
        )

    # If called from contact detail (#ai-brief-slot), return card
    return render(
        request,
        "intelligence/partials/brief_card.html",
        {
            "contact": contact,
            "brief": brief,
        },
    )


MATCH_PAGE_SIZE = 20


@login_required
def match_list(request):
    matches = Match.objects.filter(fc=request.user).select_related(
        "contact_a", "contact_b"
    )

    try:
        page = int(request.GET.get("page", 1))
    except (ValueError, TypeError):
        page = 1
    offset = (page - 1) * MATCH_PAGE_SIZE
    page_matches = matches[offset : offset + MATCH_PAGE_SIZE]
    has_more = matches[offset + MATCH_PAGE_SIZE : offset + MATCH_PAGE_SIZE + 1].exists()

    template = (
        "intelligence/partials/match_list_content.html"
        if request.htmx
        else "intelligence/match_list.html"
    )
    return render(
        request,
        template,
        {
            "matches": page_matches,
            "page": page,
            "has_more": has_more,
        },
    )


@login_required
def match_detail(request, pk):
    match = get_object_or_404(Match, pk=pk, fc=request.user)

    template = (
        "intelligence/partials/match_detail_content.html"
        if request.htmx
        else "intelligence/match_detail.html"
    )
    return render(request, template, {"match": match})


@login_required
def contact_report(request, contact_pk):
    """리포트 보기 모달 — 기본 정보 즉시 렌더, AI 분석은 lazy-load."""
    contact = get_object_or_404(Contact, pk=contact_pk, fc=request.user)
    analysis = RelationshipAnalysis.objects.filter(
        contact=contact, fc=request.user
    ).first()
    brief = contact.briefs.first()
    interactions = contact.interactions.all()[:10]
    meetings = contact.meetings.filter(status="completed").order_by("-scheduled_at")[:5]

    # Determine if AI analysis section needs lazy-load
    needs_analysis = analysis is None or _is_stale(analysis, contact)

    return render(
        request,
        "intelligence/partials/contact_report_modal.html",
        {
            "contact": contact,
            "analysis": analysis,
            "brief": brief,
            "interactions": interactions,
            "meetings": meetings,
            "needs_analysis": needs_analysis,
        },
    )


def _is_stale(analysis, contact) -> bool:
    """Check if analysis is stale (>24h or new interactions since)."""
    now = timezone.now()
    if (now - analysis.created_at).total_seconds() > 86400:
        return True
    latest = (
        contact.interactions.order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    if latest and latest > analysis.created_at:
        return True
    return False


@login_required
def contact_report_analysis(request, contact_pk):
    """HTMX lazy-load: AI analysis section for report modal."""
    contact = get_object_or_404(Contact, pk=contact_pk, fc=request.user)

    from intelligence.services import ensure_deep_analysis

    analysis = ensure_deep_analysis(contact)

    return render(
        request,
        "intelligence/partials/report_analysis_section.html",
        {
            "analysis": analysis,
        },
    )

    # analysis_trigger and analysis_status removed in Phase 6.
    # Replaced by automatic embedding-based analysis pipeline.


@login_required
def dashboard_briefing(request):
    """Lazy-load AI briefing for dashboard Section 3."""
    from datetime import timedelta

    from meetings.models import Meeting

    from intelligence.services import generate_dashboard_briefing

    today = timezone.localdate()

    # Check for cached briefing (generated today)
    latest_brief = (
        Brief.objects.filter(
            fc=request.user,
            generated_at__date=today,
        )
        .select_related("contact")
        .first()
    )

    if not latest_brief:
        # Generate new briefing
        meetings = Meeting.objects.filter(
            fc=request.user,
            scheduled_at__date__range=(today, today + timedelta(days=7)),
            status=Meeting.Status.SCHEDULED,
        ).select_related("contact")

        attention = Contact.objects.filter(
            fc=request.user,
            relationship_tier__in=["red", "yellow"],
        ).order_by("relationship_score")[:5]

        latest_brief = generate_dashboard_briefing(request.user, meetings, attention)

    return render(
        request,
        "accounts/partials/dashboard/section_briefing.html",
        {
            "latest_brief": latest_brief,
        },
    )


@login_required
def import_analysis_status(request, batch_id):
    """HTMX polling endpoint: ImportBatch analysis progress.

    Returns partial HTML with step-by-step status.
    Polling stops when is_complete or error or 5min timeout.
    """
    from intelligence.models import ImportBatch

    batch = get_object_or_404(ImportBatch, pk=batch_id, fc=request.user)

    # Timeout check (5 minutes)
    elapsed = (timezone.now() - batch.created_at).total_seconds()
    timed_out = elapsed > 300

    is_done = batch.is_complete or bool(batch.error_message) or timed_out

    # Gather stats for this batch
    sentiment_counts = {}
    tasks_detected = 0
    if batch.is_complete or timed_out:
        from contacts.models import Interaction, Task

        batch_interactions = Interaction.objects.filter(import_batch=batch)
        for sentiment in ["positive", "neutral", "negative"]:
            sentiment_counts[sentiment] = batch_interactions.filter(
                sentiment=sentiment
            ).count()
        tasks_detected = (
            Task.objects.filter(source_interactions__import_batch=batch)
            .distinct()
            .count()
        )

    return render(
        request,
        "intelligence/partials/import_analysis_status.html",
        {
            "batch": batch,
            "is_done": is_done,
            "timed_out": timed_out,
            "sentiment_counts": sentiment_counts,
            "tasks_detected": tasks_detected,
        },
    )


@login_required
def dismiss_insight(request, pk):
    """Feel Lucky 항목 닫기."""
    if request.method != "POST":
        return HttpResponse(status=405)
    insight = get_object_or_404(FortunateInsight, pk=pk, fc=request.user)
    insight.is_dismissed = True
    insight.save(update_fields=["is_dismissed"])
    return HttpResponse("")
