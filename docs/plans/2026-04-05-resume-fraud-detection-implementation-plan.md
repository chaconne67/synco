# 이력서 위조 감지 & 헤드헌터 코멘트 시스템 — 구현 계획

## Context

업무 담당자의 실무 페이크 사례 피드백을 기반으로, 자동 감지 규칙(학력/경력/생년 위조 패턴)과 수동 판정/코멘트 기능을 추가한다. 설계 문서: `docs/plans/2026-04-05-resume-fraud-detection-design.md`

**코드 리뷰 1차 반영:**
- `check_career_consolidation()` 제외 (Step 2 정규화의 same-company merge와 충돌, 오탐 위험)
- cross-version 규칙은 `apply_cross_version_comparison()` 경로에서만 실행 (중복 플래그 방지)
- `_build_candidate_snapshot()`에 `birth_year` 추가 필요
- 메인 검색 목록에도 `recommendation_status` 배지/필터 추가

**코드 리뷰 2차 반영:**
- 메인 검색 필터를 세션 기반 검색 스키마(`FILTER_SPEC_TEMPLATE` → `normalize_filter_spec()` → `build_search_queryset()`)에 완전 통합
- 코멘트 저장 응답에 `hx-swap-oob`로 헤더 배지도 동시 갱신
- `reason_codes` 전송을 체크박스 `name="reason_codes"` + `request.POST.getlist()` 방식으로 확정
- `voice-input.js`를 `base.html`에서 로드하고 `htmx:afterSettle` 이벤트로 재초기화

---

## Phase 1: 모델 & 마이그레이션

### Step 1.1: Candidate 모델에 RecommendationStatus 추가

**파일:** `candidates/models.py`

- `Candidate` 클래스 내부에 `RecommendationStatus` choices 추가 (line ~186, 기존 `ResumeReferenceDateSource` 뒤):
  ```python
  class RecommendationStatus(models.TextChoices):
      PENDING = "pending", "미결정"
      RECOMMENDED = "recommended", "추천"
      NOT_RECOMMENDED = "not_recommended", "비추천"
      ON_HOLD = "on_hold", "보류"
  ```
- `validation_status` 필드 뒤 (line ~320)에 `recommendation_status` 필드 추가:
  ```python
  recommendation_status = models.CharField(
      max_length=20,
      choices=RecommendationStatus.choices,
      default=RecommendationStatus.PENDING,
      db_index=True,
  )
  ```

### Step 1.2: CandidateComment 모델 추가

**파일:** `candidates/models.py` (DiscrepancyReport 뒤, 파일 끝부분)

- `REASON_CODES` 상수 dict 추가 (모듈 레벨)
- `CandidateComment(BaseModel)` 모델: candidate FK, author FK(`settings.AUTH_USER_MODEL`, SET_NULL), recommendation_status, reason_codes(JSONField), content(TextField), input_method(CharField)
- `db_table = "candidate_comments"`, `ordering = ["-created_at"]`

### Step 1.3: 마이그레이션 생성 & 적용

```bash
uv run python manage.py makemigrations candidates
uv run python manage.py migrate
```

---

## Phase 2: 자동 감지 규칙

### Step 2.1: `check_education_gaps()` — 학력 자기일관성 규칙

**파일:** `data_extraction/services/extraction/integrity.py` (기존 `check_career_education_overlap()` 뒤, line ~474)

```python
def check_education_gaps(educations: list[dict]) -> list[dict]:
```

- 대학원 키워드("석사", "박사", "MBA", "master", "doctor", "ph.d", "M.S.", "M.A." 등) 매칭
- 학부 키워드("학사", "bachelor", "B.S.", "B.A.", "학부", "공학사", "이학사" 등) 매칭
- 대학원 있고 학부 없음 → YELLOW, type `"EDUCATION_GAP"`
- `end_year` 있고 `start_year` 없음 → YELLOW, type `"EDUCATION_GAP"`

**파이프라인 통합:** `run_integrity_pipeline()` Step 3 영역 (line ~925), 3b 뒤에:
```python
# 3d: Education gaps
edu_gap_flags = check_education_gaps(normalized_educations)
all_flags.extend(edu_gap_flags)
```

### Step 2.2: 멀티캠퍼스 대학 데이터 구축

