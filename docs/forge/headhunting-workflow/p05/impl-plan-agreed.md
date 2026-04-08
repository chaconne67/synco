# P05: Project Detail Tabs — 확정 구현계획서

> **Phase:** 5 / 6
> **선행조건:** P03 (project CRUD), P03a (JD 분석/매칭)
> **산출물:** 프로젝트 상세 6-탭 구조 (개요 + 서칭 완성, 나머지 4탭 골격)

---

## 범위 정의

### IN (P05)
- 프로젝트 상세 페이지 6-탭 구조 리팩터
- 개요 탭: JD 요약, 퍼널 카운트, 담당 컨설턴트, 최근 진행 현황
- 서칭 탭: match_candidates() 기반 읽기 전용 매칭 결과 + 컨택 이력 표시
- 골격 탭 4개: 컨택/추천/면접/오퍼 기본 목록
- 탭 전환 HTMX, 탭 배지 카운트
- match_candidates() 조직 격리 적용

### OUT (P06+)
- 컨택 예정 등록 / 상태 관리 (P06)
- 리드 담당자 / 담당자 추가 mutation
- 전용 활동 로그 모델 (audit trail)
- 서칭 탭 내 필터 수정 / 재검색
- /candidates/ 페이지로의 링크 (비격리 문제 미해결)

---

## Step 1: match_candidates() 조직 격리 수정

### projects/services/candidate_matching.py 수정

```python
def match_candidates(requirements, organization=None, limit=100):
    """requirements 기반 후보자 매칭. organization 전달 시 격리 적용."""
    from candidates.services.search import build_search_queryset, normalize_filter_spec
    from projects.services.jd_analysis import requirements_to_search_filters

    filters = requirements_to_search_filters(requirements)
    if not filters:
        return []

    loose_filters = normalize_filter_spec({
        "min_experience_years": filters.get("min_experience_years"),
        "max_experience_years": filters.get("max_experience_years"),
        "gender": filters.get("gender"),
        "birth_year_from": filters.get("birth_year_from"),
        "birth_year_to": filters.get("birth_year_to"),
    })
    qs = build_search_queryset(loose_filters)

    # 조직 격리: 슬라이스 전에 적용
    if organization:
        qs = qs.filter(owned_by=organization)

    qs = qs[:limit * 3]

    results = []
    for candidate in qs:
        score, details = _score_candidate(candidate, requirements)
        level = _score_to_level(score)
        results.append({
            "candidate": candidate,
            "score": round(score, 2),
            "level": level,
            "details": details,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]
```

### 테스트

```python
def test_match_candidates_org_isolation(org, org2, ...):
    """타 조직 후보자가 결과에 포함되지 않음."""
    # org 소속 후보자, org2 소속 후보자 생성
    # match_candidates(requirements, organization=org) 호출
    # 결과에 org2 후보자 없음 확인
```

---

## Step 2: URL 설계

### projects/urls.py 추가

```python
urlpatterns = [
    # 기존 URL 유지...
    # P05: 탭 URL
    path("<uuid:pk>/tab/overview/", views.project_tab_overview, name="project_tab_overview"),
    path("<uuid:pk>/tab/search/", views.project_tab_search, name="project_tab_search"),
    path("<uuid:pk>/tab/contacts/", views.project_tab_contacts, name="project_tab_contacts"),
    path("<uuid:pk>/tab/submissions/", views.project_tab_submissions, name="project_tab_submissions"),
    path("<uuid:pk>/tab/interviews/", views.project_tab_interviews, name="project_tab_interviews"),
    path("<uuid:pk>/tab/offers/", views.project_tab_offers, name="project_tab_offers"),
]
```

탭 전환은 HTMX: `hx-get` + `hx-target="#tab-content"`. URL push 없음 (탭은 화면 내 전환).

---

## Step 3: View 구현

### projects/views.py

모든 탭 뷰는 `@login_required` + `_get_org(request)` + `get_object_or_404(Project, pk=pk, organization=org)` 패턴을 따른다.

