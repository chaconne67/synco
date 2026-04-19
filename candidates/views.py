import json
import uuid

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Prefetch
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from django.db import transaction

from .models import (
    Candidate,
    CandidateComment,
    Category,
    DiscrepancyReport,
    ExtractionLog,
    REASON_CODES,
    SearchSession,
    SearchTurn,
)
from .services.search import build_search_queryset, has_active_filters, parse_and_search
from .services.whisper import transcribe_audio


def _check_rate_limit(
    user_id: int, action: str, max_requests: int, period_seconds: int
) -> bool:
    """Return True if rate limit exceeded.

    Note: Uses Django default cache (LocMemCache). In production with multiple
    workers, use Redis (django-redis) for shared counters across processes.
    """
    key = f"ratelimit:{action}:{user_id}"
    count = cache.get(key)
    if count is None:
        cache.set(key, 1, period_seconds)
        return False
    if count >= max_requests:
        return True
    # Increment without resetting TTL
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, count + 1, period_seconds)
    return False


REVIEW_PAGE_SIZE = 20

STATUS_CHOICES = [
    ("needs_review", "검토 필요"),
    ("auto_confirmed", "자동 확인"),
    ("confirmed", "확인 완료"),
    ("failed", "실패"),
]


def _self_consistency_prefetch() -> Prefetch:
    return Prefetch(
        "discrepancy_reports",
        queryset=DiscrepancyReport.objects.filter(
            report_type=DiscrepancyReport.ReportType.SELF_CONSISTENCY
        ).order_by("-created_at"),
        to_attr="prefetched_self_consistency_reports",
    )


@login_required
def review_list(request):
    status_filter = request.GET.get("status", "needs_review")
    rec_status_filter = request.GET.get("rec_status", "")

    candidates = (
        Candidate.objects.filter(
            validation_status=status_filter,
        )
        .select_related("primary_category")
        .prefetch_related(
            "careers",
            _self_consistency_prefetch(),
        )
    )

    if rec_status_filter:
        candidates = candidates.filter(recommendation_status=rec_status_filter)

    total = candidates.count()
    try:
        page = int(request.GET.get("page", 1))
    except (ValueError, TypeError):
        page = 1
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
            "rec_status_filter": rec_status_filter,
            "status_choices": STATUS_CHOICES,
        },
    )


@login_required
def review_detail(request, pk):
    candidate = get_object_or_404(
        Candidate.objects.select_related(
            "primary_category", "current_resume"
        ).prefetch_related(
            "careers",
            _self_consistency_prefetch(),
        ),
        pk=pk,
    )

    primary_resume = (
        candidate.current_resume
        or candidate.resumes.filter(is_primary=True).first()
        or candidate.resumes.first()
    )
    careers = candidate.careers.all()
    educations = candidate.educations.all()
    certifications = candidate.certifications.all()
    language_skills = candidate.language_skills.all()
    logs = candidate.extraction_logs.all()[:10]

    # Compute field confidences (same as candidate_detail)
    from data_extraction.services.validation import (
        compute_field_confidences,
        compute_overall_confidence,
    )

    extracted_snapshot = {
        "name": candidate.name,
        "birth_year": candidate.birth_year,
        "email": candidate.email,
        "phone": candidate.phone,
        "address": candidate.address,
        "current_company": candidate.current_company,
        "current_position": candidate.current_position,
        "total_experience_years": candidate.total_experience_years,
        "summary": candidate.summary,
        "careers": [{"start_date": c.start_date} for c in careers],
        "educations": [{"institution": e.institution} for e in educations],
        "skills": candidate.skills or [],
        "certifications": [{"name": c.name} for c in certifications],
        "language_skills": [{"language": ls.language} for ls in language_skills],
    }
    field_scores, category_scores = compute_field_confidences(extracted_snapshot, {})
    fc = field_scores
    live_score, _ = compute_overall_confidence(category_scores, [], field_scores)

    # New model fields context (same as candidate_detail)
    from candidates.services.etc_normalizer import build_etc_context

    etc_ctx = build_etc_context(candidate)
    extra_context = {
        "salary_detail": candidate.salary_detail or {},
        "military_service": candidate.military_service or {},
        "self_introduction": candidate.self_introduction or "",
        "family_info": candidate.family_info or {},
        **etc_ctx,
    }

    comments = candidate.comments.select_related("author").all()

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
            "fc": fc,
            "category_scores": category_scores,
            "live_score": live_score,
            "comments": comments,
            "reason_codes": REASON_CODES,
            **extra_context,
        },
    )


