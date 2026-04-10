# P19: Chrome Extension — 확정 구현계획서

> **Source:** design-spec-agreed.md (확정 설계서) + impl-rulings.md (구현 쟁점 판정)
> **Scope:** Django 서버 API + Chrome Extension (Manifest V3)

---

## Step 0: DB Migration — 모델 변경

### 0.1 Candidate 모델 확장

**파일:** `candidates/models.py`

```python
# Source TextChoices 추가
class Source(models.TextChoices):
    DRIVE_IMPORT = "drive_import", "드라이브 임포트"
    MANUAL = "manual", "직접 입력"
    REFERRAL = "referral", "추천"
    CHROME_EXT = "chrome_ext", "크롬 확장"

# 새 필드 (Candidate 클래스 내)
external_profile_url = models.CharField(
    max_length=500, blank=True, default="", db_index=True,
    help_text="LinkedIn/잡코리아/사람인 프로필 URL (정규화)"
)
consent_status = models.CharField(
    max_length=20, blank=True, default="not_requested",
    help_text="not_requested | requested | granted | denied"
)

# Meta constraints 추가
class Meta:
    ...
    constraints = [
        models.UniqueConstraint(
            fields=["owned_by", "external_profile_url"],
            condition=models.Q(external_profile_url__gt=""),
            name="unique_candidate_external_url_per_org",
        ),
    ]
```

### 0.2 ExtractionLog 모델 확장

**파일:** `candidates/models.py`

```python
class ExtractionLog(BaseModel):
    class Action(models.TextChoices):
        AUTO_EXTRACT = "auto_extract", "자동 추출"
        HUMAN_EDIT = "human_edit", "사람 편집"
        HUMAN_CONFIRM = "human_confirm", "사람 확인"
        HUMAN_REJECT = "human_reject", "사람 거부"
        EXTENSION_SAVE = "extension_save", "확장 저장"  # NEW

    candidate = models.ForeignKey(...)
    resume = models.ForeignKey(...)
    action = models.CharField(...)
    field_name = models.CharField(...)
    old_value = models.TextField(...)
    new_value = models.TextField(...)
    confidence = models.FloatField(...)
    note = models.TextField(...)
    # NEW fields
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="extraction_logs",
    )
    details = models.JSONField(default=dict, blank=True)
```

### 0.3 Migration 실행

```bash
uv run python manage.py makemigrations candidates
uv run python manage.py migrate
uv run pytest -v  # 기존 테스트 통과 확인
```

---

## Step 1: 서버 API — 인증 & 기반

### 1.1 커스텀 인증 데코레이터

**파일:** `candidates/views_extension.py`

```python
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
    strip_html,
    safe_str,
    MAX_PAYLOAD_SIZE,
)


def extension_login_required(view_func):
    """Extension API용 인증 데코레이터. 미인증 시 JSON 401 반환."""
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"status": "error", "errors": ["Authentication required"]},
                status=401,
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_user_org(user):
    """사용자의 Organization 반환. 멤버십 없으면 None."""
    membership = getattr(user, "membership", None)
    return membership.organization if membership else None


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
```

### 1.2 URL 라우팅

**파일:** `candidates/urls.py` — 기존 패턴에 추가:

```python
from .views_extension import (
    extension_auth_status,
    extension_check_duplicate,
    extension_save_profile,
    extension_search,
    extension_stats,
)

# Extension API (csrf_exempt applied in views)
path("extension/auth-status/", extension_auth_status, name="extension_auth_status"),
path("extension/save-profile/", extension_save_profile, name="extension_save_profile"),
path("extension/check-duplicate/", extension_check_duplicate, name="extension_check_duplicate"),
path("extension/search/", extension_search, name="extension_search"),
path("extension/stats/", extension_stats, name="extension_stats"),
```

### 1.3 인증 상태 뷰

```python
@csrf_exempt
@extension_login_required
def extension_auth_status(request):
    """GET: 인증 상태 + 사용자/조직 정보."""
    if request.method != "GET":
        return _json_error(["Method not allowed"], 405)

    org = _get_user_org(request.user)
    return JsonResponse({
        "status": "success",
        "data": {
            "authenticated": True,
            "user": request.user.get_full_name() or request.user.username,
            "organization": org.name if org else None,
        }
    })
```

### 1.4 통계 뷰