**파일:** `data_extraction/data/multi_campus_universities.json` (신규, 디렉토리도 생성)

웹 검색으로 9개 대학(고려대, 연세대, 성균관대, 한양대, 건국대, 동국대, 홍익대, 단국대, 경희대)의 캠퍼스별 학과 데이터 수집. `docs/research/korean-university-rankings.md` 티어 분류 연동.

### Step 2.3: `check_campus_match()` — 캠퍼스 매칭 규칙

**파일:** `data_extraction/services/extraction/integrity.py`

```python
def check_campus_match(educations: list[dict]) -> list[dict]:
```

- 모듈 레벨 캐시로 JSON 로드 (`_load_multi_campus_data()`)
- institution에서 대학명+별칭 매칭 → 캠퍼스 키워드 탐색
- 캠퍼스 미기재 → YELLOW, type `"CAMPUS_MISSING"`
- 학과가 지방캠퍼스 전용 → RED, type `"CAMPUS_DEPARTMENT_MATCH"`

**파이프라인 통합:** Step 2.1 바로 뒤:
```python
# 3e: Campus match
campus_flags = check_campus_match(normalized_educations)
all_flags.extend(campus_flags)
```

### Step 2.4: `check_birth_year_consistency()` — 생년 cross-version 규칙

**핵심: `run_integrity_pipeline()` 안이 아닌 `apply_cross_version_comparison()` 경로에서 실행.**

**파일 1:** `candidates/services/candidate_identity.py`
- `_build_candidate_snapshot()` (line 163)에 `"birth_year": candidate.birth_year` 추가

**파일 2:** `data_extraction/services/extraction/integrity.py`
```python
def check_birth_year_consistency(
    current_birth_year: int | None,
    previous_birth_year: int | None,
) -> list[dict]:
```
- 둘 다 non-None이고 다르면 → RED, type `"BIRTH_YEAR_MISMATCH"`, field `"birth_year"`

**파일 3:** `data_extraction/services/pipeline.py`
- `apply_cross_version_comparison()` (line ~182)에서 `compare_versions()` 호출 뒤:
```python
birth_flags = check_birth_year_consistency(
    extracted.get("birth_year"),
    previous_data.get("birth_year"),
)
cross_version_flags.extend(birth_flags)
```

### Step 2.5: `_check_career_deleted()` 보강

**파일:** `data_extraction/services/extraction/integrity.py`

기존 `_check_career_deleted()` (line ~570) 수정. 플래그 생성 후 후처리:
```python
if len(flags) >= 2:
    for flag in flags:
        flag["severity"] = "RED"
        flag["reasoning"] = "2건 이상의 경력이 동시 삭제됨 — 의도적 은폐 가능성 높음"
```

기존 `_check_career_period_changed()` (line ~614)의 패턴과 동일.

---

## Phase 3: 뷰 & URL

### Step 3.1: 코멘트 생성 뷰

**파일:** `candidates/views.py`

`comment_create(request, pk)` 뷰 추가:
- POST만 허용, `@login_required`
- `transaction.atomic()`으로 CandidateComment 생성 + Candidate.recommendation_status 업데이트
- `reason_codes`는 `request.POST.getlist("reason_codes")` 로 수신 (체크박스 복수 값)
- HTMX response: `_comment_list.html` partial + **`hx-swap-oob`로 헤더 배지 갱신**

```python
def comment_create(request, pk):
    # ... CandidateComment 생성, Candidate.recommendation_status 업데이트 ...
    
    comments = candidate.comments.select_related("author").all()
    # 메인 응답(코멘트 리스트) + OOB(헤더 배지)를 한 템플릿에서 렌더링
    return render(request, "candidates/partials/_comment_response.html", {
        "candidate": candidate,
        "comments": comments,
        "reason_codes": REASON_CODES,
    })
```

`_comment_response.html`은 `_comment_list.html` 본문 + OOB 배지를 포함:
```html
{# 메인 응답: comment-list swap #}
{% include "candidates/partials/_comment_list.html" %}

{# OOB: 헤더 배지 동시 갱신 #}
<span id="recommendation-badge" hx-swap-oob="true">
  {% include "candidates/partials/_recommendation_badge.html" %}
</span>
```

### Step 3.2: 검색 필터 스키마 통합

**파일:** `candidates/services/search.py`

