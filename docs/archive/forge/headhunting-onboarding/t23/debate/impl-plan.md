# t23: 퍼널 클릭 가능한 내비게이션

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 개요 탭의 퍼널 시각화를 클릭 가능한 링크로 변경하고, "관심" 카운트를 추가하여 워크플로우 상태를 한눈에 파악하고 바로 이동할 수 있게 한다.

**Design spec:** `docs/forge/headhunting-onboarding/t23/design-spec.md`

**depends_on:** t19

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/views.py` | 수정 | `_build_overview_context()`에 "관심" 카운트 추가, `project_tab_contacts()`에 결과 필터 지원 |
| `projects/templates/projects/partials/tab_overview.html` | 수정 | 퍼널 항목을 클릭 가능한 `hx-get` 링크로 변경 |
| `tests/test_p20_workflow_transition.py` | 추가 | 퍼널 링크 및 관심 카운트 테스트 |

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
        # 컨택 퍼널 항목에 컨택 탭 URL이 있어야 함
        assert f"/projects/{project.pk}/tab/contacts/" in content
        # 추천 퍼널 항목에 추천 탭 URL이 있어야 함
        assert f"/projects/{project.pk}/tab/submissions/" in content

    @pytest.mark.django_db
    def test_overview_funnel_includes_interested_count(
        self, auth_client, project, candidate, user_with_org
    ):
        """퍼널에 '관심' 카운트가 포함되어야 한다."""
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="관심",
        )
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/overview/",
            HTTP_HX_REQUEST="true",
        )
        content = resp.content.decode()
        assert "관심" in content
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestFunnelNavigation -v`
Expected: FAIL — 현재 퍼널에 `hx-get` 링크가 없음

- [ ] **Step 3: _build_overview_context에 "관심" 카운트 + 서칭 카운트 추가**

`projects/views.py`의 `_build_overview_context()` (라인 435-440). 현재:

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

- [ ] **Step 5: project_tab_contacts에 결과 필터 지원 추가 (선택)**

`projects/views.py`의 `project_tab_contacts()` (라인 579-584 부근). "관심" 필터 클릭 시 `?result=관심` query param을 처리한다.

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
    if result_filter:
        completed_contacts = completed_contacts.filter(result=result_filter)
```

- [ ] **Step 6: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestFunnelNavigation -v`
Expected: All 2 tests PASS

- [ ] **Step 7: 커밋**

```bash
git add projects/views.py projects/templates/projects/partials/tab_overview.html tests/test_p20_workflow_transition.py
git commit -m "feat(projects): make funnel stages clickable with tab navigation"
```

<!-- forge:t23:구현계획:draft:2026-04-12 -->