```python
@csrf_exempt
@extension_login_required
def extension_stats(request):
    """GET: org 내 총 후보자 수."""
    if request.method != "GET":
        return _json_error(["Method not allowed"], 405)

    org = _get_user_org(request.user)
    if org is None:
        return _json_error(["No organization"], 403)

    count = Candidate.objects.filter(owned_by=org).count()
    return JsonResponse({
        "status": "success",
        "data": {"total_candidates": count}
    })
```

---

## Step 2: 서버 API — 중복 감지 & 검색

### 2.1 Identity 서비스 확장

**파일:** `candidates/services/candidate_identity.py`

```python
from dataclasses import dataclass, field as dataclass_field


@dataclass
class ExtensionIdentityResult:
    """Extension 중복 감지 결과."""
    match_type: str  # "exact" | "possible" | "none"
    candidate: Candidate | None = None
    match_reason: str = ""  # "external_url" | "email" | "phone" | "name_company"
    possible_matches: list = dataclass_field(default_factory=list)


def identify_candidate_from_extension(
    data: dict, organization
) -> ExtensionIdentityResult:
    """Extension 프로필 데이터로 중복 감지.

    매칭 순서 (first exact match wins):
      1. external_profile_url 일치 (org 스코핑)
      2. email 일치 (org 스코핑)
      3. phone 일치 (org 스코핑)
      4. name+company 유사 매칭 → possible_matches (사용자 확인 필요)

    Race condition 방지: 호출자가 transaction.atomic() 내에서 호출해야 함.
    select_for_update()는 exact match 시 적용.
    """
    base_qs = Candidate.objects.filter(owned_by=organization)

    # 1. External URL match
    url = (data.get("external_profile_url") or "").strip()
    if url:
        candidate = base_qs.select_for_update().filter(
            external_profile_url=url
        ).first()
        if candidate:
            return ExtensionIdentityResult("exact", candidate, "external_url")

    # 2. Email match
    email = (data.get("email") or "").strip().lower()
    if email:
        candidate = base_qs.select_for_update().filter(
            email__iexact=email
        ).first()
        if candidate:
            return ExtensionIdentityResult("exact", candidate, "email")

    # 3. Phone match (normalized)
    phone = data.get("phone") or ""
    normalized = normalize_phone_for_matching(phone)
    if len(normalized) >= 10:
        candidate = base_qs.select_for_update().filter(
            phone_normalized=normalized
        ).first()
        if candidate:
            return ExtensionIdentityResult("exact", candidate, "phone")

    # 4. Name + Company possible match (NOT auto-merge)
    name = (data.get("name") or "").strip()
    company = (data.get("current_company") or "").strip()
    if name and company:
        possible = list(
            base_qs.filter(
                name__iexact=name,
                current_company__iexact=company,
            ).order_by("-updated_at")[:5]
        )
        if possible:
            return ExtensionIdentityResult("possible", None, "name_company", possible)

    return ExtensionIdentityResult("none")
```

### 2.2 중복 체크 뷰

```python
@csrf_exempt
@extension_login_required
def extension_check_duplicate(request):
    """POST: 중복 체크 (lightweight, diff 미포함)."""
    if request.method != "POST":
        return _json_error(["Method not allowed"], 405)

    org = _get_user_org(request.user)
    if org is None:
        return _json_error(["No organization"], 403)

    data, err = _parse_json_body(request)
    if err:
        return err

    result = identify_candidate_from_extension(data, org)

    if result.match_type == "exact":
        return JsonResponse({
            "status": "duplicate_found",
            "data": {
                "candidate_id": str(result.candidate.id),
                "name": result.candidate.name,
                "company": result.candidate.current_company,
                "position": result.candidate.current_position,
                "match_reason": result.match_reason,
                "synco_url": f"/candidates/{result.candidate.id}/",
                "updated_at": result.candidate.updated_at.isoformat(),
            }
        })
    elif result.match_type == "possible":
        return JsonResponse({
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
            }
        })
    else:
        return JsonResponse({"status": "success", "data": {"exists": False}})
```

### 2.3 검색 뷰

