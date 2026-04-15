# P19: Chrome Extension — 구현계획서 초안

> **Source:** design-spec-agreed.md (확정 설계서)
> **Scope:** Django 서버 API + Chrome Extension (Manifest V3)

---

## Step 0: 사전 준비

### 0.1 DB Migration — Candidate 모델 확장

**파일:** `candidates/migrations/NNNN_add_extension_fields.py` (auto-generated)

**변경 사항:**
```python
# candidates/models.py

# Source TextChoices에 추가
class Source(models.TextChoices):
    DRIVE_IMPORT = "drive_import", "드라이브 임포트"
    MANUAL = "manual", "직접 입력"
    REFERRAL = "referral", "추천"
    CHROME_EXT = "chrome_ext", "크롬 확장"

# 새 필드 (Candidate 클래스 내)
external_profile_url = models.CharField(
    max_length=500, blank=True, db_index=True,
    help_text="LinkedIn/잡코리아/사람인 프로필 URL (정규화)"
)
consent_status = models.CharField(
    max_length=20, blank=True, default="",
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

**ExtractionLog Action 확장:**
```python
class Action(models.TextChoices):
    AUTO_EXTRACT = "auto_extract", "자동 추출"
    HUMAN_EDIT = "human_edit", "사람 편집"
    HUMAN_CONFIRM = "human_confirm", "사람 확인"
    EXTENSION_SAVE = "extension_save", "확장 저장"
```

**실행:**
```bash
uv run python manage.py makemigrations candidates
uv run python manage.py migrate
```

**검증:** `uv run pytest tests/ -v -k "candidate"` — 기존 테스트 통과 확인

---

## Step 1: 서버 API — 인증 & 기반

### 1.1 URL 라우팅

**파일:** `candidates/urls.py`

기존 `urlpatterns`에 extension 엔드포인트 추가:
```python
from .views_extension import (
    extension_auth_status,
    extension_check_duplicate,
    extension_save_profile,
    extension_search,
    extension_stats,
)

urlpatterns = [
    # ... existing patterns ...
    # Extension API
    path("extension/auth-status/", extension_auth_status, name="extension_auth_status"),
    path("extension/save-profile/", extension_save_profile, name="extension_save_profile"),
    path("extension/check-duplicate/", extension_check_duplicate, name="extension_check_duplicate"),
    path("extension/search/", extension_search, name="extension_search"),
    path("extension/stats/", extension_stats, name="extension_stats"),
]
```

### 1.2 인증 상태 뷰

**파일:** `candidates/views_extension.py`

```python
@login_required
def extension_auth_status(request):
    """GET: 인증 상태 + CSRF 토큰 반환."""
    if request.method != "GET":
        return JsonResponse({"status": "error", "errors": ["Method not allowed"]}, status=405)

    membership = getattr(request.user, "membership", None)
    org = membership.organization if membership else None

    return JsonResponse({
        "status": "success",
        "data": {
            "authenticated": True,
            "user": request.user.get_full_name() or request.user.username,
            "organization": org.name if org else None,
            "csrf_token": get_token(request),
        }
    })
```

**CSRF 처리:** `get_token(request)`는 `django.middleware.csrf.get_token`에서 import. Extension은 이 토큰을 POST 요청의 `X-CSRFToken` 헤더에 포함.

**검증:** 미인증 → 302 redirect (login_required 기본 동작, Extension은 응답 코드로 판별), 인증 → 200 + user/org 데이터.

### 1.3 통계 뷰

**파일:** `candidates/views_extension.py`

```python
@login_required
def extension_stats(request):
    """GET: org 내 총 후보자 수."""
    org = _get_user_org(request.user)
    if org is None:
        return JsonResponse({"status": "error", "errors": ["No organization"]}, status=403)

    count = Candidate.objects.filter(owned_by=org).count()
    return JsonResponse({
        "status": "success",
        "data": {"total_candidates": count}
    })
```

**헬퍼 함수:**
```python
def _get_user_org(user):
    """사용자의 Organization 반환. 멤버십 없으면 None."""
    membership = getattr(user, "membership", None)
    return membership.organization if membership else None

def _json_error(errors, status=400):
    return JsonResponse({"status": "error", "errors": errors}, status=status)