```python
@login_required
def project_detail(request, pk):
    """탭 wrapper + 개요 탭 인라인 렌더링."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # 탭 배지 카운트
    tab_counts = {
        "contacts": project.contacts.count(),
        "submissions": project.submissions.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
        "offers": Offer.objects.filter(submission__project=project).count(),
    }

    # 개요 탭 데이터 인라인 (초기 로드 시 추가 요청 없이)
    overview_context = _build_overview_context(project)

    return render(request, "projects/project_detail.html", {
        "project": project,
        "tab_counts": tab_counts,
        "active_tab": "overview",
        **overview_context,
    })


@login_required
def project_tab_overview(request, pk):
    """개요: JD 요약, 퍼널, 담당자, 최근 진행 현황."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    context = _build_overview_context(project)
    context["project"] = project
    return render(request, "projects/partials/tab_overview.html", context)


def _build_overview_context(project):
    """개요 탭 공통 컨텍스트."""
    # 퍼널 카운트
    funnel = {
        "contacts": project.contacts.count(),
        "submissions": project.submissions.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
        "offers": Offer.objects.filter(submission__project=project).count(),
    }

    # 최근 진행 현황 (Contact 최신 3건 + Submission 최신 2건)
    recent_contacts = (
        project.contacts
        .select_related("candidate", "consultant")
        .order_by("-contacted_at")[:3]
    )
    recent_submissions = (
        project.submissions
        .select_related("candidate", "consultant")
        .order_by("-created_at")[:2]
    )

    # 담당 컨설턴트
    consultants = project.assigned_consultants.all()

    return {
        "funnel": funnel,
        "recent_contacts": recent_contacts,
        "recent_submissions": recent_submissions,
        "consultants": consultants,
    }


@login_required
def project_tab_search(request, pk):
    """서칭: 읽기 전용 매칭 결과 + 컨택 이력 표시."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    results = []
    if project.requirements:
        from projects.services.candidate_matching import match_candidates
        results = match_candidates(project.requirements, organization=org, limit=50)

        # 컨택 이력 있는 후보자 표시
        contacted_candidate_ids = set(
            project.contacts
            .values_list("candidate_id", flat=True)
        )
        for item in results:
            item["has_contact_history"] = item["candidate"].pk in contacted_candidate_ids

    return render(request, "projects/partials/tab_search.html", {
        "project": project,
        "results": results,
        "has_requirements": bool(project.requirements),
    })


@login_required
def project_tab_contacts(request, pk):
    """컨택: Contact 목록 (기본). P06에서 완성."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    contacts = (
        project.contacts
        .select_related("candidate", "consultant")
        .order_by("-contacted_at")
    )
    return render(request, "projects/partials/tab_contacts.html", {
        "project": project,
        "contacts": contacts,
    })


@login_required
def project_tab_submissions(request, pk):
    """추천: Submission 목록 (기본). 후속 Phase에서 완성."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submissions = (
        project.submissions
        .select_related("candidate", "consultant")
        .order_by("-created_at")
    )
    return render(request, "projects/partials/tab_submissions.html", {
        "project": project,
        "submissions": submissions,
    })


@login_required
def project_tab_interviews(request, pk):
    """면접: Interview 목록 (기본). 후속 Phase에서 완성."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    interviews = (
        Interview.objects
        .filter(submission__project=project)
        .select_related("submission__candidate")
        .order_by("-scheduled_at")
    )
    return render(request, "projects/partials/tab_interviews.html", {
        "project": project,
        "interviews": interviews,
    })


@login_required
def project_tab_offers(request, pk):
    """오퍼: Offer 목록 (기본). 후속 Phase에서 완성."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    offers = (
        Offer.objects
        .filter(submission__project=project)
        .select_related("submission__candidate")
        .order_by("-created_at")
    )
    return render(request, "projects/partials/tab_offers.html", {
        "project": project,
        "offers": offers,
    })
```

---

## Step 4: Template 구조

### projects/templates/projects/project_detail.html (리팩터)

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}

{% block title %}{{ project.title }} — synco{% endblock %}