```python
@csrf_exempt
@extension_login_required
def extension_search(request):
    """GET: 키워드 검색. org 스코핑, 페이지네이션."""
    if request.method != "GET":
        return _json_error(["Method not allowed"], 405)

    org = _get_user_org(request.user)
    if org is None:
        return _json_error(["No organization"], 403)

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
    qs = (
        Candidate.objects.filter(owned_by=org)
        .filter(
            Q(name__icontains=q) |
            Q(current_company__icontains=q) |
            Q(current_position__icontains=q) |
            Q(email__icontains=q)
        )
        .order_by("-updated_at")
    )

    total = qs.count()
    candidates = qs[offset:offset + page_size]

    return JsonResponse({
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
        }
    })
```

---

## Step 3: 서버 API — 데이터 검증

### 3.1 입력 검증 모듈

**파일:** `candidates/serializers_extension.py`

```python
import re
from html import unescape

MAX_PAYLOAD_SIZE = 100 * 1024  # 100KB

FIELD_LIMITS = {
    "name": 100,
    "current_company": 255,
    "current_position": 255,
    "address": 500,
    "email": 254,
    "phone": 255,
    "external_profile_url": 500,
}

ARRAY_LIMITS = {
    "careers": 50,
    "educations": 20,
    "skills": 100,
}


def safe_str(val) -> str:
    """None-safe string conversion. None -> "", else str(val)."""
    if val is None:
        return ""
    return str(val)


def strip_html(value: str) -> str:
    """HTML 태그 제거, 엔티티 디코딩."""
    cleaned = re.sub(r"<[^>]+>", "", value)
    return unescape(cleaned).strip()


def normalize_url(url: str) -> str:
    """외부 프로필 URL 정규화. 서버에서만 수행."""
    from urllib.parse import urlsplit, urlunsplit
    url = url.strip()
    if not url:
        return ""
    parts = urlsplit(url)
    # Remove query, fragment, trailing slash
    normalized = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
    return normalized.lower()


def normalize_company(name: str) -> str:
    """회사명 정규화 (비교용)."""
    name = name.strip().lower()
    # Remove common Korean legal suffixes
    for suffix in ["(주)", "주식회사", "(유)", "유한회사", "㈜"]:
        name = name.replace(suffix, "")
    return name.strip()


def parse_int_or_none(val) -> int | None:
    """안전한 정수 파싱. 실패 시 None."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    try:
        # Handle strings like "2020", "2020년"
        digits = re.sub(r"\D", "", str(val))
        if digits and len(digits) <= 4:
            return int(digits)
    except (ValueError, TypeError):
        pass
    return None


def _validate_dict_item(item, field_keys: list[str]) -> dict | None:
    """배열 요소가 dict인지 확인. 아니면 None."""
    if not isinstance(item, dict):
        return None
    return {k: strip_html(safe_str(item.get(k, ""))) for k in field_keys}


def validate_profile_data(raw_data: dict) -> tuple[dict | None, list[str]]:
    """프로필 데이터 검증. (cleaned_data, errors) 반환."""
    errors = []

    # Required: name
    name = strip_html(safe_str(raw_data.get("name", "")).strip())
    if not name:
        errors.append("name is required")

    # Build cleaned fields
    company = strip_html(safe_str(raw_data.get("current_company", "")))
    position = strip_html(safe_str(raw_data.get("current_position", "")))
    email = safe_str(raw_data.get("email", "")).strip().lower()
    phone = safe_str(raw_data.get("phone", ""))
    ext_url = normalize_url(safe_str(raw_data.get("external_profile_url", "")))

    # Phone normalization for secondary check
    from candidates.services.candidate_identity import normalize_phone_for_matching
    normalized_phone = normalize_phone_for_matching(phone)
    phone_valid = len(normalized_phone) >= 10

    # Secondary identifier check (at least one required)
    if not any([company, position, email, ext_url, phone_valid]):
        errors.append(
            "At least one of company, position, email, external_profile_url, "
            "or phone (10+ digits) required"
        )

    # Identity field length validation (reject, not truncate)
    if email and len(email) > FIELD_LIMITS["email"]:
        errors.append(f"email exceeds {FIELD_LIMITS['email']} chars")
    if ext_url and len(ext_url) > FIELD_LIMITS["external_profile_url"]:
        errors.append(f"external_profile_url exceeds {FIELD_LIMITS['external_profile_url']} chars")

    if errors:
        return None, errors

    cleaned = {
        "name": name[:FIELD_LIMITS["name"]],
        "current_company": company[:FIELD_LIMITS["current_company"]],
        "current_position": position[:FIELD_LIMITS["current_position"]],
        "address": strip_html(safe_str(raw_data.get("address", "")))[:FIELD_LIMITS["address"]],
        "email": email,
        "phone": phone[:FIELD_LIMITS["phone"]],
        "phone_normalized": normalized_phone,
        "external_profile_url": ext_url,
        "source_site": safe_str(raw_data.get("source_site", ""))[:20],
        "source_url": safe_str(raw_data.get("source_url", ""))[:500],
        "parse_quality": safe_str(raw_data.get("parse_quality", "complete"))[:20],
    }

    # Validate email format
    if cleaned["email"] and "@" not in cleaned["email"]:
        errors.append("Invalid email format")

    # Validate URL
    if cleaned["external_profile_url"] and not cleaned["external_profile_url"].startswith("http"):
        errors.append("external_profile_url must start with http")

    # Array fields — validate each item is dict
    career_keys = ["company", "position", "department", "start_date", "end_date", "is_current", "duties"]
    careers_raw = raw_data.get("careers", [])
    if not isinstance(careers_raw, list):
        careers_raw = []
    cleaned["careers"] = [
        item for item in
        (_validate_dict_item(c, career_keys) for c in careers_raw[:ARRAY_LIMITS["careers"]])
        if item is not None
    ]

    edu_keys = ["institution", "degree", "major", "start_year", "end_year"]
    edus_raw = raw_data.get("educations", [])
    if not isinstance(edus_raw, list):
        edus_raw = []
    cleaned["educations"] = [
        item for item in
        (_validate_dict_item(e, edu_keys) for e in edus_raw[:ARRAY_LIMITS["educations"]])
        if item is not None
    ]

    skills_raw = raw_data.get("skills", [])
    if not isinstance(skills_raw, list):
        skills_raw = []
    cleaned["skills"] = [strip_html(safe_str(s))[:100] for s in skills_raw[:ARRAY_LIMITS["skills"]]]

    # Update mode fields
    cleaned["update_mode"] = bool(raw_data.get("update_mode", False))
    cleaned["candidate_id"] = safe_str(raw_data.get("candidate_id", ""))
    cleaned["fields"] = raw_data.get("fields", [])

    # Confirmed new records for update mode
    new_careers_raw = raw_data.get("new_careers_confirmed", [])
    if not isinstance(new_careers_raw, list):
        new_careers_raw = []
    cleaned["new_careers_confirmed"] = [
        item for item in
        (_validate_dict_item(c, career_keys) for c in new_careers_raw[:ARRAY_LIMITS["careers"]])
        if item is not None
    ]

    new_edus_raw = raw_data.get("new_educations_confirmed", [])
    if not isinstance(new_edus_raw, list):
        new_edus_raw = []
    cleaned["new_educations_confirmed"] = [
        item for item in
        (_validate_dict_item(e, edu_keys) for e in new_edus_raw[:ARRAY_LIMITS["educations"]])
        if item is not None
    ]

    if errors:
        return None, errors

    return cleaned, []
```