@login_required
def review_confirm(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    candidate = get_object_or_404(
        Candidate.objects.select_related("current_resume"),
        pk=pk,
    )
    candidate.validation_status = Candidate.ValidationStatus.CONFIRMED
    candidate.save(update_fields=["validation_status", "updated_at"])

    ExtractionLog.objects.create(
        candidate=candidate,
        resume=candidate.current_resume,
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

    candidate = get_object_or_404(
        Candidate.objects.select_related("current_resume"),
        pk=pk,
    )
    candidate.validation_status = Candidate.ValidationStatus.FAILED
    candidate.save(update_fields=["validation_status", "updated_at"])

    reason = request.POST.get("reason", "")
    ExtractionLog.objects.create(
        candidate=candidate,
        resume=candidate.current_resume,
        action=ExtractionLog.Action.HUMAN_REJECT,
        note=reason,
    )

    return HttpResponse(
        status=204,
        headers={"HX-Redirect": "/candidates/review/"},
    )


@login_required
def comment_create(request, pk):
    """Create a comment with recommendation status update."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    candidate = get_object_or_404(Candidate, pk=pk)

    recommendation_status = request.POST.get("recommendation_status", "")
    reason_codes = request.POST.getlist("reason_codes")
    content = request.POST.get("content", "").strip()
    input_method = request.POST.get("input_method", "text")

    if recommendation_status not in dict(Candidate.RecommendationStatus.choices):
        recommendation_status = Candidate.RecommendationStatus.PENDING

    with transaction.atomic():
        CandidateComment.objects.create(
            candidate=candidate,
            author=request.user,
            recommendation_status=recommendation_status,
            reason_codes=reason_codes,
            content=content,
            input_method=input_method,
        )
        candidate.recommendation_status = recommendation_status
        candidate.save(update_fields=["recommendation_status", "updated_at"])

    comments = candidate.comments.select_related("author").all()
    return render(
        request,
        "candidates/partials/_comment_response.html",
        {
            "candidate": candidate,
            "comments": comments,
            "reason_codes": REASON_CODES,
        },
    )


# -- Search views (Phase 2) ---------------------------------------------------

SEARCH_PAGE_SIZE = 20


@login_required
def candidate_list(request):
    """Main search page: candidate list + category tabs + floating chatbot."""
    category_filter = request.GET.get("category")
    rec_status_filter = request.GET.get("rec_status", "")
    try:
        page = int(request.GET.get("page", 1))
    except (ValueError, TypeError):
        page = 1

    categories = Category.objects.order_by("-candidate_count", "name")
    total_candidates = Candidate.objects.count()

    # Get session for search state
    session_id = request.GET.get("session_id")
    session = None
    filters = {}
    if session_id:
        try:
            uuid.UUID(session_id)
        except (ValueError, AttributeError):
            session_id = None
        if session_id:
            session = SearchSession.objects.filter(
                pk=session_id, user=request.user, is_active=True
            ).first()
        if session:
            filters = dict(session.current_filters)  # copy

    # If category tab clicked, use simple category filter
    if category_filter:
        qs = (
            Candidate.objects.select_related("primary_category")
            .prefetch_related(
                "educations",
                "careers",
                "categories",
                _self_consistency_prefetch(),
            )
            .filter(categories__name=category_filter)
            .distinct()
            .order_by("-updated_at")
        )
        # Apply recommendation_status filter (GET param or session)
        if rec_status_filter:
            qs = qs.filter(recommendation_status=rec_status_filter)
        elif session and has_active_filters(filters):
            rec_statuses = filters.get("recommendation_status", [])
            if rec_statuses:
                qs = qs.filter(recommendation_status__in=rec_statuses)
        total = qs.count()
        offset = (page - 1) * SEARCH_PAGE_SIZE
        page_candidates = qs[offset : offset + SEARCH_PAGE_SIZE]
        has_more = qs[
            offset + SEARCH_PAGE_SIZE : offset + SEARCH_PAGE_SIZE + 1
        ].exists()
    elif session and has_active_filters(filters):
        qs = build_search_queryset(filters)
        total = qs.count()
        offset = (page - 1) * SEARCH_PAGE_SIZE
        page_candidates = qs[offset : offset + SEARCH_PAGE_SIZE]
        has_more = qs[
            offset + SEARCH_PAGE_SIZE : offset + SEARCH_PAGE_SIZE + 1
        ].exists()
    else:
        qs = (
            Candidate.objects.select_related("primary_category")
            .prefetch_related(
                "educations",
                "careers",
                "categories",
                _self_consistency_prefetch(),
            )
            .order_by("-updated_at")
        )
        if rec_status_filter:
            qs = qs.filter(recommendation_status=rec_status_filter)
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
        if page > 1:
            # Pagination: cards only, no wrapper div (prevents nested padding)
            template = "candidates/partials/candidate_list_page.html"
        elif getattr(request.htmx, "target", None) == "main-content":
            # Back navigation from detail: full search content with header + tabs
            template = "candidates/partials/search_content.html"
        elif getattr(request.htmx, "target", None) == "search-area":
            # Category tab switch: status bar + card list
            template = "candidates/partials/search_area.html"
        else:
            # Default: card list only
            template = "candidates/partials/candidate_list.html"
    else:
        template = "candidates/search.html"

    # Project context mode: ?project=<uuid> sets a target_project for "프로젝트에 추가"
    project_id = request.GET.get("project")
    target_project = None
    if project_id:
        try:
            project_uuid = uuid.UUID(project_id)
        except (ValueError, AttributeError):
            project_uuid = None
        if project_uuid:
            from projects.models import Project
            from accounts.helpers import _get_org

            try:
                org = _get_org(request)
            except Exception:
                org = None
            if org:
                target_project = Project.objects.filter(
                    pk=project_uuid, organization=org
                ).first()

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
            "rec_status_filter": rec_status_filter,
            "target_project": target_project,
            "total_candidates": total_candidates,
        },
    )


@login_required
def candidate_create(request):
    """Render Add Candidate form (GET) or create (POST)."""
    from candidates.services.candidate_create import create_candidate, find_duplicate

    categories = Category.objects.order_by("name")

    if request.method == "POST":
        data = request.POST
        name = data.get("name", "").strip()
        email = data.get("email", "").strip() or None
        phone = data.get("phone", "").strip() or None

        errors = {}
        if not name:
            errors["name"] = "이름은 필수입니다."
        if not email and not phone:
            errors["contact"] = "이메일 또는 전화번호 중 하나 이상 입력해주세요."

        if errors:
            return render(
                request,
                "candidates/candidate_form.html",
                {"errors": errors, "form_data": data, "categories": categories},
                status=400,
            )

        if not data.get("confirm_duplicate"):
            dup = find_duplicate(email, phone)
            if dup:
                return render(
                    request,
                    "candidates/candidate_form.html",
                    {
                        "duplicate": dup,
                        "form_data": data,
                        "categories": categories,
                    },
                )

        payload = {
            "name": name,
            "email": email or "",
            "phone": phone or "",
            "current_company": data.get("current_company") or "",
            "current_position": data.get("current_position") or "",
            "birth_year": data.get("birth_year") or None,
            "source": data.get("source") or "manual",
        }
        cat_id = data.get("primary_category")
        if cat_id:
            try:
                payload["primary_category"] = Category.objects.get(pk=cat_id)
            except (Category.DoesNotExist, ValueError):
                pass
        candidate = create_candidate(payload, user=request.user)

        resume_file = request.FILES.get("resume_file")
        if resume_file:
            from candidates.services.candidate_create import attach_resume
            from django.contrib import messages
            try:
                attach_resume(candidate, resume_file)
            except ValueError as e:
                messages.error(request, str(e))

        return redirect("candidates:candidate_detail", pk=candidate.pk)

    return render(
        request,
        "candidates/candidate_form.html",
        {"categories": categories, "form_data": {}, "errors": {}},
    )


@login_required
def candidate_detail(request, pk):
    """Candidate detail page."""
    from django.db.models import Prefetch

    from projects.models import Application

    candidate = get_object_or_404(
        Candidate.objects.select_related(
            "primary_category", "current_resume"
        ).prefetch_related(
            "careers",
            _self_consistency_prefetch(),
            Prefetch(
                "applications",
                queryset=Application.objects.select_related("project__client").order_by(
                    "-created_at"
                ),
                to_attr="prefetched_applications",
            ),
        ),
        pk=pk,
    )
    careers = candidate.careers.all()
    educations = candidate.educations.all()
    certifications = candidate.certifications.all()
    language_skills = candidate.language_skills.all()
    primary_resume = (
        candidate.current_resume
        or candidate.resumes.filter(is_primary=True).first()
        or candidate.resumes.first()
    )

    # Compute field confidences in real-time from current candidate data
    from data_extraction.services.validation import (
        compute_field_confidences,
        compute_overall_confidence,
    )

    extracted_snapshot = {
        "name": candidate.name,
        "birth_year": candidate.birth_year,
        "email": candidate.email,
        "phone": candidate.phone,
        "address": candidate.address,
        "current_company": candidate.current_company,
        "current_position": candidate.current_position,
        "total_experience_years": candidate.total_experience_years,
        "summary": candidate.summary,
        "careers": [{"start_date": c.start_date} for c in careers],
        "educations": [{"institution": e.institution} for e in educations],
        "skills": candidate.skills or [],
        "certifications": [{"name": c.name} for c in certifications],
        "language_skills": [{"language": ls.language} for ls in language_skills],
    }
    field_scores, category_scores = compute_field_confidences(extracted_snapshot, {})
    fc = field_scores
    live_score, _ = compute_overall_confidence(category_scores, [], field_scores)

    # Find hallucinated fields from validation diagnosis
    from .models import ValidationDiagnosis

    hallucinated_fields = set()
    diag_qs = ValidationDiagnosis.objects.filter(candidate=candidate)
    if primary_resume:
        diag_qs = diag_qs.filter(resume=primary_resume)
    diag = diag_qs.first()
    if diag and diag.issues:
        for issue in diag.issues:
            if issue.get("type") == "hallucinated":
                hallucinated_fields.add(issue.get("field", ""))

    # New model fields context
    from candidates.services.etc_normalizer import build_etc_context

    etc_ctx = build_etc_context(candidate)
    extra_context = {
        "salary_detail": candidate.salary_detail or {},
        "military_service": candidate.military_service or {},
        "self_introduction": candidate.self_introduction or "",
        "family_info": candidate.family_info or {},
        **etc_ctx,
    }

    comments = candidate.comments.select_related("author").all()

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
            "candidate_applications": candidate.prefetched_applications,
            "careers": careers,
            "educations": educations,
            "certifications": certifications,
            "language_skills": language_skills,
            "primary_resume": primary_resume,
            "fc": fc,
            "category_scores": category_scores,
            "live_score": live_score,
            "hallucinated_fields": hallucinated_fields,
            "comments": comments,
            "reason_codes": REASON_CODES,
            **extra_context,
        },
    )


@login_required
def search_chat(request):
    """Handle text search query from chatbot. Returns JSON."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    if _check_rate_limit(request.user.pk, "search_chat", 10, 60):
        return JsonResponse(
            {"error": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."}, status=429
        )

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "잘못된 요청입니다."}, status=400)

    user_text = body.get("message", "").strip()
    session_id = body.get("session_id")

    input_type = body.get("input_type", "text")
    if input_type not in ("text", "voice"):
        input_type = "text"

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

    # LLM generates structured filters and executes ORM search
    previous_filters = (
        session.current_filters if has_active_filters(session.current_filters) else None
    )
    result = parse_and_search(user_text, previous_filters=previous_filters)

    ai_message = result["ai_message"]
    result_count = result["result_count"]
    filters = result.get("filters") or {}

    # Too many results — guide user to narrow down with the current filter context
    if result_count > 50:
        ai_message += (
            f"\n\n검색 결과가 {result_count}명으로 너무 많습니다. "
            "추가 조건을 말씀해주시면 현재 결과에서 바로 좁혀드리겠습니다. "
            "예: 경력 10년 이상, 서울대 출신, 삼성 경력자 등"
        )

    # Save turn
    turn_number = session.turns.count() + 1
    SearchTurn.objects.create(
        session=session,
        turn_number=turn_number,
        input_type=input_type,
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
        }
    )


@login_required
def voice_transcribe(request):
    """Handle voice audio upload → Whisper transcription. Returns JSON."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    if _check_rate_limit(request.user.pk, "voice_transcribe", 5, 60):
        return JsonResponse(
            {"error": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."}, status=429
        )

    audio = request.FILES.get("audio")
    if not audio:
        return JsonResponse({"error": "오디오 파일이 없습니다."}, status=400)

    if audio.size > 10 * 1024 * 1024:
        return JsonResponse(
            {"error": "오디오 파일이 너무 큽니다. 10MB 이하로 녹음해주세요."},
            status=400,
        )

    try:
        text = transcribe_audio(audio)
        if not text:
            return JsonResponse(
                {"error": "음성이 감지되지 않았습니다. 다시 말씀해주세요."}, status=400
            )
        return JsonResponse({"text": text})
    except RuntimeError as e:
        return JsonResponse({"error": str(e)}, status=500)
    except Exception:
        return JsonResponse({"error": "음성 인식 중 오류가 발생했습니다."}, status=500)