{% block content %}
<div class="p-4 lg:p-8 space-y-4">

  <!-- 상단 헤더: 뒤로가기 + 프로젝트 정보 + 상태 -->
  <div class="flex items-center justify-between">
    <a href="{% url 'projects:project_list' %}"
       hx-get="{% url 'projects:project_list' %}"
       hx-target="#main-content" hx-push-url="true"
       class="flex items-center gap-1 text-[15px] text-gray-500 hover:text-gray-700 transition">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
      </svg>
      목록
    </a>
    <div class="flex items-center gap-2">
      <a href="{% url 'projects:project_update' project.pk %}"
         hx-get="{% url 'projects:project_update' project.pk %}"
         hx-target="#main-content" hx-push-url="true"
         class="text-[15px] text-primary font-medium hover:text-primary-dark transition">
        수정
      </a>
    </div>
  </div>

  <!-- 프로젝트 제목 + 상태 뱃지 -->
  <div class="flex items-center justify-between">
    <div>
      <h1 class="text-[18px] font-bold text-gray-900">
        {{ project.client.name }} · {{ project.title }}
      </h1>
      <p class="text-[14px] text-gray-500 mt-0.5">
        고객사: {{ project.client.name }} | 
        등록자: {% if project.created_by %}{{ project.created_by.get_full_name|default:project.created_by.username }}{% else %}-{% endif %} | 
        의뢰일: {{ project.created_at|date:"m/d" }}
      </p>
    </div>
    <!-- 상태 뱃지 (기존 색상 규약 유지) -->
    <span class="text-[13px] px-2 py-0.5 rounded-full {status_color_classes}">
      {{ project.get_status_display }}
    </span>
  </div>

  <!-- 탭 바 -->
  {% include "projects/partials/detail_tab_bar.html" %}

  <!-- 탭 콘텐츠 영역 -->
  <div id="tab-content">
    {% include "projects/partials/tab_overview.html" %}
  </div>

</div>
{% endblock %}
```

### projects/templates/projects/partials/detail_tab_bar.html

```html
<div class="border-b border-gray-200 flex gap-0 overflow-x-auto">
  {% with tabs="overview:개요,search:서칭,contacts:컨택,submissions:추천,interviews:면접,offers:오퍼" %}
  <!-- 각 탭 버튼: hx-get, hx-target="#tab-content" -->
  <!-- active_tab에 따라 현재 탭 하이라이트 -->
  <!-- contacts/submissions/interviews 탭에 배지 카운트 표시 -->
  {% endwith %}
</div>
```

### projects/templates/projects/partials/tab_overview.html

```
┌─ JD 요약 ──────────────────────────────────────┐
│  포지션: {{ project.requirements.position }}     │
│  요구조건 표시 (requirements 기반)               │
│  [JD 전문 보기] [수정]                           │
├─ 진행 현황 (퍼널) ─────────────────────────────┤
│  컨택({{ funnel.contacts }}) →                   │
│  추천({{ funnel.submissions }}) →                │
│  면접({{ funnel.interviews }}) →                 │
│  오퍼({{ funnel.offers }})                       │
│  진행률 시각화 (바)                              │
├─ 담당 컨설턴트 ────────────────────────────────┤
│  {{ consultants }} 목록 (단순 이름 나열)          │
├─ 최근 진행 현황 ───────────────────────────────┤
│  Contact 최신 3건: 날짜 + 후보자명 + 채널 + 결과  │
│  Submission 최신 2건: 날짜 + 후보자명 + 상태      │
│  데이터 없으면 "진행 이력이 없습니다"             │
└────────────────────────────────────────────────┘
```

### projects/templates/projects/partials/tab_search.html

```
{% if not has_requirements %}
  <p>JD 분석이 먼저 필요합니다. 개요 탭에서 JD 분석을 실행해주세요.</p>
{% elif not results %}
  <p>매칭되는 후보자가 없습니다.</p>
{% else %}
  <p>매칭 후보자 ({{ results|length }}명)</p>
  {% for item in results %}
    <div>
      {{ item.candidate.name }}
      {{ item.candidate.current_company }} · {{ item.candidate.current_position }}
      {{ item.level }} ({{ item.score|floatformat:0 }}%)
      {% if item.has_contact_history %}
        <span class="badge">컨택 이력</span>
      {% endif %}
    </div>
  {% endfor %}
{% endif %}
```

### 골격 탭 (tab_contacts, tab_submissions, tab_interviews, tab_offers)

각 탭은 해당 모델의 기본 테이블 목록을 표시.

**tab_contacts.html:**
| 후보자 | 채널 | 결과 | 컨택일 | 담당 |

**tab_submissions.html:**
| 후보자 | 상태 | 제출일 | 담당 |

**tab_interviews.html:**
| 후보자 | 차수 | 유형 | 일정 | 결과 |

**tab_offers.html:**
| 후보자 | 연봉 | 포지션 | 시작일 | 상태 |

각 골격 탭은 데이터가 없으면 안내 메시지 표시:
- "컨택 이력이 없습니다."
- "추천 이력이 없습니다."
- "면접 이력이 없습니다."
- "오퍼 이력이 없습니다."

---

## Step 5: 테스트

### tests/test_p05_project_tabs.py

```python
"""P05: Project detail tabs tests."""