---

## Step 4: 서버 API — 프로필 저장

### 4.1 저장 뷰

**파일:** `candidates/views_extension.py`

```python
@csrf_exempt
@extension_login_required
def extension_save_profile(request):
    """POST: 프로필 저장/업데이트."""
    if request.method != "POST":
        return _json_error(["Method not allowed"], 405)

    org = _get_user_org(request.user)
    if org is None:
        return _json_error(["No organization"], 403)

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
        return _handle_update(request, cleaned, org)

    # New save: check duplicates within transaction
    with transaction.atomic():
        identity = identify_candidate_from_extension(cleaned, org)

        if identity.match_type == "exact":
            diff = _build_diff(identity.candidate, cleaned)
            return JsonResponse({
                "status": "duplicate_found",
                "data": {
                    "candidate_id": str(identity.candidate.id),
                    "name": identity.candidate.name,
                    "match_reason": identity.match_reason,
                    "synco_url": f"/candidates/{identity.candidate.id}/",
                    "diff": diff,
                }
            }, status=409)

        if identity.match_type == "possible":
            return JsonResponse({
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
                }
            }, status=409)

        # Create new candidate
        try:
            candidate = _create_candidate(cleaned, org, request.user)
        except IntegrityError:
            return _json_error(["Candidate already exists (concurrent save)"], 409)

    return JsonResponse({
        "status": "success",
        "data": {
            "candidate_id": str(candidate.id),
            "name": candidate.name,
            "synco_url": f"/candidates/{candidate.id}/",
            "operation": "created",
        }
    }, status=201)
```

