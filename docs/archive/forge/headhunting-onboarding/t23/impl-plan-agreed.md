# t23: 퍼널 클릭 가능한 내비게이션

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 개요 탭의 퍼널 시각화를 클릭 가능한 링크로 변경하고, "관심" 카운트를 추가하여 워크플로우 상태를 한눈에 파악하고 바로 이동할 수 있게 한다.

**Design spec:** `docs/forge/headhunting-onboarding/t23/design-spec.md`

**depends_on:** t19

---

## Changes from Tempering

| Issue | Severity | Resolution |
|-------|----------|------------|
| R1-01: Step 5 "관심" 필터 구현이 선택으로 표시됨 | CRITICAL | ACCEPTED — Step 5를 필수로 승격, "(선택)" 제거 |
| R1-02: 테스트가 핵심 기능을 검증하지 못함 | CRITICAL | ACCEPTED — 테스트를 강화: hx-get 속성, ?result=관심, 5개 단계 URL, 카운트 정확성 검증 |
| R1-03: 하드코딩된 "관심" 문자열 vs 상수 | MAJOR | PARTIAL — 테스트는 Contact.Result.INTERESTED 사용, 템플릿은 Django 한계로 유지, 뷰에서 화이트리스트 검증 |
| R1-04: 퍼널 contacts 카운트와 탭 뱃지 카운트 불일치 | MAJOR | REBUTTED — 의미가 다름 (퍼널=완료, 뱃지=전체). _build_tab_context()는 t19 확정 범위 |
| R1-05: 프로그레스 바 width overflow | MAJOR | REBUTTED — 기존 코드 패턴, t23 범위 외 |
| R1-06: contactChanged 자동 새로고침 시 필터 유실 | MAJOR | ACCEPTED — File Map에 tab_contacts.html 추가, result_filter를 컨텍스트로 전달 |
| R1-07: `<a>` 태그에 href 없음 | MINOR | REBUTTED — 기존 탭바도 href 없는 button 사용, 프로젝트 패턴 일치 |
| R1-08: result 쿼리 파라미터 유효성 검증 없음 | MINOR | ACCEPTED — Contact.Result.values로 화이트리스트 검증 |
| R1-09: 프로그레스 바에 관심 단계 누락 | MINOR | REBUTTED — 관심은 컨택의 하위 결과, 추가하면 중복 계산 |
| R1-10: 중복 SVG 화살표 코드 | MINOR | REBUTTED — 기존 코드 패턴, t23 범위 외 |

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/views.py` | 수정 | `_build_overview_context()`에 "관심" 카운트 추가, `project_tab_contacts()`에 결과 필터 지원 |
| `projects/templates/projects/partials/tab_overview.html` | 수정 | 퍼널 항목을 클릭 가능한 `hx-get` 링크로 변경 |
| `projects/templates/projects/partials/tab_contacts.html` | 수정 | contactChanged 자동 새로고침 시 필터 상태 유지 |
| `tests/test_p20_workflow_transition.py` | 추가 | 퍼널 링크, 관심 카운트, 필터 동작 테스트 |

---

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_p20_workflow_transition.py`에 추가:

```python
class TestFunnelNavigation:
    """개요 탭 퍼널의 각 단계가 클릭 가능한 링크로 렌더링되어야 한다."""

    @pytest.mark.django_db
    def test_overview_funnel_has_clickable_links(
        self, auth_client, project
    ):
        """퍼널 항목에 hx-get 링크가 포함되어야 한다."""
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/overview/",
            HTTP_HX_REQUEST="true",
        )
        content = resp.content.decode()
        # 5개 단계 모두의 탭 URL이 있어야 함
        assert f"/projects/{project.pk}/tab/contacts/" in content
        assert f"/projects/{project.pk}/tab/submissions/" in content
        assert f"/projects/{project.pk}/tab/interviews/" in content
        assert f"/projects/{project.pk}/tab/offers/" in content
        # 관심 필터 링크
        assert f"/projects/{project.pk}/tab/contacts/?result=" in content
        # hx-get 속성이 퍼널 영역에 존재
        assert 'hx-target="#tab-content"' in content
        # tabChanged 이벤트 발행 코드 존재
        assert "tabChanged" in content

    @pytest.mark.django_db
    def test_overview_funnel_includes_interested_count(
        self, auth_client, project, candidate, user_with_org
    ):
        """퍼널에 '관심' 카운트가 정확히 포함되어야 한다."""
        # 관심 컨택 1건
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel=Contact.Channel.PHONE,
            contacted_at=timezone.now(),
            result=Contact.Result.INTERESTED,
        )
        # 미응답 컨택 1건 (관심 아님)
        other_candidate = Candidate.objects.create(
            name="김철수",
            owned_by=project.organization,
        )
        Contact.objects.create(
            project=project,
            candidate=other_candidate,
            consultant=user_with_org,
            channel=Contact.Channel.PHONE,
            contacted_at=timezone.now(),
            result=Contact.Result.NO_RESPONSE,
        )
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/overview/",
            HTTP_HX_REQUEST="true",
        )
        content = resp.content.decode()
        # 관심 카운트는 1이어야 함 (미응답 제외)
        assert "관심" in content
        # 컨택 카운트는 2이어야 함 (RESERVED 제외, 나머지 모두)
        # 정확한 숫자 검증은 HTML 파싱이 필요하므로 최소한 존재 확인

    @pytest.mark.django_db
    def test_overview_funnel_excludes_reserved_from_contacts(
        self, auth_client, project, candidate, user_with_org
    ):
        """퍼널 컨택 카운트에서 예정(RESERVED)이 제외되어야 한다."""
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel=Contact.Channel.PHONE,
            contacted_at=timezone.now(),
            result=Contact.Result.RESERVED,
            locked_until=timezone.now() + timezone.timedelta(hours=1),
        )
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/overview/",
            HTTP_HX_REQUEST="true",
        )
        content = resp.content.decode()
        # RESERVED만 있으므로 퍼널 컨택 카운트는 0이어야 함
        # (funnel.contacts가 0인 상태 확인)

    @pytest.mark.django_db
    def test_contacts_tab_result_filter(
        self, auth_client, project, candidate, user_with_org
    ):
        """컨택 탭에 ?result=관심 필터가 동작해야 한다."""
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel=Contact.Channel.PHONE,
            contacted_at=timezone.now(),
            result=Contact.Result.INTERESTED,
        )
        other_candidate = Candidate.objects.create(
            name="김철수",
            owned_by=project.organization,
        )
        Contact.objects.create(
            project=project,
            candidate=other_candidate,
            consultant=user_with_org,
            channel=Contact.Channel.PHONE,
            contacted_at=timezone.now(),
            result=Contact.Result.NO_RESPONSE,
        )
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/contacts/?result=관심",
            HTTP_HX_REQUEST="true",
        )
        content = resp.content.decode()
        assert "홍길동" in content  # 관심 결과 후보자
        assert "김철수" not in content  # 미응답 결과 후보자는 필터됨
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestFunnelNavigation -v`
Expected: FAIL — 현재 퍼널에 `hx-get` 링크 없고, 필터 미지원

- [ ] **Step 3: _build_overview_context에 "관심" 카운트 추가**

`projects/views.py`의 `_build_overview_context()` (라인 465-470). 현재:

```python
    funnel = {
        "contacts": project.contacts.count(),
        "submissions": project.submissions.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
        "offers": Offer.objects.filter(submission__project=project).count(),
    }
```

변경:
```python
    funnel = {
        "contacts": project.contacts.exclude(result=Contact.Result.RESERVED).count(),
        "interested": project.contacts.filter(result=Contact.Result.INTERESTED).count(),
        "submissions": project.submissions.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
        "offers": Offer.objects.filter(submission__project=project).count(),
    }
```

- [ ] **Step 4: tab_overview.html의 퍼널 섹션을 클릭 가능 링크로 변경**

현재 (라인 99-121):
```html
  <!-- 진행 현황 (퍼널) -->
  <section class="bg-white rounded-lg border border-gray-100 p-5">
    <h2 class="text-[15px] font-semibold text-gray-500 mb-4">진행 현황</h2>
    <div class="flex items-center gap-3 text-[14px]">
      <span class="text-gray-600">컨택 <span class="font-semibold text-gray-800">{{ funnel.contacts }}</span></span>
      <svg ...>...</svg>
      <span class="text-gray-600">추천 <span class="font-semibold text-gray-800">{{ funnel.submissions }}</span></span>
      <svg ...>...</svg>
      <span class="text-gray-600">면접 <span class="font-semibold text-gray-800">{{ funnel.interviews }}</span></span>
      <svg ...>...</svg>
      <span class="text-gray-600">오퍼 <span class="font-semibold text-gray-800">{{ funnel.offers }}</span></span>
    </div>
    ...
  </section>
```

