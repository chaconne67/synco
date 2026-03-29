import threading

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from contacts.models import Contact

from .models import AnalysisJob, Brief, FortunateInsight, Match, RelationshipAnalysis


@login_required
def brief_detail(request, contact_pk):
    contact = get_object_or_404(Contact, pk=contact_pk, fc=request.user)
    brief = contact.briefs.first()

    template = "intelligence/partials/brief_detail_content.html" if request.htmx else "intelligence/brief_detail.html"
    return render(request, template, {
        "contact": contact,
        "brief": brief,
    })


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

    return render(request, "intelligence/partials/brief_card.html", {
        "contact": contact,
        "brief": brief,
    })


MATCH_PAGE_SIZE = 20


@login_required
def match_list(request):
    matches = Match.objects.filter(fc=request.user).select_related(
        "contact_a", "contact_b"
    )

    page = int(request.GET.get("page", 1))
    offset = (page - 1) * MATCH_PAGE_SIZE
    page_matches = matches[offset : offset + MATCH_PAGE_SIZE]
    has_more = matches[offset + MATCH_PAGE_SIZE : offset + MATCH_PAGE_SIZE + 1].exists()

    template = "intelligence/partials/match_list_content.html" if request.htmx else "intelligence/match_list.html"
    return render(request, template, {
        "matches": page_matches,
        "page": page,
        "has_more": has_more,
    })


@login_required
def match_detail(request, pk):
    match = get_object_or_404(Match, pk=pk, fc=request.user)

    template = "intelligence/partials/match_detail_content.html" if request.htmx else "intelligence/match_detail.html"
    return render(request, template, {"match": match})


@login_required
def contact_report(request, contact_pk):
    """리포트 보기 모달 — 기본 정보 즉시 렌더, AI 분석은 lazy-load."""
    contact = get_object_or_404(Contact, pk=contact_pk, fc=request.user)
    analysis = RelationshipAnalysis.objects.filter(contact=contact, fc=request.user).first()
    brief = contact.briefs.first()
    interactions = contact.interactions.all()[:10]
    meetings = contact.meetings.filter(status="completed").order_by("-scheduled_at")[:5]

    # Determine if AI analysis section needs lazy-load
    needs_analysis = analysis is None or _is_stale(analysis, contact)

    return render(request, "intelligence/partials/contact_report_modal.html", {
        "contact": contact,
        "analysis": analysis,
        "brief": brief,
        "interactions": interactions,
        "meetings": meetings,
        "needs_analysis": needs_analysis,
    })


def _is_stale(analysis, contact) -> bool:
    """Check if analysis is stale (>24h or new interactions since)."""
    now = timezone.now()
    if (now - analysis.created_at).total_seconds() > 86400:
        return True
    latest = contact.interactions.order_by("-created_at").values_list("created_at", flat=True).first()
    if latest and latest > analysis.created_at:
        return True
    return False


@login_required
def contact_report_analysis(request, contact_pk):
    """HTMX lazy-load: AI analysis section for report modal."""
    contact = get_object_or_404(Contact, pk=contact_pk, fc=request.user)

    from intelligence.services import ensure_deep_analysis

    analysis = ensure_deep_analysis(contact)

    return render(request, "intelligence/partials/report_analysis_section.html", {
        "analysis": analysis,
    })


@login_required
def analysis_trigger(request):
    """관계 분석 실행 트리거 — 백그라운드 스레드."""
    if request.method != "POST":
        return HttpResponse(status=405)

    contacts = Contact.objects.filter(fc=request.user)
    total = contacts.count()
    if total == 0:
        return HttpResponse('<p class="text-sm text-gray-500">분석할 연락처가 없습니다.</p>')

    job = AnalysisJob.objects.create(
        fc=request.user,
        total_contacts=total,
        started_at=timezone.now(),
        status=AnalysisJob.Status.RUNNING,
    )

    def _run_analysis(job_pk, user_pk):
        import django
        django.setup()
        from intelligence.services import analyze_contact_relationship, calculate_relationship_score
        from contacts.models import Contact as BgContact

        try:
            job = AnalysisJob.objects.get(pk=job_pk)
            contacts = BgContact.objects.filter(fc_id=user_pk)
            for contact in contacts:
                # AI analysis if contact has interactions, else pure Python
                has_data = contact.interactions.exists()
                if has_data:
                    try:
                        analyze_contact_relationship(contact)
                    except Exception:
                        calculate_relationship_score(contact)
                else:
                    calculate_relationship_score(contact)
                job.processed_contacts += 1
                job.save(update_fields=["processed_contacts"])
            job.status = AnalysisJob.Status.COMPLETED
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "completed_at"])
        except Exception as e:
            try:
                job = AnalysisJob.objects.get(pk=job_pk)
                job.status = AnalysisJob.Status.FAILED
                job.error_message = str(e)
                job.save(update_fields=["status", "error_message"])
            except Exception:
                pass

    thread = threading.Thread(
        target=_run_analysis,
        args=(job.pk, request.user.pk),
        daemon=True,
    )
    thread.start()

    return render(request, "intelligence/partials/analysis_progress.html", {"job": job})


@login_required
def analysis_status(request, job_pk):
    """분석 진행 상태 폴링."""
    job = get_object_or_404(AnalysisJob, pk=job_pk, fc=request.user)

    if job.status in (AnalysisJob.Status.COMPLETED, AnalysisJob.Status.FAILED):
        return render(request, "intelligence/partials/analysis_complete.html", {"job": job})

    return render(request, "intelligence/partials/analysis_progress.html", {"job": job})


@login_required
def dashboard_briefing(request):
    """Lazy-load AI briefing for dashboard Section 3."""
    from datetime import timedelta

    from meetings.models import Meeting

    from intelligence.services import generate_dashboard_briefing

    today = timezone.localdate()

    # Check for cached briefing (generated today)
    latest_brief = Brief.objects.filter(
        fc=request.user,
        generated_at__date=today,
    ).select_related("contact").first()

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

    return render(request, "accounts/partials/dashboard/section_briefing.html", {
        "latest_brief": latest_brief,
    })


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
            sentiment_counts[sentiment] = batch_interactions.filter(sentiment=sentiment).count()
        tasks_detected = Task.objects.filter(source_interactions__import_batch=batch).distinct().count()

    return render(request, "intelligence/partials/import_analysis_status.html", {
        "batch": batch,
        "is_done": is_done,
        "timed_out": timed_out,
        "sentiment_counts": sentiment_counts,
        "tasks_detected": tasks_detected,
    })


@login_required
def dismiss_insight(request, pk):
    """Feel Lucky 항목 닫기."""
    if request.method != "POST":
        return HttpResponse(status=405)
    insight = get_object_or_404(FortunateInsight, pk=pk, fc=request.user)
    insight.is_dismissed = True
    insight.save(update_fields=["is_dismissed"])
    return HttpResponse("")