### 4.2 후보자 생성

```python
def _create_candidate(cleaned: dict, organization, user) -> Candidate:
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
        owned_by=organization,
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
            is_current=cd.get("is_current", "") == "true" or cd.get("is_current") is True,
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
```

### 4.3 Diff 산출 (Career + Education)

```python
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
        key = (normalize_company(cd.get("company", "")), cd.get("start_date", "").strip())
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
        key = (ed.get("institution", "").lower().strip(), ed.get("degree", "").lower().strip())
        if key not in existing_educations:
            new_educations.append(ed)
    if new_educations:
        diff["new_educations"] = new_educations

    return diff
```

### 4.4 업데이트 처리

```python
@transaction.atomic
def _handle_update(request, cleaned: dict, org) -> JsonResponse:
    """사용자가 확인한 필드만 업데이트."""
    try:
        candidate = Candidate.objects.select_for_update().get(
            id=cleaned["candidate_id"], owned_by=org,
        )
    except (Candidate.DoesNotExist, ValueError):
        return _json_error(["Candidate not found"], 404)

    updated_fields = []
    allowed_fields = [
        "current_company", "current_position", "address",
        "email", "phone", "external_profile_url",
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
            is_current=cd.get("is_current", "") == "true" or cd.get("is_current") is True,
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

    return JsonResponse({
        "status": "success",
        "data": {
            "candidate_id": str(candidate.id),
            "name": candidate.name,
            "synco_url": f"/candidates/{candidate.id}/",
            "operation": "updated",
            "fields_updated": updated_fields,
        }
    })
```

---

## Step 5: Django 설정 변경

**파일:** `main/settings.py`

Production 쿠키 설정 (환경변수로 분기):

```python
# Extension cross-origin cookie support (production only)
if os.environ.get("SYNCO_ENV") == "production":
    SESSION_COOKIE_SAMESITE = "None"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = "None"
    CSRF_COOKIE_SECURE = True
```

**주의:** `@csrf_exempt`를 사용하므로 CSRF_TRUSTED_ORIGINS 변경 불필요. Extension 뷰는 세션 인증만 체크.

---

## Step 6: 서버 테스트

**파일:** `tests/test_extension_api.py`

### 테스트 목록

```python
import pytest
from django.test import TestCase, Client
from candidates.models import Candidate, Career, Education, ExtractionLog
from accounts.models import User, Organization, Membership


class TestExtensionAuth(TestCase):
    """인증 테스트."""
    def test_unauthenticated_returns_401_json(self):
    def test_authenticated_returns_user_and_org(self):
    def test_no_membership_returns_null_org(self):

class TestExtensionSaveProfile(TestCase):
    """프로필 저장 테스트."""
    def test_create_new_candidate_201(self):
    def test_create_with_careers_and_educations(self):
    def test_missing_name_returns_400(self):
    def test_missing_all_secondary_identifiers_400(self):
    def test_name_plus_phone_accepted(self):
    def test_html_stripped_from_fields(self):
    def test_none_values_become_empty_string(self):
    def test_duplicate_url_returns_409_with_diff(self):
    def test_possible_match_returns_409(self):
    def test_concurrent_save_same_url_one_succeeds(self):
    def test_cross_org_isolation(self):
    def test_rate_limit_101st_returns_429(self):
    def test_payload_too_large_returns_413(self):
    def test_invalid_json_returns_400(self):
    def test_non_object_json_returns_400(self):
    def test_source_set_to_chrome_ext(self):
    def test_consent_status_not_requested(self):
    def test_extraction_log_created_with_actor_details(self):
    def test_education_year_string_parsed(self):
    def test_education_year_invalid_becomes_none(self):
    def test_malformed_career_item_skipped(self):
    def test_long_email_rejected(self):
    def test_long_url_rejected(self):

class TestExtensionUpdateMode(TestCase):
    """업데이트 모드 테스트."""
    def test_update_confirmed_fields(self):
    def test_update_external_url(self):
    def test_update_new_careers_confirmed(self):
    def test_update_new_educations_confirmed(self):
    def test_update_wrong_org_returns_404(self):
    def test_update_url_conflict_returns_409(self):

class TestExtensionCheckDuplicate(TestCase):
    """중복 체크 테스트."""
    def test_exact_match_by_url(self):
    def test_exact_match_by_email(self):
    def test_exact_match_by_phone(self):
    def test_possible_match_by_name_company_iexact(self):
    def test_no_match(self):
    def test_cross_org_isolation(self):
    def test_invalid_json_returns_400(self):

class TestExtensionSearch(TestCase):
    """검색 테스트."""
    def test_search_by_name(self):
    def test_search_by_company(self):
    def test_search_min_query_length(self):
    def test_search_pagination(self):
    def test_search_invalid_page(self):
    def test_cross_org_isolation(self):

class TestExtensionStats(TestCase):
    """통계 테스트."""
    def test_returns_org_candidate_count(self):
    def test_cross_org_isolation(self):
```