```

---

## Step 2: 서버 API — 중복 감지 & 검색

### 2.1 Identity 서비스 확장

**파일:** `candidates/services/candidate_identity.py`

기존 `identify_candidate()` 아래에 새 함수 추가:

```python
@dataclass
class ExtensionIdentityResult:
    """Extension 중복 감지 결과."""
    match_type: str  # "exact" | "possible" | "none"
    candidate: Candidate | None
    match_reason: str  # "external_url" | "email" | "phone" | "name_company" | ""
    possible_matches: list[Candidate]  # name+company 유사 매칭


def identify_candidate_from_extension(
    data: dict, organization
) -> ExtensionIdentityResult:
    """Extension 프로필 데이터로 중복 감지.

    매칭 순서 (first exact match wins):
      1. external_profile_url 일치 (org 스코핑)
      2. email 일치 (org 스코핑)
      3. phone 일치 (org 스코핑)
      4. name+company 유사 매칭 → possible_matches
    """
    base_qs = Candidate.objects.filter(owned_by=organization)

    # 1. External URL match
    url = (data.get("external_profile_url") or "").strip()
    if url:
        candidate = base_qs.filter(external_profile_url=url).first()
        if candidate:
            return ExtensionIdentityResult("exact", candidate, "external_url", [])

    # 2. Email match
    email = (data.get("email") or "").strip().lower()
    if email:
        candidate = base_qs.filter(email__iexact=email).first()
        if candidate:
            return ExtensionIdentityResult("exact", candidate, "email", [])

    # 3. Phone match
    phone = data.get("phone") or ""
    normalized = normalize_phone_for_matching(phone)
    if len(normalized) >= 10:
        candidate = base_qs.filter(phone_normalized=normalized).first()
        if candidate:
            return ExtensionIdentityResult("exact", candidate, "phone", [])

    # 4. Name + Company possible match
    name = (data.get("name") or "").strip()
    company = (data.get("current_company") or "").strip()
    possible = []
    if name and company:
        possible = list(
            base_qs.filter(name=name, current_company=company)
            .order_by("-updated_at")[:5]
        )

    if possible:
        return ExtensionIdentityResult("possible", None, "name_company", possible)

    return ExtensionIdentityResult("none", None, "", [])
```

**검증:** 단위 테스트 — URL 매칭, email 매칭, phone 매칭, name+company possible 매칭, cross-org 격리.

### 2.2 중복 체크 뷰

**파일:** `candidates/views_extension.py`

```python
@login_required
def extension_check_duplicate(request):
    """POST: 중복 체크. org 스코핑."""
    if request.method != "POST":
        return _json_error(["Method not allowed"], 405)

    org = _get_user_org(request.user)
    if org is None:
        return _json_error(["No organization"], 403)

    data = json.loads(request.body)
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
        return JsonResponse({
            "status": "success",
            "data": {"exists": False}
        })
```

### 2.3 검색 뷰

**파일:** `candidates/views_extension.py`

```python
@login_required
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

    page = int(request.GET.get("page", 1))
    page_size = 20
    offset = (page - 1) * page_size

    qs = Candidate.objects.filter(owned_by=org)
    # Simple name/company/position search
    from django.db.models import Q
    qs = qs.filter(
        Q(name__icontains=q) |
        Q(current_company__icontains=q) |
        Q(current_position__icontains=q) |
        Q(email__icontains=q)
    ).order_by("-updated_at")

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

## Step 3: 서버 API — 프로필 저장

### 3.1 입력 데이터 검증

**파일:** `candidates/serializers_extension.py`

DRF 미사용. plain Python 검증 클래스.

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


def strip_html(value: str) -> str:
    """HTML 태그 제거, 엔티티 디코딩."""
    cleaned = re.sub(r"<[^>]+>", "", value)
    return unescape(cleaned).strip()


def normalize_url(url: str) -> str:
    """외부 프로필 URL 정규화."""
    url = url.strip().rstrip("/").split("?")[0].split("#")[0]
    return url.lower()