`recommendation_status`를 세션 기반 검색 파이프라인 전체에 관통시킨다:

**3.2a) `FILTER_SPEC_TEMPLATE` (line ~15)에 추가:**
```python
"recommendation_status": [],  # ["recommended", "on_hold", "pending"] 등 리스트
```

리스트 형태로 지원. 기존 `name_keywords: []` 패턴과 일관.
- "추천만" → `["recommended"]`
- "비추천 제외" → `["recommended", "on_hold", "pending"]`
- 필터 없음 → `[]`

**3.2b) `FILTER_SCHEMA_TEMPLATE` (LLM 프롬프트용)에 추가:**
```
recommendation_status: ["recommended", "not_recommended", "on_hold", "pending"] 중 해당하는 값들의 리스트
  — 추천 상태 필터. "추천만 보여줘" → ["recommended"]. "비추천 제외" → ["recommended", "on_hold", "pending"].
  — 빈 리스트 [] = 필터 없음 (전체)
```

**3.2b-2) `_SEARCH_SYSTEM_PROMPT_TEMPLATE` 내 하드코딩된 filters JSON 예시 (line ~178)에도 추가:**

`search.py`의 `_SEARCH_SYSTEM_PROMPT_TEMPLATE`에는 `{filter_schema}` 외에 출력 형식 예시로 filters JSON이 별도 하드코딩되어 있다 (line 178~199). 이 예시에도 `"recommendation_status": []` 를 추가해야 LLM이 출력에서 안정적으로 이 필드를 포함한다.

**3.2c) `normalize_filter_spec()` (line ~212)에 클리너 추가:**
```python
valid_rec = {"recommended", "not_recommended", "on_hold", "pending"}
raw_rec = spec.get("recommendation_status", [])
if isinstance(raw_rec, str):
    raw_rec = [raw_rec]  # 단일값 → 리스트 변환
normalized["recommendation_status"] = [v for v in raw_rec if v in valid_rec]
```

**3.2d) `build_search_queryset()` (line ~291)에 필터 조건 추가:**
```python
if normalized.get("recommendation_status"):
    qs = qs.filter(recommendation_status__in=normalized["recommendation_status"])
```

**3.2e) 카테고리 탭에 session_id 스레딩:**

현재 카테고리 링크(`search_content.html` line ~42)는 `?category=XX`만 전달하고 `session_id`가 빠져 있어, 탭 전환 시 세션 필터가 끊긴다.

**파일:** `candidates/templates/candidates/partials/search_content.html`
- 카테고리 링크에 `&session_id={{ session.pk }}` 추가 (세션이 있을 때)

**파일:** `candidates/views.py` — `candidate_list()` (line ~270)
- 카테고리 탭 분기(`if category_filter:`)에서도 세션 필터가 있으면 AND 적용.
- **기존 `select_related`/`prefetch_related` 체인을 유지한 채 필터만 추가.** 현재 카테고리 분기(line ~271)의 prefetch 구조를 그대로 두고 `.filter()`만 얹는다:
```python
if category_filter:
    qs = (
        Candidate.objects.select_related("primary_category")
        .prefetch_related("educations", "careers", "categories", _self_consistency_prefetch())
        .filter(categories__name=category_filter)
        .distinct()
        .order_by("-updated_at")
    )
    # 세션 필터 중 recommendation_status만 추가 적용
    if session and has_active_filters(filters):
        rec_statuses = filters.get("recommendation_status", [])
        if rec_statuses:
            qs = qs.filter(recommendation_status__in=rec_statuses)
```
`build_search_queryset()`는 카테고리/키워드/경력 등 전체 필터를 재적용하므로 카테고리 탭에서 중복 호출하면 충돌한다. 카테고리 탭 분기에서는 세션 필터 중 `recommendation_status`만 직접 적용하는 것이 안전하다.

### Step 3.3: 기존 뷰 수정

**파일:** `candidates/views.py`

- `review_detail()` (line 107): context에 `comments`, `reason_codes` 추가
- `review_list()` (line 66): `recommendation_status` GET 파라미터 필터 추가
- `candidate_list()` (line 242): GET 파라미터 `rec_status`로 UI 탭 필터 지원 (세션 필터와 AND 동작)
- `candidate_detail()`: context에 `comments`, `reason_codes` 추가

### Step 3.4: URL 패턴