**실행:** `uv run pytest tests/test_extension_api.py -v`

---

## Step 7: Chrome Extension — 기반

### 7.1 manifest.json

**파일:** `synco-extension/manifest.json`

확정 설계서의 manifest 구현. `host_permissions`에 synco 서버 URL (빌드 시 결정).

### 7.2 Service Worker

**파일:** `synco-extension/background/service-worker.js`

```javascript
const API = {
  async getServerUrl() {
    const { serverUrl } = await chrome.storage.sync.get("serverUrl");
    return serverUrl || "https://synco.example.com";
  },

  async request(path, options = {}) {
    const baseUrl = await this.getServerUrl();
    const url = `${baseUrl}/candidates/extension${path}`;

    const defaultHeaders = { "Content-Type": "application/json" };
    const headers = { ...defaultHeaders, ...(options.headers || {}) };

    const response = await fetch(url, {
      credentials: "include",
      ...options,
      headers,
    });
    return response.json();
  },

  async checkAuth() {
    try {
      return await this.request("/auth-status/");
    } catch (e) {
      return { status: "error", errors: [e.message] };
    }
  },

  async saveProfile(data) {
    return this.request("/save-profile/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async checkDuplicate(data) {
    return this.request("/check-duplicate/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async search(query, page = 1) {
    return this.request(`/search/?q=${encodeURIComponent(query)}&page=${page}`);
  },

  async getStats() {
    return this.request("/stats/");
  },
};

// Message routing
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      switch (message.type) {
        case "CHECK_AUTH":
          sendResponse(await API.checkAuth());
          break;
        case "CHECK_DUPLICATE":
          sendResponse(await API.checkDuplicate(message.data));
          break;
        case "SAVE_PROFILE":
          sendResponse(await API.saveProfile(message.data));
          break;
        case "SEARCH":
          sendResponse(await API.search(message.query, message.page));
          break;
        case "GET_STATS":
          sendResponse(await API.getStats());
          break;
        default:
          sendResponse({ status: "error", errors: ["Unknown message type"] });
      }
    } catch (e) {
      sendResponse({ status: "error", errors: [e.message] });
    }
  })();
  return true;
});

chrome.runtime.onInstalled.addListener(() => API.checkAuth());
```

### 7.3 Options Page

**파일:** `synco-extension/options/options.html`, `options.js`

서버 URL 설정 + 연결 테스트 + 사이트별 파서 on/off.

---

## Step 8: Chrome Extension — 콘텐츠 스크립트

### 8.1 공통 오버레이 모듈

각 콘텐츠 스크립트에서 공유하는 오버레이 생성/표시 함수. Shadow DOM으로 사이트 스타일 격리.

### 8.2 LinkedIn 파서 (`content/linkedin.js`)

- `/in/*` URL에서만 활성화
- MutationObserver + URL 변경 감지 (SPA 대응)
- `LinkedInParser.parse()` → `parse_quality` 산출
- 오버레이: 인증 → 파싱 → 중복 체크 → 결과 표시
- 저장 버튼 debounce 300ms

### 8.3 잡코리아 파서 (`content/jobkorea.js`)

동일 패턴. 잡코리아 DOM 셀렉터 사용.

### 8.4 사람인 파서 (`content/saramin.js`)

동일 패턴. 사람인 DOM 셀렉터 사용.

### 8.5 LinkedIn SPA 네비게이션 처리