def validate_profile_data(raw_data: dict) -> tuple[dict | None, list[str]]:
    """프로필 데이터 검증. (cleaned_data, errors) 반환."""
    errors = []

    # Required: name
    name = strip_html(str(raw_data.get("name", "")).strip())
    if not name:
        errors.append("name is required")

    # At least one secondary identifier
    company = strip_html(str(raw_data.get("current_company", "")))
    position = strip_html(str(raw_data.get("current_position", "")))
    email = str(raw_data.get("email", "")).strip().lower()
    ext_url = normalize_url(str(raw_data.get("external_profile_url", "")))

    if not any([company, position, email, ext_url]):
        errors.append("At least one of company, position, email, or external_profile_url required")

    if errors:
        return None, errors

    # Build cleaned data
    cleaned = {
        "name": name[:FIELD_LIMITS["name"]],
        "current_company": company[:FIELD_LIMITS["current_company"]],
        "current_position": position[:FIELD_LIMITS["current_position"]],
        "address": strip_html(str(raw_data.get("address", "")))[:FIELD_LIMITS["address"]],
        "email": email[:FIELD_LIMITS["email"]] if email else "",
        "phone": str(raw_data.get("phone", ""))[:FIELD_LIMITS["phone"]],
        "external_profile_url": ext_url[:FIELD_LIMITS["external_profile_url"]],
        "source_site": str(raw_data.get("source_site", ""))[:20],
        "source_url": str(raw_data.get("source_url", ""))[:500],
    }

    # Validate email format
    if cleaned["email"] and "@" not in cleaned["email"]:
        errors.append("Invalid email format")

    # Validate URL
    if cleaned["external_profile_url"] and not cleaned["external_profile_url"].startswith("http"):
        errors.append("external_profile_url must start with http")

    # Array fields
    careers = raw_data.get("careers", [])
    if not isinstance(careers, list):
        careers = []
    cleaned["careers"] = careers[:ARRAY_LIMITS["careers"]]

    educations = raw_data.get("educations", [])
    if not isinstance(educations, list):
        educations = []
    cleaned["educations"] = educations[:ARRAY_LIMITS["educations"]]

    skills = raw_data.get("skills", [])
    if not isinstance(skills, list):
        skills = []
    cleaned["skills"] = [str(s)[:100] for s in skills[:ARRAY_LIMITS["skills"]]]

    # Update mode fields
    cleaned["update_mode"] = bool(raw_data.get("update_mode", False))
    cleaned["candidate_id"] = str(raw_data.get("candidate_id", ""))
    cleaned["fields"] = raw_data.get("fields", [])
    cleaned["parse_quality"] = str(raw_data.get("parse_quality", "complete"))[:20]

    if errors:
        return None, errors

    return cleaned, []
```

### 3.2 프로필 저장 뷰

**파일:** `candidates/views_extension.py`

```python
@login_required
def extension_save_profile(request):
    """POST: 프로필 저장/업데이트."""
    if request.method != "POST":
        return _json_error(["Method not allowed"], 405)

    # Payload size check
    if len(request.body) > MAX_PAYLOAD_SIZE:
        return _json_error(["Payload too large"], 413)

    org = _get_user_org(request.user)
    if org is None:
        return _json_error(["No organization"], 403)

    # Rate limit: 100/day per user
    if _check_rate_limit(request.user.id, "ext_save", 100, 86400):
        return _json_error(["Daily save limit exceeded (100/day)"], 429)

    try:
        raw_data = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error(["Invalid JSON"], 400)

    cleaned, errors = validate_profile_data(raw_data)
    if errors:
        return _json_error(errors, 400)

    # Update mode: apply confirmed field changes to existing candidate
    if cleaned["update_mode"]:
        return _handle_update(request, cleaned, org)

    # New save: check duplicates first
    identity = identify_candidate_from_extension(cleaned, org)

    if identity.match_type == "exact":
        # Return diff for user confirmation
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
        # Race condition: URL unique constraint violation
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

### 3.3 후보자 생성 함수

**파일:** `candidates/views_extension.py` (private helper)