**파일:** `candidates/urls.py`

```python
path("<uuid:pk>/comments/", views.comment_create, name="comment_create"),
```

---

## Phase 4: 템플릿

### Step 4.1: `_comment_section.html` (신규)

**파일:** `candidates/templates/candidates/partials/_comment_section.html`

- 추천/비추천/보류 라디오 버튼 (`name="recommendation_status"`)
- 사유 코드 체크박스 그리드 (`name="reason_codes"`, 복수 선택 → `getlist()`)
  ```html
  {% for code, label in reason_codes.items %}
  <label><input type="checkbox" name="reason_codes" value="{{ code }}"> {{ label }}</label>
  {% endfor %}
  ```
- textarea (`name="content"`) + 마이크 버튼 (`data-voice-input`)
- hidden input (`name="input_method"` value="text", JS가 voice로 변경)
- `hx-post` → comment_create URL, `hx-target="#comment-list"`, `hx-swap="innerHTML"`

### Step 4.2: `_comment_list.html` (신규)

**파일:** `candidates/templates/candidates/partials/_comment_list.html`

- 시간순 코멘트 이력 (작성자, 일시, 판정 배지, 사유 코드 라벨, 본문)

### Step 4.3: `_comment_response.html` (신규)

**파일:** `candidates/templates/candidates/partials/_comment_response.html`

코멘트 저장 후 HTMX 응답용. 코멘트 리스트 + OOB 헤더 배지를 한 응답에 포함:
```html
{% include "candidates/partials/_comment_list.html" %}
<span id="recommendation-badge" hx-swap-oob="true">
  {% include "candidates/partials/_recommendation_badge.html" %}
</span>
```

### Step 4.4: `_recommendation_badge.html` (신규)

**파일:** `candidates/templates/candidates/partials/_recommendation_badge.html`

추천 상태 배지 컴포넌트 (상세페이지 헤더 + OOB 갱신 + 카드에서 공유):
```html
{% if candidate.recommendation_status == "recommended" %}
  <span class="text-sm px-2 py-0.5 rounded-full bg-green-100 text-green-700">추천</span>
{% elif candidate.recommendation_status == "not_recommended" %}
  <span class="text-sm px-2 py-0.5 rounded-full bg-red-100 text-red-700">비추천</span>
{% elif candidate.recommendation_status == "on_hold" %}
  <span class="text-sm px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700">보류</span>
{% endif %}
```

### Step 4.5: 상세페이지에 코멘트 섹션 포함

**파일:** `candidates/templates/candidates/partials/review_detail_content.html`

- 헤더(line ~10)에 `<span id="recommendation-badge">{% include "_recommendation_badge.html" %}</span>` 추가
- 컨텐츠 하단에 `{% include "_comment_section.html" %}` + `<div id="comment-list">{% include "_comment_list.html" %}</div>`

**파일:** `candidates/templates/candidates/partials/candidate_detail_content.html`
- 동일하게 코멘트 섹션 포함

### Step 4.6: 목록 페이지 필터

**파일:** `candidates/templates/candidates/partials/review_list_content.html`
- 기존 validation_status 탭 옆에 recommendation_status 필터 탭 추가
- **"더 보기" 페이지네이션 URL에 `rec_status` GET 파라미터 스레딩** (현재 `status`와 `page`만 전달 중, line ~81)
  ```html
  hx-get="?status={{ status_filter }}&rec_status={{ rec_status_filter }}&page={{ page|add:1 }}"
  ```

**파일:** `candidates/views.py` — `review_list()` (line ~66)
- `rec_status` GET 파라미터를 받아 queryset에 `.filter(recommendation_status=...)` 적용
- context에 `rec_status_filter` 전달 (탭 활성 상태 + 페이지네이션 URL 유지용)

**파일:** `candidates/templates/candidates/partials/search_content.html`
- recommendation_status 필터 탭 추가 (카테고리 탭과 유사한 UI)
- 카테고리 링크에 `session_id` 스레딩 (Step 3.2e)
- 무한스크롤 URL에 `rec_status` 파라미터 스레딩

**파일:** 후보자 카드 템플릿 (`candidate_card.html`)
- `{% include "_recommendation_badge.html" %}` 로 배지 표시

---

## Phase 5: 음성 입력 JS

### Step 5.1: `voice-input.js` (신규)

