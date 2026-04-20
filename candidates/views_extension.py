import json
import functools
from datetime import date

from django.db import transaction, IntegrityError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Candidate, Career, Education, ExtractionLog
from .services.candidate_identity import (
    identify_candidate_from_extension,
    normalize_phone_for_matching,
)
from .serializers_extension import (
    validate_profile_data,
    normalize_url,
    normalize_company,
    parse_int_or_none,
    MAX_PAYLOAD_SIZE,
)


def extension_login_required(view_func):
    """Extension API용 인증 데코레이터. 미인증 시 JSON 401, level=0 PENDING 시 JSON 403 반환."""

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return JsonResponse(
                {"status": "error", "errors": ["Authentication required"]},
                status=401,
            )
        if not user.is_superuser and user.level < 1:
            return JsonResponse(
                {"status": "error", "errors": ["pending_approval"]},
                status=403,
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def _json_error(errors, status=400):
    return JsonResponse({"status": "error", "errors": errors}, status=status)


def _parse_json_body(request):
    """JSON body 파싱. 실패 시 (None, JsonResponse) 반환."""
    if len(request.body) > MAX_PAYLOAD_SIZE:
        return None, _json_error(["Payload too large"], 413)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            return None, _json_error(["Expected JSON object"], 400)
        return data, None
    except (json.JSONDecodeError, ValueError):
        return None, _json_error(["Invalid JSON"], 400)


@csrf_exempt
@extension_login_required
def extension_auth_status(request):
    """GET: 인증 상태 + 사용자/조직 정보."""
    if request.method != "GET":
        return _json_error(["Method not allowed"], 405)

    return JsonResponse(
        {
            "status": "success",
            "data": {
                "authenticated": True,
                "user": request.user.get_full_name() or request.user.username,
                "organization": None,
            },
        }
    )


@csrf_exempt
@extension_login_required
def extension_stats(request):
    """GET: org 내 총 후보자 수."""
    if request.method != "GET":
        return _json_error(["Method not allowed"], 405)

    count = Candidate.objects.count()
    return JsonResponse({"status": "success", "data": {"total_candidates": count}})


@csrf_exempt
@extension_login_required
def extension_check_duplicate(request):
    """POST: 중복 체크 (lightweight, diff 미포함)."""
    if request.method != "POST":
        return _json_error(["Method not allowed"], 405)

    data, err = _parse_json_body(request)
    if err:
        return err

    result = identify_candidate_from_extension(data)

    if result.match_type == "exact":
        return JsonResponse(
            {
                "status": "duplicate_found",
                "data": {
                    "candidate_id": str(result.candidate.id),
                    "name": result.candidate.name,
                    "company": result.candidate.current_company,
                    "position": result.candidate.current_position,
                    "match_reason": result.match_reason,
                    "synco_url": f"/candidates/{result.candidate.id}/",
                    "updated_at": result.candidate.updated_at.isoformat(),
                },
            }
        )
    elif result.match_type == "possible":
        return JsonResponse(
            {
                "status": "possible_match",
                "data": {
                    "possible_matches": [
                        {
                            "candidate_id": str(c.id),
                            "name": c.name,
                            "company": c.current_company,
                            "position": c.current_position,
                            "match_reason": "name_company",
                            "synco_url": f"/candidates/{c.id}/",
                        }
                        for c in result.possible_matches
                    ]
                },
            }
        )
    else:
        return JsonResponse({"status": "success", "data": {"exists": False}})


@csrf_exempt
@extension_login_required
def extension_search(request):
    """GET: 키워드 검색. org 스코핑, 페이지네이션."""
    if request.method != "GET":
        return _json_error(["Method not allowed"], 405)

    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return _json_error(["Query must be at least 2 characters"], 400)

    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    page_size = 20
    offset = (page - 1) * page_size

    from django.db.models import Q

    qs = Candidate.objects.filter(
        Q(name__icontains=q)
        | Q(current_company__icontains=q)
        | Q(current_position__icontains=q)
        | Q(email__icontains=q)
    ).order_by("-updated_at")

    total = qs.count()
    candidates = qs[offset : offset + page_size]

    return JsonResponse(
        {
            "status": "success",
            "data": {
                "results": [
                    {
                        "candidate_id": str(c.id),
                        "name": c.name,
                        "company": c.current_company,
                        "position": c.current_position,
                        "synco_url": f"/candidates/{c.id}/",
                    }
                    for c in candidates
                ],
                "total": total,
                "page": page,
                "page_size": page_size,
            },
        }
    )


@csrf_exempt
@extension_login_required
def extension_save_profile(request):
    """POST: 프로필 저장/업데이트."""
    if request.method != "POST":
        return _json_error(["Method not allowed"], 405)

    # DB-backed rate limit: 100/day per user
    today = date.today()
    today_count = ExtractionLog.objects.filter(
        action=ExtractionLog.Action.EXTENSION_SAVE,
        actor=request.user,
        created_at__date=today,
    ).count()
    if today_count >= 100:
        return _json_error(["Daily save limit exceeded (100/day)"], 429)

    data, err = _parse_json_body(request)
    if err:
        return err

    cleaned, errors = validate_profile_data(data)
    if errors:
        return _json_error(errors, 400)

    # Update mode
    if cleaned["update_mode"]:
        return _handle_update(request, cleaned)

    # New save: check duplicates within transaction
    with transaction.atomic():
        identity = identify_candidate_from_extension(cleaned)

        if identity.match_type == "exact":
            diff = _build_diff(identity.candidate, cleaned)
            return JsonResponse(
                {
                    "status": "duplicate_found",
                    "data": {
                        "candidate_id": str(identity.candidate.id),
                        "name": identity.candidate.name,
                        "match_reason": identity.match_reason,
                        "synco_url": f"/candidates/{identity.candidate.id}/",
                        "diff": diff,
                    },
                },
                status=409,
            )

        if identity.match_type == "possible":
            return JsonResponse(
                {
                    "status": "possible_match",
                    "data": {
                        "possible_matches": [
                            {
                                "candidate_id": str(c.id),
                                "name": c.name,
                                "company": c.current_company,
                                "match_reason": "name_company",
                                "synco_url": f"/candidates/{c.id}/",
                            }
                            for c in identity.possible_matches
                        ]
                    },
                },
                status=409,
            )

        # Create new candidate
        try:
            candidate = _create_candidate(cleaned, request.user)
        except IntegrityError:
            return _json_error(["Candidate already exists (concurrent save)"], 409)

    return JsonResponse(
        {
            "status": "success",
            "data": {
                "candidate_id": str(candidate.id),
                "name": candidate.name,
                "synco_url": f"/candidates/{candidate.id}/",
                "operation": "created",
            },
        },
        status=201,
    )


def _create_candidate(cleaned: dict, user) -> Candidate:
    """새 후보자 + Career + Education 생성. 호출자가 transaction.atomic() 보장."""
    candidate = Candidate.objects.create(
        name=cleaned["name"],
        current_company=cleaned["current_company"],
        current_position=cleaned["current_position"],
        address=cleaned["address"],
        email=cleaned["email"],
        phone=cleaned["phone"],
        phone_normalized=cleaned["phone_normalized"],
        external_profile_url=cleaned["external_profile_url"],
        skills=cleaned["skills"],
        source=Candidate.Source.CHROME_EXT,
        consent_status="not_requested",
    )

    for i, cd in enumerate(cleaned["careers"]):
        Career.objects.create(
            candidate=candidate,
            company=cd.get("company", "")[:255],
            position=cd.get("position", "")[:255],
            department=cd.get("department", "")[:255],
            start_date=cd.get("start_date", "")[:255],
            end_date=cd.get("end_date", "")[:255],
            is_current=cd.get("is_current", "") == "true"
            or cd.get("is_current") is True,
            duties=cd.get("duties", ""),
            order=i,
        )

    for ed in cleaned["educations"]:
        Education.objects.create(
            candidate=candidate,
            institution=ed.get("institution", "")[:255],
            degree=ed.get("degree", "")[:100],
            major=ed.get("major", "")[:255],
            start_year=parse_int_or_none(ed.get("start_year")),
            end_year=parse_int_or_none(ed.get("end_year")),
        )

    ExtractionLog.objects.create(
        candidate=candidate,
        action=ExtractionLog.Action.EXTENSION_SAVE,
        actor=user,
        details={
            "source_site": cleaned["source_site"],
            "source_url": cleaned["source_url"],
            "operation": "created",
            "parse_quality": cleaned["parse_quality"],
        },
    )

    return candidate


def _build_diff(candidate: Candidate, cleaned: dict) -> dict:
    """기존 후보자와 새 데이터의 차이."""
    diff = {}

    # Field diff
    field_map = {
        "current_company": "current_company",
        "current_position": "current_position",
        "address": "address",
        "email": "email",
        "phone": "phone",
        "external_profile_url": "external_profile_url",
    }
    for key, attr in field_map.items():
        old_val = getattr(candidate, attr, "")
        new_val = cleaned.get(key, "")
        if new_val and new_val != old_val:
            diff[key] = {"old": old_val, "new": new_val}

    # Career diff
    existing_careers = set()
    for c in candidate.careers.all():
        key = (normalize_company(c.company), c.start_date.strip())
        existing_careers.add(key)

    new_careers = []
    for cd in cleaned.get("careers", []):
        key = (
            normalize_company(cd.get("company", "")),
            cd.get("start_date", "").strip(),
        )
        if key not in existing_careers:
            new_careers.append(cd)
    if new_careers:
        diff["new_careers"] = new_careers

    # Education diff
    existing_educations = set()
    for e in candidate.educations.all():
        key = (e.institution.lower().strip(), e.degree.lower().strip())
        existing_educations.add(key)

    new_educations = []
    for ed in cleaned.get("educations", []):
        key = (
            ed.get("institution", "").lower().strip(),
            ed.get("degree", "").lower().strip(),
        )
        if key not in existing_educations:
            new_educations.append(ed)
    if new_educations:
        diff["new_educations"] = new_educations

    return diff


@transaction.atomic
def _handle_update(request, cleaned: dict) -> JsonResponse:
    """사용자가 확인한 필드만 업데이트."""
    try:
        candidate = Candidate.objects.select_for_update().get(
            id=cleaned["candidate_id"],
        )
    except (Candidate.DoesNotExist, ValueError):
        return _json_error(["Candidate not found"], 404)

    updated_fields = []
    allowed_fields = [
        "current_company",
        "current_position",
        "address",
        "email",
        "phone",
        "external_profile_url",
    ]

    for field in cleaned.get("fields", []):
        if field not in allowed_fields:
            continue
        new_val = cleaned.get(field, "")
        if not new_val:
            continue
        # URL normalization
        if field == "external_profile_url":
            new_val = normalize_url(new_val)
        old_val = getattr(candidate, field, "")
        if old_val != new_val:
            setattr(candidate, field, new_val)
            updated_fields.append(field)

    # Add confirmed new careers
    for i, cd in enumerate(cleaned.get("new_careers_confirmed", [])):
        Career.objects.create(
            candidate=candidate,
            company=cd.get("company", "")[:255],
            position=cd.get("position", "")[:255],
            department=cd.get("department", "")[:255],
            start_date=cd.get("start_date", "")[:255],
            end_date=cd.get("end_date", "")[:255],
            is_current=cd.get("is_current", "") == "true"
            or cd.get("is_current") is True,
            order=candidate.careers.count() + i,
        )
        updated_fields.append(f"career:{cd.get('company', '')}")

    # Add confirmed new educations
    for ed in cleaned.get("new_educations_confirmed", []):
        Education.objects.create(
            candidate=candidate,
            institution=ed.get("institution", "")[:255],
            degree=ed.get("degree", "")[:100],
            major=ed.get("major", "")[:255],
            start_year=parse_int_or_none(ed.get("start_year")),
            end_year=parse_int_or_none(ed.get("end_year")),
        )
        updated_fields.append(f"education:{ed.get('institution', '')}")

    if updated_fields:
        if "phone" in updated_fields:
            candidate.phone_normalized = normalize_phone_for_matching(candidate.phone)
        try:
            candidate.save()
        except IntegrityError:
            return _json_error(["URL conflict with existing candidate"], 409)

    ExtractionLog.objects.create(
        candidate=candidate,
        action=ExtractionLog.Action.EXTENSION_SAVE,
        actor=request.user,
        details={
            "source_site": cleaned["source_site"],
            "source_url": cleaned["source_url"],
            "operation": "updated",
            "fields_changed": updated_fields,
        },
    )

    return JsonResponse(
        {
            "status": "success",
            "data": {
                "candidate_id": str(candidate.id),
                "name": candidate.name,
                "synco_url": f"/candidates/{candidate.id}/",
                "operation": "updated",
                "fields_updated": updated_fields,
            },
        }
    )