```python
@transaction.atomic
def _create_candidate(cleaned: dict, organization, user) -> Candidate:
    """새 후보자 + Career + Education 생성."""
    from candidates.services.candidate_identity import normalize_phone_for_matching

    candidate = Candidate.objects.create(
        name=cleaned["name"],
        current_company=cleaned["current_company"],
        current_position=cleaned["current_position"],
        address=cleaned["address"],
        email=cleaned["email"],
        phone=cleaned["phone"],
        phone_normalized=normalize_phone_for_matching(cleaned["phone"]),
        external_profile_url=cleaned["external_profile_url"],
        skills=cleaned["skills"],
        source=Candidate.Source.CHROME_EXT,
        owned_by=organization,
        consent_status="not_requested",
    )

    # Create careers
    for i, career_data in enumerate(cleaned["careers"]):
        Career.objects.create(
            candidate=candidate,
            company=strip_html(str(career_data.get("company", "")))[:255],
            position=strip_html(str(career_data.get("position", "")))[:255],
            department=strip_html(str(career_data.get("department", "")))[:255],
            start_date=str(career_data.get("start_date", ""))[:255],
            end_date=str(career_data.get("end_date", ""))[:255],
            is_current=bool(career_data.get("is_current", False)),
            duties=strip_html(str(career_data.get("duties", ""))),
            order=i,
        )

    # Create educations
    for edu_data in cleaned["educations"]:
        Education.objects.create(
            candidate=candidate,
            institution=strip_html(str(edu_data.get("institution", "")))[:255],
            degree=strip_html(str(edu_data.get("degree", "")))[:100],
            major=strip_html(str(edu_data.get("major", "")))[:255],
            start_year=edu_data.get("start_year"),
            end_year=edu_data.get("end_year"),
        )

    # Audit log
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

### 3.4 업데이트 & Diff 함수

```python
def _build_diff(candidate: Candidate, cleaned: dict) -> dict:
    """기존 후보자와 새 데이터의 차이 산출."""
    diff = {}
    field_map = {
        "current_company": "current_company",
        "current_position": "current_position",
        "address": "address",
        "email": "email",
        "phone": "phone",
    }
    for key, attr in field_map.items():
        old_val = getattr(candidate, attr, "")
        new_val = cleaned.get(key, "")
        if new_val and new_val != old_val:
            diff[key] = {"old": old_val, "new": new_val}

    # Career diff: new careers not in existing
    existing_careers = set()
    for c in candidate.careers.all():
        existing_careers.add((c.company.lower().strip(), c.start_date.strip()))

    new_careers = []
    for cd in cleaned.get("careers", []):
        key = (
            str(cd.get("company", "")).lower().strip(),
            str(cd.get("start_date", "")).strip(),
        )
        if key not in existing_careers:
            new_careers.append(cd)

    if new_careers:
        diff["new_careers"] = new_careers

    return diff