# --- Login Required ---
class TestTabLoginRequired:
    # 7개 URL (detail + 6 tabs) 에 대해 미로그인 시 redirect 검증
    def test_detail_requires_login(self): ...
    def test_tab_overview_requires_login(self): ...
    def test_tab_search_requires_login(self): ...
    def test_tab_contacts_requires_login(self): ...
    def test_tab_submissions_requires_login(self): ...
    def test_tab_interviews_requires_login(self): ...
    def test_tab_offers_requires_login(self): ...

# --- Organization Isolation ---
class TestTabOrgIsolation:
    # 각 탭 URL에서 타 조직 프로젝트 접근 시 404
    def test_detail_other_org_404(self): ...
    def test_tab_overview_other_org_404(self): ...
    def test_tab_search_other_org_404(self): ...
    def test_tab_contacts_other_org_404(self): ...
    # ... 나머지 탭 동일

# --- Tab Content ---
class TestTabContent:
    def test_detail_renders_overview_inline(self):
        """상세 진입 시 개요 탭이 추가 요청 없이 렌더링."""
        # tab_overview.html 내용이 응답에 포함

    def test_tab_overview_funnel_counts(self):
        """퍼널 카운트 정확성."""
        # Contact, Submission 생성 후 카운트 확인

    def test_tab_overview_recent_progress(self):
        """최근 진행 현황 표시."""
        # Contact 3건, Submission 2건 생성 후 표시 확인

    def test_tab_search_with_requirements(self):
        """requirements 있을 때 매칭 결과 표시."""

    def test_tab_search_without_requirements(self):
        """requirements 없을 때 안내 메시지."""

    def test_tab_search_contact_history_badge(self):
        """기존 Contact이 있는 후보자에 컨택 이력 배지 표시."""

    def test_tab_contacts_list(self):
        """컨택 목록 표시."""

    def test_tab_submissions_list(self):
        """추천 목록 표시."""

    def test_tab_interviews_via_submission(self):
        """면접 목록 (submission__project 경로)."""

    def test_tab_offers_via_submission(self):
        """오퍼 목록 (submission__project 경로)."""

    def test_tab_badge_counts(self):
        """탭 배지 카운트 정확성."""

# --- HTMX Partial ---
class TestHTMXPartial:
    def test_detail_htmx_renders_partial(self):
        """HTMX 요청 시 partial (base_partial.html 사용)."""

    def test_tab_always_partial(self):
        """탭 콘텐츠는 항상 partial (extends 없음)."""

# --- Search Org Isolation ---
class TestSearchOrgIsolation:
    def test_search_excludes_other_org_candidates(self):
        """서칭 탭 결과에 타 조직 후보자 미포함."""
        # org1 후보자, org2 후보자 생성
        # project_tab_search 호출
        # org2 후보자 이름이 응답에 없음 확인
```

---

## 산출물

| 파일 | 변경 유형 |
|------|----------|
| `projects/services/candidate_matching.py` | 수정 (조직 격리) |
| `projects/views.py` | 수정 (detail 리팩터 + 6개 탭 뷰 추가) |
| `projects/urls.py` | 수정 (6개 탭 URL 추가) |
| `projects/templates/projects/project_detail.html` | 리팩터 (탭 wrapper) |
| `projects/templates/projects/partials/detail_tab_bar.html` | 신규 |
| `projects/templates/projects/partials/tab_overview.html` | 신규 |
| `projects/templates/projects/partials/tab_search.html` | 신규 |
| `projects/templates/projects/partials/tab_contacts.html` | 신규 |
| `projects/templates/projects/partials/tab_submissions.html` | 신규 |
| `projects/templates/projects/partials/tab_interviews.html` | 신규 |
| `projects/templates/projects/partials/tab_offers.html` | 신규 |
| `tests/test_p05_project_tabs.py` | 신규 |

---

## HTMX 규약 정리

| 컨텍스트 | target | push-url |
|---------|--------|----------|
| 전체 내비 (목록, 수정) | `#main-content` | `true` |
| 탭 전환 | `#tab-content` | 없음 |
| JD 분석 결과 | `#jd-analysis-result` | 없음 |

---

## 상태 뱃지 색상

| 상태 | 색상 |
|------|------|
| 신규 | blue |
| 서칭중 | yellow |
| 추천진행 | purple |
| 면접진행 | indigo |
| 오퍼협상 | green |
| 클로즈(성공) | emerald |
| 클로즈(실패) | red |
| 클로즈(취소) | gray |
| 보류 | orange |
| 승인대기 | amber |

<!-- forge:p05:구현담금질:complete:2026-04-08T12:45:00+09:00 -->