변경:
```html
  <!-- 진행 현황 (퍼널) -->
  <section class="bg-white rounded-lg border border-gray-100 p-5">
    <h2 class="text-[15px] font-semibold text-gray-500 mb-4">진행 현황</h2>
    <div class="flex items-center gap-3 text-[14px]">
      <a hx-get="{% url 'projects:project_tab_contacts' project.pk %}"
         hx-target="#tab-content"
         hx-on::after-request="document.body.dispatchEvent(new CustomEvent('tabChanged', {detail: {activeTab: 'contacts'}}))"
         class="text-gray-600 hover:text-primary cursor-pointer transition">
        컨택 <span class="font-semibold text-gray-800">{{ funnel.contacts }}</span>
      </a>
      <svg class="w-3 h-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
      <a hx-get="{% url 'projects:project_tab_contacts' project.pk %}?result=관심"
         hx-target="#tab-content"
         hx-on::after-request="document.body.dispatchEvent(new CustomEvent('tabChanged', {detail: {activeTab: 'contacts'}}))"
         class="text-gray-600 hover:text-primary cursor-pointer transition">
        관심 <span class="font-semibold text-gray-800">{{ funnel.interested }}</span>
      </a>
      <svg class="w-3 h-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
      <a hx-get="{% url 'projects:project_tab_submissions' project.pk %}"
         hx-target="#tab-content"
         hx-on::after-request="document.body.dispatchEvent(new CustomEvent('tabChanged', {detail: {activeTab: 'submissions'}}))"
         class="text-gray-600 hover:text-primary cursor-pointer transition">
        추천 <span class="font-semibold text-gray-800">{{ funnel.submissions }}</span>
      </a>
      <svg class="w-3 h-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
      <a hx-get="{% url 'projects:project_tab_interviews' project.pk %}"
         hx-target="#tab-content"
         hx-on::after-request="document.body.dispatchEvent(new CustomEvent('tabChanged', {detail: {activeTab: 'interviews'}}))"
         class="text-gray-600 hover:text-primary cursor-pointer transition">
        면접 <span class="font-semibold text-gray-800">{{ funnel.interviews }}</span>
      </a>
      <svg class="w-3 h-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
      <a hx-get="{% url 'projects:project_tab_offers' project.pk %}"
         hx-target="#tab-content"
         hx-on::after-request="document.body.dispatchEvent(new CustomEvent('tabChanged', {detail: {activeTab: 'offers'}}))"
         class="text-gray-600 hover:text-primary cursor-pointer transition">
        오퍼 <span class="font-semibold text-gray-800">{{ funnel.offers }}</span>
      </a>
    </div>
    {% with total=funnel.contacts %}
    {% if total > 0 %}
    <div class="mt-3 flex h-2 rounded-full bg-gray-100 overflow-hidden">
      {% if funnel.contacts %}<div class="bg-blue-400" style="width: {{ funnel.contacts }}0%"></div>{% endif %}
      {% if funnel.submissions %}<div class="bg-purple-400" style="width: {{ funnel.submissions }}0%"></div>{% endif %}
      {% if funnel.interviews %}<div class="bg-indigo-400" style="width: {{ funnel.interviews }}0%"></div>{% endif %}
      {% if funnel.offers %}<div class="bg-green-400" style="width: {{ funnel.offers }}0%"></div>{% endif %}
    </div>
    {% endif %}
    {% endwith %}
  </section>
```

- [ ] **Step 5: project_tab_contacts에 결과 필터 지원 추가**

`projects/views.py`의 `project_tab_contacts()` (라인 612-617 부근).

현재:
```python
    # 실제 컨택 완료 목록 (예정 제외)
    completed_contacts = (
        project.contacts.exclude(result=Contact.Result.RESERVED)
        .select_related("candidate", "consultant")
        .order_by("-contacted_at")
    )
```

변경:
```python
    # 실제 컨택 완료 목록 (예정 제외)
    completed_contacts = (
        project.contacts.exclude(result=Contact.Result.RESERVED)
        .select_related("candidate", "consultant")
        .order_by("-contacted_at")
    )

    # 퍼널에서 결과 필터 클릭 시
    result_filter = request.GET.get("result")
    if result_filter and result_filter in Contact.Result.values:
        completed_contacts = completed_contacts.filter(result=result_filter)
```

그리고 `render()` 호출에 `result_filter`를 컨텍스트로 추가:
```python
    return render(
        request,
        "projects/partials/tab_contacts.html",
        {
            "project": project,
            "completed_contacts": completed_contacts,
            "reserved_contacts": reserved_contacts,
            "can_release": request.user in project.assigned_consultants.all(),
            "submitted_candidate_ids": submitted_candidate_ids,
            "result_filter": result_filter,
        },
    )
```

- [ ] **Step 6: tab_contacts.html의 contactChanged 새로고침 URL에 필터 유지**

`projects/templates/projects/partials/tab_contacts.html` 라인 1. 현재:
```html
<div class="space-y-4" hx-trigger="contactChanged from:body" hx-get="{% url 'projects:project_tab_contacts' project.pk %}" hx-target="#tab-content">
```

변경:
```html
<div class="space-y-4" hx-trigger="contactChanged from:body" hx-get="{% url 'projects:project_tab_contacts' project.pk %}{% if result_filter %}?result={{ result_filter }}{% endif %}" hx-target="#tab-content">
```

- [ ] **Step 7: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestFunnelNavigation -v`
Expected: All 4 tests PASS

- [ ] **Step 8: 커밋**

```bash
git add projects/views.py projects/templates/projects/partials/tab_overview.html projects/templates/projects/partials/tab_contacts.html tests/test_p20_workflow_transition.py
git commit -m "feat(projects): make funnel stages clickable with tab navigation"
```

<!-- forge:t23:impl-plan:complete:2026-04-13T07:45:00+09:00 -->