@transaction.atomic
def _handle_update(request, cleaned: dict, org) -> JsonResponse:
    """사용자가 확인한 필드만 업데이트."""
    try:
        candidate_id = cleaned["candidate_id"]
        candidate = Candidate.objects.select_for_update().get(
            id=candidate_id, owned_by=org
        )
    except (Candidate.DoesNotExist, ValueError):
        return _json_error(["Candidate not found"], 404)

    updated_fields = []
    allowed_fields = ["current_company", "current_position", "address", "email", "phone"]

    for field in cleaned.get("fields", []):
        if field in allowed_fields and cleaned.get(field):
            old_val = getattr(candidate, field)
            new_val = cleaned[field]
            if old_val != new_val:
                setattr(candidate, field, new_val)
                updated_fields.append(field)

    # Add new careers if specified
    new_careers = cleaned.get("new_careers_confirmed", [])
    for i, cd in enumerate(new_careers):
        Career.objects.create(
            candidate=candidate,
            company=strip_html(str(cd.get("company", "")))[:255],
            position=strip_html(str(cd.get("position", "")))[:255],
            start_date=str(cd.get("start_date", ""))[:255],
            end_date=str(cd.get("end_date", ""))[:255],
            is_current=bool(cd.get("is_current", False)),
            order=candidate.careers.count() + i,
        )
        updated_fields.append(f"career:{cd.get('company', '')}")

    if updated_fields:
        if "phone" in updated_fields:
            candidate.phone_normalized = normalize_phone_for_matching(candidate.phone)
        candidate.save()

    # Audit log
    ExtractionLog.objects.create(
        candidate=candidate,
        action=ExtractionLog.Action.EXTENSION_SAVE,
        actor=request.user,
        details={
            "source_site": cleaned["source_site"],
            "source_url": cleaned["source_url"],
            "operation": "updated",
            "fields_changed": updated_fields,
            "parse_quality": cleaned["parse_quality"],
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

**검증:** Step 3 완료 후 `uv run pytest -v` 실행.

---

## Step 4: Django 설정 변경

### 4.1 CSRF 설정

**파일:** `main/settings.py` (또는 `settings/base.py`)

```python
# Extension에서 POST 요청 시 CSRF 토큰을 헤더로 전송
CSRF_TRUSTED_ORIGINS = [
    "chrome-extension://*",  # Chrome Extension origin
    # 기존 값 유지
]

# SameSite=None for cross-origin cookie (production only)
# SESSION_COOKIE_SAMESITE = "None"  # production only
# SESSION_COOKIE_SECURE = True       # production only (HTTPS)
# CSRF_COOKIE_SAMESITE = "None"      # production only
# CSRF_COOKIE_SECURE = True           # production only
```

**주의:** 개발환경에서는 `SameSite=Lax` (기본값) 유지. Production 배포 시 환경변수로 분기.

### 4.2 CORS 설정 (필요 시)

Chrome Extension의 `host_permissions`가 있으면 CORS preflight 없이 요청 가능. 별도 CORS 미들웨어 불필요. 만약 필요하다면 `django-cors-headers` 추가하되, 현재 설계에서는 불필요.

---

## Step 5: 서버 테스트

**파일:** `tests/test_extension_api.py`

### 테스트 목록

```python
class TestExtensionAuthStatus:
    def test_unauthenticated_returns_redirect(self):
    def test_authenticated_returns_user_and_org(self):
    def test_no_membership_returns_null_org(self):

class TestExtensionSaveProfile:
    def test_create_new_candidate(self):
    def test_create_with_careers_and_educations(self):
    def test_missing_name_returns_400(self):
    def test_missing_secondary_identifier_returns_400(self):
    def test_html_stripped_from_fields(self):
    def test_duplicate_url_returns_409_with_diff(self):
    def test_possible_match_returns_409(self):
    def test_concurrent_save_same_url_returns_409(self):
    def test_cross_org_isolation(self):
    def test_rate_limit_101st_returns_429(self):
    def test_payload_too_large_returns_413(self):
    def test_source_set_to_chrome_ext(self):
    def test_consent_status_set_to_not_requested(self):
    def test_extraction_log_created(self):
    def test_update_mode_applies_confirmed_fields(self):
    def test_update_mode_wrong_org_returns_404(self):

class TestExtensionCheckDuplicate:
    def test_exact_match_by_url(self):
    def test_exact_match_by_email(self):
    def test_exact_match_by_phone(self):
    def test_possible_match_by_name_company(self):
    def test_no_match(self):
    def test_cross_org_isolation(self):

class TestExtensionSearch:
    def test_search_by_name(self):
    def test_search_by_company(self):
    def test_search_min_query_length(self):
    def test_search_pagination(self):
    def test_cross_org_isolation(self):

class TestExtensionStats:
    def test_returns_org_candidate_count(self):
    def test_cross_org_isolation(self):
```

**실행:** `uv run pytest tests/test_extension_api.py -v`

---

## Step 6: Chrome Extension — 기반 구조

### 6.1 디렉토리 생성

```bash
mkdir -p synco-extension/{popup,content,background,options,icons,styles,tests}
```

### 6.2 manifest.json

**파일:** `synco-extension/manifest.json`

확정 설계서의 manifest 그대로 구현. `host_permissions`에 synco 서버 URL 포함 (빌드 시 결정).

### 6.3 Service Worker

**파일:** `synco-extension/background/service-worker.js`

```javascript
// API 통신 래퍼
const API = {
  async getServerUrl() {
    const { serverUrl } = await chrome.storage.sync.get("serverUrl");
    return serverUrl || "https://synco.example.com";  // build-time default
  },

  async request(path, options = {}) {
    const baseUrl = await this.getServerUrl();
    const url = `${baseUrl}/candidates/extension${path}`;

    const defaults = {
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    };

    // Get CSRF token for POST requests
    if (options.method === "POST") {
      const csrfToken = await this.getCsrfToken();
      if (csrfToken) {
        defaults.headers["X-CSRFToken"] = csrfToken;
      }
    }

    const response = await fetch(url, { ...defaults, ...options });
    return response;
  },

  async getCsrfToken() {
    const { csrfToken } = await chrome.storage.local.get("csrfToken");
    return csrfToken;
  },

  // Auth status check + CSRF token refresh
  async checkAuth() { /* ... */ },

  // Save profile
  async saveProfile(data) { /* ... */ },

  // Check duplicate
  async checkDuplicate(data) { /* ... */ },

  // Search
  async search(query, page = 1) { /* ... */ },

  // Stats
  async getStats() { /* ... */ },
};

// Message routing from content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Handle async responses
  (async () => {
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
      default:
        sendResponse({ error: "Unknown message type" });
    }
  })();
  return true;  // Keep message channel open for async response
});

// On install/startup: check auth
chrome.runtime.onInstalled.addListener(() => API.checkAuth());
```

### 6.4 Options Page

**파일:** `synco-extension/options/options.html`, `options.js`

서버 URL 입력 + 연결 테스트 + 사이트별 on/off 토글.

---

## Step 7: Chrome Extension — 콘텐츠 스크립트

### 7.1 LinkedIn 파서

**파일:** `synco-extension/content/linkedin.js`

```javascript
// LinkedIn /in/* 프로필 DOM 파싱
const LinkedInParser = {
  SELECTORS: {
    name: ".text-heading-xlarge",
    headline: ".text-body-medium",
    location: ".text-body-small.inline",
    experienceSection: "#experience",
    educationSection: "#education",
    skillsSection: "#skills",
  },

  parse() {
    const result = {
      name: "", current_company: "", current_position: "",
      address: "", careers: [], educations: [], skills: [],
      external_profile_url: "",
      source_site: "linkedin",
      source_url: window.location.href,
      parse_quality: "complete",
    };

    // Name
    const nameEl = document.querySelector(this.SELECTORS.name);
    result.name = nameEl?.textContent?.trim() || "";
    if (!result.name) {
      result.parse_quality = "failed";
      return result;
    }

    // Profile URL (normalize)
    result.external_profile_url = window.location.href.split("?")[0].replace(/\/$/, "").toLowerCase();

    // Headline → current_position
    const headlineEl = document.querySelector(this.SELECTORS.headline);
    result.current_position = headlineEl?.textContent?.trim() || "";

    // Location
    const locationEl = document.querySelector(this.SELECTORS.location);
    result.address = locationEl?.textContent?.trim() || "";

    // Experience section
    try {
      result.careers = this._parseExperience();
      if (result.careers.length > 0) {
        const firstCareer = result.careers[0];
        result.current_company = firstCareer.company;
      }
    } catch (e) {
      console.warn("[synco] Experience parsing failed:", e);
    }

    // Education section
    try {
      result.educations = this._parseEducation();
    } catch (e) {
      console.warn("[synco] Education parsing failed:", e);
    }

    // Skills section
    try {
      result.skills = this._parseSkills();
    } catch (e) {
      console.warn("[synco] Skills parsing failed:", e);
    }

    // Quality assessment
    const fieldCount = [result.current_company, result.current_position, result.address].filter(Boolean).length;
    if (fieldCount < 2) {
      result.parse_quality = "partial";
    }

    return result;
  },

  _parseExperience() { /* DOM traversal for experience section */ },
  _parseEducation() { /* DOM traversal for education section */ },
  _parseSkills() { /* DOM traversal for skills section */ },
};

// Overlay UI injection
const SyncoOverlay = {
  create(type, data) { /* Create overlay element */ },
  showNewCandidate(parsedData) { /* 새 후보자 오버레이 */ },
  showExisting(candidate, diff) { /* 기존 후보자 오버레이 */ },
  showPossibleMatch(matches) { /* 가능한 매칭 오버레이 */ },
  showError(message) { /* 파싱 실패 오버레이 */ },
  remove() { /* 오버레이 제거 */ },
};

// Main entry point
async function init() {
  // 1. Check auth
  const authResult = await chrome.runtime.sendMessage({ type: "CHECK_AUTH" });
  if (!authResult?.data?.authenticated) return;

  // 2. Parse page
  const parsed = LinkedInParser.parse();

  // 3. Check duplicate
  if (parsed.parse_quality !== "failed") {
    const dupResult = await chrome.runtime.sendMessage({
      type: "CHECK_DUPLICATE",
      data: parsed,
    });

    if (dupResult?.status === "duplicate_found") {
      SyncoOverlay.showExisting(dupResult.data, dupResult.data.diff);
    } else if (dupResult?.status === "possible_match") {
      SyncoOverlay.showPossibleMatch(dupResult.data.possible_matches);
    } else {
      SyncoOverlay.showNewCandidate(parsed);
    }
  } else {
    SyncoOverlay.showError("프로필 파싱에 실패했습니다.");
  }
}

// Wait for page load (LinkedIn uses SPA)
const observer = new MutationObserver((mutations, obs) => {
  if (document.querySelector(".text-heading-xlarge")) {
    obs.disconnect();
    init();
  }
});
observer.observe(document.body, { childList: true, subtree: true });
```

### 7.2 잡코리아 파서

**파일:** `synco-extension/content/jobkorea.js`

동일 패턴: `JobKoreaParser` + `SyncoOverlay` + `init()`. 잡코리아 DOM에 맞는 셀렉터 사용.

### 7.3 사람인 파서

**파일:** `synco-extension/content/saramin.js`

동일 패턴: `SaraminParser` + `SyncoOverlay` + `init()`. 사람인 DOM에 맞는 셀렉터 사용.

### 7.4 오버레이 스타일

**파일:** `synco-extension/styles/overlay.css`

고정 위치(fixed), z-index 최상위, 사이트 스타일과 격리 (shadow DOM 또는 all: initial).

---

## Step 8: Chrome Extension — 팝업

### 8.1 팝업 UI

**파일:** `synco-extension/popup/popup.html`, `popup.js`, `popup.css`

- 검색 입력 + 결과 리스트
- 최근 저장 목록 (`chrome.storage.local`에서 로드)
- 오늘 저장 수 (local), 총 DB (서버 API)
- synco 열기 버튼 (새 탭)
- 설정 버튼 (options page)

---

## Step 9: 통합 테스트 & 마무리

### 9.1 서버 테스트 실행

```bash
uv run pytest tests/test_extension_api.py -v
```

### 9.2 Extension 수동 테스트

Chrome에서 `chrome://extensions` → 개발자 모드 → "압축 해제된 확장 프로그램을 로드합니다" → `synco-extension/` 선택.

테스트 항목:
1. Options 페이지에서 서버 URL 설정 (localhost:8000)
2. synco에 로그인
3. LinkedIn 프로필 방문 → 오버레이 표시 확인
4. "후보자로 저장" → DB 저장 확인
5. 동일 프로필 재방문 → "DB에 있음" 표시 확인
6. 팝업에서 검색 → 결과 표시 확인

### 9.3 린트 & 포맷

```bash
uv run ruff check .
uv run ruff format .
```

---

## 구현 순서 요약

| Step | 내용 | 의존성 | 검증 |
|------|------|--------|------|
| 0 | DB migration (모델 변경) | 없음 | makemigrations + migrate + 기존 테스트 |
| 1 | 인증/통계 API | Step 0 | curl/httpie 수동 테스트 |
| 2 | 중복 감지 + 검색 API | Step 0, 1 | 단위 테스트 |
| 3 | 프로필 저장 API | Step 0, 1, 2 | 단위 테스트 |
| 4 | Django 설정 (CSRF) | Step 1 | 설정 확인 |
| 5 | 서버 테스트 전체 | Step 0-4 | pytest |
| 6 | Extension 기반 (manifest, SW, options) | 없음 (병렬 가능) | 수동 로드 |
| 7 | 콘텐츠 스크립트 (3개 사이트 파서) | Step 6 | 실제 사이트 수동 테스트 |
| 8 | 팝업 UI | Step 6 | 수동 테스트 |
| 9 | 통합 테스트 | Step 0-8 | pytest + 수동 |

---

## 파일 변경 목록

### 신규 파일

| 파일 | 내용 |
|------|------|
| `candidates/views_extension.py` | Extension API 5개 뷰 + 헬퍼 |
| `candidates/serializers_extension.py` | 프로필 데이터 검증 |
| `candidates/migrations/NNNN_add_extension_fields.py` | 모델 마이그레이션 |
| `tests/test_extension_api.py` | 서버 API 테스트 |
| `synco-extension/manifest.json` | Manifest V3 |
| `synco-extension/background/service-worker.js` | API 통신 + 메시지 라우팅 |
| `synco-extension/content/linkedin.js` | LinkedIn 파서 |
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
| `candidates/models.py` | Source.CHROME_EXT 추가, external_profile_url/consent_status 필드, UniqueConstraint, ExtractionLog.Action.EXTENSION_SAVE |
| `candidates/urls.py` | `/extension/*` URL 패턴 5개 추가 |
| `candidates/services/candidate_identity.py` | `identify_candidate_from_extension()` 함수 추가 |
| `main/settings.py` | CSRF_TRUSTED_ORIGINS 추가 |