**파일:** `candidates/static/candidates/voice-input.js`

- IIFE 패턴 (기존 `chatbot.js`와 동일)
- Web Speech API (`SpeechRecognition`) 기반 브라우저 네이티브 음성 인식
- `lang: 'ko-KR'`, `continuous: true`
- 마이크 버튼(`[data-voice-input]`) 토글, textarea에 실시간 반영
- `input_method` hidden 필드를 `"voice"`로 변경
- 브라우저 미지원 시 마이크 버튼 숨김

**초기화 패턴:**
```javascript
(function() {
  "use strict";
  function initVoiceInput() {
    const btn = document.querySelector('[data-voice-input]');
    if (!btn || btn.dataset.voiceInitialized) return;
    btn.dataset.voiceInitialized = "true";
    // ... SpeechRecognition 바인딩
  }
  initVoiceInput();
  document.addEventListener('htmx:afterSettle', initVoiceInput);
})();
```

- `htmx:afterSettle`로 partial swap 후 재초기화 (상세페이지는 HTMX로 `#main-content`만 교체됨)
- `data-voiceInitialized`로 중복 초기화 방지

### Step 5.2: `base.html`에 스크립트 로드

**파일:** `templates/common/base.html` (line ~167, `{% block extra_js %}` 영역)

기존 `chatbot_fab.html` include 근처에 추가:
```html
<script src="{% static 'candidates/voice-input.js' %}"></script>
```

`base.html`에서 로드하므로 HTMX partial swap에도 스크립트가 유지됨.

---

## Phase 6: 테스트

### Step 6.1: 자동 감지 규칙 테스트

**파일:** `tests/test_fraud_detection.py` (신규)

순수 코드 함수이므로 직접 호출 테스트 (LLM mock 불필요):
- `TestEducationGaps`: 대학원만/학부+대학원/start_year 누락 케이스
- `TestCampusMatch`: 비멀티캠퍼스/캠퍼스 미기재/지방캠퍼스 학과/별칭 매칭
- `TestBirthYearConsistency`: 동일/불일치/None 케이스
- `TestCareerDeletedEnhanced`: 1건 삭제(기존 severity 유지)/2건 이상(RED 승격)

### Step 6.2: 코멘트 시스템 테스트

**파일:** `tests/test_candidate_comments.py` (신규)

Django TestCase:
- POST로 코멘트 생성 → candidate.recommendation_status 업데이트 확인
- 코멘트 이력 순서 확인
- reason_codes JSON 직렬화 확인
- 미인증 접근 리다이렉트 확인

### Step 6.3: 전체 테스트 실행

```bash
uv run pytest -v
```

---

## Phase 7: 설계 문서 업데이트 & 커밋

- `docs/plans/2026-04-05-resume-fraud-detection-design.md` 리뷰 반영 사항 업데이트 (career_consolidation 제외, 아키텍처 명확화)
- 커밋

---

## 실행 순서 & 병렬화

```
Phase 1 (모델)  →  Phase 3 (뷰/URL)  →  Phase 4 (템플릿)  →  Phase 5 (JS)
                                                                    ↓
Phase 2 (감지 규칙, Phase 1과 병렬 가능)                      Phase 6 (테스트)
  2.1 education_gaps  ─┐
  2.2 campus data     ─┼→ 2.3 campus_match (2.2 필요)
  2.4 birth_year      ─┤
  2.5 career_deleted   ─┘
```

- **Phase 1과 Phase 2는 병렬 가능** (서로 의존성 없음)
- Phase 2.3은 2.2(데이터 파일) 완료 후
- Phase 3, 4, 5는 순차 (뷰 → 템플릿 → JS)
- Phase 6은 모든 구현 완료 후

---

## 검증 방법

1. **자동 감지:** `uv run pytest tests/test_fraud_detection.py -v` 로 규칙 단위 테스트
2. **코멘트 시스템:** `uv run pytest tests/test_candidate_comments.py -v` 로 CRUD 테스트
3. **전체 회귀:** `uv run pytest -v`
4. **UI 검증:** `/browse`로 리뷰 상세페이지 접속 → 코멘트 폼 작동, 판정 저장, 이력 표시 확인
5. **목록 필터:** 리뷰 목록 & 메인 검색 목록에서 recommendation_status 필터 동작 확인