```javascript
// URL 변경 감지 (LinkedIn SPA)
let lastUrl = location.href;
const urlObserver = new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    SyncoOverlay.remove();
    // Re-parse after DOM settles
    setTimeout(() => init(), 1500);
  }
});
urlObserver.observe(document.body, { childList: true, subtree: true });
```

---

## Step 9: Chrome Extension — 팝업

**파일:** `synco-extension/popup/popup.html`, `popup.js`, `popup.css`

- 검색: message to service worker → API → 결과 표시
- 최근 저장: `chrome.storage.local` (최대 20건)
- 오늘 저장 수: `chrome.storage.local` (date-keyed)
- 총 DB: service worker → `GET /stats/`
- synco 열기: `chrome.tabs.create()`

---

## Step 10: 통합 테스트 & 마무리

### 10.1 서버 테스트

```bash
uv run pytest tests/test_extension_api.py -v
uv run ruff check . && uv run ruff format .
```

### 10.2 Extension 수동 테스트

1. `chrome://extensions` → 개발자 모드 → synco-extension 로드
2. Options → 서버 URL 설정 (localhost:8000) → 연결 테스트
3. synco 로그인
4. LinkedIn /in/ 프로필 → 오버레이 확인
5. "저장" → 201 확인 → DB 확인
6. 동일 프로필 재방문 → "DB에 있음" 확인
7. 팝업 검색 → 결과 확인
8. 프로필 간 SPA 이동 → 오버레이 재생성 확인

---

## 구현 순서 요약

| Step | 내용 | 검증 |
|------|------|------|
| 0 | DB migration (모델 변경 + ExtractionLog 확장) | makemigrations + migrate + 기존 pytest |
| 1 | 인증/기반 API (auth-status, stats) | curl 수동 |
| 2 | 중복 감지 + 검색 API | 단위 테스트 |
| 3 | 데이터 검증 모듈 | 단위 테스트 |
| 4 | 프로필 저장/업데이트 API | 단위 테스트 |
| 5 | Django 설정 (cookie) | 설정 확인 |
| 6 | 서버 전체 테스트 | pytest |
| 7 | Extension 기반 (manifest, SW, options) | 수동 로드 |
| 8 | 콘텐츠 스크립트 (3개 사이트) | 실제 사이트 |
| 9 | 팝업 UI | 수동 |
| 10 | 통합 테스트 | pytest + 수동 |

---

## 파일 변경 목록

### 신규 파일

| 파일 | 내용 |
|------|------|
| `candidates/views_extension.py` | Extension API 5개 뷰 + 헬퍼 |
| `candidates/serializers_extension.py` | 프로필 데이터 검증 |
| `candidates/migrations/NNNN_add_extension_fields.py` | Candidate + ExtractionLog 마이그레이션 |
| `tests/test_extension_api.py` | 서버 API 테스트 (~40 test cases) |
| `synco-extension/manifest.json` | Manifest V3 |
| `synco-extension/background/service-worker.js` | API 통신 + 메시지 라우팅 |
| `synco-extension/content/linkedin.js` | LinkedIn /in/* 파서 |
| `synco-extension/content/jobkorea.js` | 잡코리아 파서 |
| `synco-extension/content/saramin.js` | 사람인 파서 |
| `synco-extension/popup/popup.html` | 팝업 HTML |
| `synco-extension/popup/popup.js` | 팝업 JS |
| `synco-extension/popup/popup.css` | 팝업 CSS |
| `synco-extension/options/options.html` | 옵션 HTML |
| `synco-extension/options/options.js` | 옵션 JS |
| `synco-extension/styles/overlay.css` | 오버레이 CSS |

### 수정 파일

| 파일 | 변경 |
|------|------|
| `candidates/models.py` | Source.CHROME_EXT, external_profile_url, consent_status, UniqueConstraint, ExtractionLog.actor, ExtractionLog.details, ExtractionLog.Action.EXTENSION_SAVE |
| `candidates/urls.py` | `/extension/*` URL 5개 추가 |
| `candidates/services/candidate_identity.py` | `ExtensionIdentityResult`, `identify_candidate_from_extension()` |
| `main/settings.py` | Production cookie SameSite settings |

<!-- forge:p19-chrome-extension:구현담금질:complete:2026-04-10T14:15:00+09:00 -->
