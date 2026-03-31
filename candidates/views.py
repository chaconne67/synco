import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, render

from .models import Candidate, Category, ExtractionLog, SearchSession, SearchTurn
from .services.search import hybrid_search, parse_search_query
from .services.whisper import transcribe_audio

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


# -- Search views (Phase 2) ---------------------------------------------------

SEARCH_PAGE_SIZE = 20


@login_required
def candidate_list(request):
    """Main search page: candidate list + category tabs + floating chatbot."""
    category_filter = request.GET.get("category")
    page = int(request.GET.get("page", 1))

    categories = Category.objects.all()

    # Get session for search state
    session_id = request.GET.get("session_id")
    session = None
    filters = {}
    if session_id:
        session = SearchSession.objects.filter(
            pk=session_id, user=request.user, is_active=True
        ).first()
        if session:
            filters = dict(session.current_filters)  # copy

    # If category tab clicked, override filter
    if category_filter:
        filters["category"] = category_filter

    # Execute search
    if filters:
        semantic_query = filters.pop("_semantic_query", None)
        candidates_list = hybrid_search(
            filters, semantic_query=semantic_query, limit=200
        )
        total = len(candidates_list)
        offset = (page - 1) * SEARCH_PAGE_SIZE
        page_candidates = candidates_list[offset : offset + SEARCH_PAGE_SIZE]
        has_more = len(candidates_list) > offset + SEARCH_PAGE_SIZE
    else:
        qs = Candidate.objects.select_related("primary_category").order_by(
            "-updated_at"
        )
        total = qs.count()
        offset = (page - 1) * SEARCH_PAGE_SIZE
        page_candidates = qs[offset : offset + SEARCH_PAGE_SIZE]
        has_more = qs[
            offset + SEARCH_PAGE_SIZE : offset + SEARCH_PAGE_SIZE + 1
        ].exists()

    # Get last search summary for status bar
    last_turn = None
    if session:
        last_turn = session.turns.order_by("-turn_number").first()

    # Template selection
    if request.htmx:
        template = "candidates/partials/candidate_list.html"
    else:
        template = "candidates/search.html"

    return render(
        request,
        template,
        {
            "candidates": page_candidates,
            "categories": categories,
            "active_category": category_filter
            or (filters.get("category") if filters else None),
            "total": total,
            "page": page,
            "has_more": has_more,
            "session": session,
            "last_turn": last_turn,
        },
    )


@login_required
def candidate_detail(request, pk):
    """Candidate detail page."""
    candidate = get_object_or_404(
        Candidate.objects.select_related("primary_category"),
        pk=pk,
    )
    careers = candidate.careers.all()
    educations = candidate.educations.all()
    certifications = candidate.certifications.all()
    language_skills = candidate.language_skills.all()
    primary_resume = candidate.resumes.filter(is_primary=True).first()

    template = (
        "candidates/partials/candidate_detail_content.html"
        if request.htmx
        else "candidates/detail.html"
    )
    return render(
        request,
        template,
        {
            "candidate": candidate,
            "careers": careers,
            "educations": educations,
            "certifications": certifications,
            "language_skills": language_skills,
            "primary_resume": primary_resume,
        },
    )


@login_required
def search_chat(request):
    """Handle text search query from chatbot. Returns JSON."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    body = json.loads(request.body)
    user_text = body.get("message", "").strip()
    session_id = body.get("session_id")

    if not user_text:
        return JsonResponse({"error": "메시지를 입력해주세요."}, status=400)

    # Get or create session
    session = None
    if session_id:
        session = SearchSession.objects.filter(
            pk=session_id, user=request.user, is_active=True
        ).first()

    if not session:
        SearchSession.objects.filter(user=request.user, is_active=True).update(
            is_active=False
        )
        session = SearchSession.objects.create(user=request.user)

    # Parse query via LLM
    parsed = parse_search_query(user_text, session.current_filters)

    # Apply action
    action = parsed.get("action", "new")
    new_filters = parsed.get("filters", {})

    if action == "new":
        filters = new_filters
    elif action == "narrow":
        filters = {**session.current_filters, **new_filters}
    else:
        filters = new_filters

    # Execute search
    semantic_query = parsed.get("semantic_query")
    results = hybrid_search(filters, semantic_query=semantic_query)
    result_count = len(results)

    ai_message = parsed.get("ai_message", "")
    if not ai_message:
        ai_message = f"{result_count}명의 후보자를 찾았습니다."

    # Save turn
    turn_number = session.turns.count() + 1
    SearchTurn.objects.create(
        session=session,
        turn_number=turn_number,
        input_type="text",
        user_text=user_text,
        ai_response=ai_message,
        filters_applied=filters,
        result_count=result_count,
    )

    session.current_filters = filters
    session.save(update_fields=["current_filters", "updated_at"])

    return JsonResponse(
        {
            "session_id": str(session.pk),
            "ai_message": ai_message,
            "result_count": result_count,
            "filters": filters,
            "action": action,
        }
    )


@login_required
def voice_transcribe(request):
    """Handle voice audio upload → Whisper transcription. Returns JSON."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    audio = request.FILES.get("audio")
    if not audio:
        return JsonResponse({"error": "오디오 파일이 없습니다."}, status=400)

    try:
        text = transcribe_audio(audio)
        return JsonResponse({"text": text})
    except RuntimeError as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def chat_history(request):
    """Return chat messages for a session as HTML partial."""
    session_id = request.GET.get("session_id")
    turns = []
    if session_id:
        session = SearchSession.objects.filter(pk=session_id, user=request.user).first()
        if session:
            turns = session.turns.order_by("turn_number")

    return render(request, "candidates/partials/chat_messages.html", {"turns": turns})
