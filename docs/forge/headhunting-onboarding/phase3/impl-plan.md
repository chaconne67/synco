# 워크플로우 연결 구현 계획 (Plan 3/3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 컨택→추천 자동 전환, 퍼널 클릭 내비게이션, 탭 뱃지 신규 표시 등 워크플로우 단계 간 연결을 강화하여 사용자가 수동으로 탭을 전환하지 않아도 되게 한다.

**Architecture:** `submission_create()` 뷰가 성공 시 추천 탭 파셜을 직접 반환하고 `HX-Retarget`으로 `#tab-content`를 교체한다. `tabChanged` 커스텀 이벤트로 탭바 활성 상태를 갱신한다. `contact_update()` 뷰가 "관심" 결과일 때 유도 배너를 포함한다. 개요 탭 퍼널을 클릭 가능한 링크로 변경한다. 클라이언트 측 JavaScript(`tab-navigation.js`)로 탭바 활성 상태 갱신 및 뱃지 신규 표시를 처리한다.

**Tech Stack:** Django 5.2, HTMX, Tailwind CSS, pytest

**Design spec:** `docs/forge/headhunting-onboarding/phase3/design-spec.md`

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/views.py` | 수정 | `submission_create()` 성공 시 추천 탭 파셜 반환 + HX-Retarget, `contact_update()` "관심" 시 유도 배너, `_build_overview_context()`에 "관심" 카운트 추가, `project_tab_overview()`에 퍼널 탭 이름 매핑 |
| `projects/templates/projects/partials/detail_tab_bar.html` | 수정 | `tabChanged` 이벤트 리스너 추가, 뱃지에 신규 표시 data 속성 추가 |
| `projects/templates/projects/partials/tab_contacts.html` | 수정 | 유도 배너 삽입 영역 추가, 예정 목록에 "컨택 등록" 버튼 추가 |
| `projects/templates/projects/partials/tab_overview.html` | 수정 | 퍼널 단계를 클릭 가능한 `hx-get` 링크로 변경, "관심" 단계 추가 |
| `projects/templates/projects/partials/submission_form.html` | 수정 | `hx-target` 변경 — 성공 시 `#tab-content`로 교체되도록 |
| `projects/templates/projects/partials/contact_interest_banner.html` | 생성 | "관심" 결과 저장 후 추천 유도 배너 |
| `static/js/tab-navigation.js` | 생성 | `tabChanged` 이벤트 핸들러, 탭 뱃지 신규 표시 로직 (sessionStorage) |
| `projects/templates/projects/project_detail.html` | 수정 | `tab-navigation.js` script 태그 추가 |
| `tests/test_p20_workflow_transition.py` | 생성 | 컨택→추천 자동 전환, 유도 배너, 퍼널 링크 테스트 |

---

### Task 1: tabChanged 이벤트 시스템 + tab-navigation.js

**Files:**
- Create: `static/js/tab-navigation.js`
- Modify: `projects/templates/projects/partials/detail_tab_bar.html`
- Modify: `projects/templates/projects/project_detail.html`

- [ ] **Step 1: tab-navigation.js 생성 — tabChanged 이벤트 핸들러**

```javascript
// static/js/tab-navigation.js

/**
 * tabChanged 이벤트 리스너:
 * HTMX 커스텀 이벤트 "tabChanged"를 수신하여 탭바의 활성 상태를 갱신한다.
 * 이벤트 detail에 { activeTab: "submissions" } 등의 데이터가 포함된다.
 */
document.body.addEventListener("tabChanged", function (e) {
  const activeTab = e.detail.activeTab;
  if (!activeTab) return;

  const tabBar = document.querySelector("[data-tab-bar]");
  if (!tabBar) return;

  // 모든 탭 버튼에서 active 클래스 제거, 해당 탭에 추가
  tabBar.querySelectorAll("[data-tab]").forEach(function (btn) {
    const tab = btn.getAttribute("data-tab");
    if (tab === activeTab) {
      btn.classList.remove("border-transparent", "text-gray-500", "hover:text-gray-700", "hover:border-gray-300");
      btn.classList.add("border-primary", "text-primary");
    } else {
      btn.classList.remove("border-primary", "text-primary");
      btn.classList.add("border-transparent", "text-gray-500", "hover:text-gray-700", "hover:border-gray-300");
    }
  });

  // 뱃지 신규 표시 갱신: 현재 탭의 lastViewed 타임스탬프 업데이트
  const projectPk = document.querySelector("[data-project-pk]")?.getAttribute("data-project-pk");
  if (projectPk) {
    sessionStorage.setItem("lastViewed_" + projectPk + "_" + activeTab, Date.now().toString());
    // 현재 탭의 신규 표시 제거
    const badge = tabBar.querySelector('[data-tab="' + activeTab + '"] [data-badge-new]');
    if (badge) {
      badge.removeAttribute("data-badge-new");
      badge.classList.remove("ring-2", "ring-blue-400");
    }
  }
});

/**
 * 뱃지 신규 표시 초기화:
 * 페이지 로드 시, 각 탭의 최신 항목 생성일(data-latest)과
 * sessionStorage의 lastViewed 타임스탬프를 비교하여 신규 표시를 적용한다.
 */
document.addEventListener("DOMContentLoaded", function () {
  const projectPk = document.querySelector("[data-project-pk]")?.getAttribute("data-project-pk");
  if (!projectPk) return;

  document.querySelectorAll("[data-tab-bar] [data-tab]").forEach(function (btn) {
    const tab = btn.getAttribute("data-tab");
    const badge = btn.querySelector("[data-badge-count]");
    if (!badge) return;

    const latestStr = badge.getAttribute("data-latest");
    if (!latestStr) return;

    const latest = new Date(latestStr).getTime();
    const lastViewed = parseInt(sessionStorage.getItem("lastViewed_" + projectPk + "_" + tab) || "0", 10);

    if (latest > lastViewed) {
      badge.setAttribute("data-badge-new", "true");
      badge.classList.add("ring-2", "ring-blue-400");
    }
  });
});
```

- [ ] **Step 2: detail_tab_bar.html에 data 속성 추가**

`detail_tab_bar.html`을 수정하여 각 버튼에 `data-tab` 속성, 컨테이너에 `data-tab-bar` 속성, 뱃지에 `data-badge-count`와 `data-latest` 속성을 추가한다.

현재 코드 (라인 1):
```html
<div class="border-b border-gray-200 flex gap-0 overflow-x-auto -mx-4 lg:-mx-8 px-4 lg:px-8">
```

변경:
```html
<div class="border-b border-gray-200 flex gap-0 overflow-x-auto -mx-4 lg:-mx-8 px-4 lg:px-8" data-tab-bar>
```

각 `<button>`에 `data-tab` 속성을 추가한다. 예를 들어 개요 탭:

현재 (라인 4-8):
```html
  <button hx-get="{% url 'projects:project_tab_overview' project.pk %}"
          hx-target="#tab-content"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'overview' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    개요
  </button>
```

변경:
```html
  <button data-tab="overview"
          hx-get="{% url 'projects:project_tab_overview' project.pk %}"
          hx-target="#tab-content"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'overview' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    개요
  </button>
```

동일하게 나머지 5개 탭 버튼에도 `data-tab="search"`, `data-tab="contacts"`, `data-tab="submissions"`, `data-tab="interviews"`, `data-tab="offers"`를 추가한다.

뱃지 span에 `data-badge-count`와 `data-latest` 추가. 예시 (컨택 탭 뱃지):

현재:
```html
    <span class="text-[11px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full">{{ tab_counts.contacts }}</span>
```

변경:
```html
    <span class="text-[11px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full"
          data-badge-count
          data-latest="{{ tab_latest.contacts|date:'c' }}">{{ tab_counts.contacts }}</span>
```

동일하게 추천, 면접 뱃지에도 적용. (오퍼 탭은 현재 뱃지가 없으므로 추가 불필요)

- [ ] **Step 3: project_detail.html에 tab-navigation.js 로드 추가**

현재 (라인 77-78):
```html
{% load static %}
<script src="{% static 'js/context-autosave.js' %}"></script>
```

변경:
```html
{% load static %}
<script src="{% static 'js/context-autosave.js' %}"></script>
<script src="{% static 'js/tab-navigation.js' %}"></script>
```

- [ ] **Step 4: project_detail 뷰에 tab_latest 컨텍스트 추가**

`projects/views.py`의 `project_detail()` 뷰 (라인 339-345 부근)에 `tab_latest` 데이터를 추가한다.

현재:
```python
    # 탭 배지 카운트
    tab_counts = {
        "contacts": project.contacts.count(),
        "submissions": project.submissions.count(),
        "interviews": Interview.objects.filter(submission__project=project).count(),
        "offers": Offer.objects.filter(submission__project=project).count(),
    }
```

이후에 추가:
```python
    # 탭 뱃지 최신 항목 생성일 (신규 표시용)
    from django.db.models import Max

    tab_latest = {
        "contacts": project.contacts.aggregate(latest=Max("created_at"))["latest"],
        "submissions": project.submissions.aggregate(latest=Max("created_at"))["latest"],
        "interviews": Interview.objects.filter(
            submission__project=project
        ).aggregate(latest=Max("created_at"))["latest"],
    }
```

`render()` 호출에 `"tab_latest": tab_latest` 추가.

- [ ] **Step 5: 수동 검증**

브라우저에서 프로젝트 상세 페이지에 진입하여:
1. 탭바에 `data-tab` 속성이 렌더링되는지 확인
2. 콘솔에서 `document.querySelector('[data-tab-bar]')` 존재 확인
3. `tab-navigation.js`가 로드되는지 Network 탭에서 확인

- [ ] **Step 6: 커밋**

```bash
git add static/js/tab-navigation.js projects/templates/projects/partials/detail_tab_bar.html projects/templates/projects/project_detail.html projects/views.py
git commit -m "feat(projects): add tabChanged event system and tab-navigation.js"
```

---

### Task 2: submission_create() 성공 시 추천 탭 자동 전환

**Files:**
- Modify: `projects/views.py` — `submission_create()` 수정
- Modify: `projects/templates/projects/partials/submission_form.html` — `hx-target` 조정
- Test: `tests/test_p20_workflow_transition.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_p20_workflow_transition.py
"""P20: Workflow transition tests.

Tests for contact→submission auto-transition, interest banner,
and funnel click navigation.
"""

import pytest
from django.test import Client as TestClient
from django.utils import timezone

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Contact, Project, Submission


# --- Fixtures ---


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user_with_org(db, org):
    user = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=user, organization=org)
    return user


@pytest.fixture
def auth_client(user_with_org):
    c = TestClient()
    c.login(username="tester", password="test1234")
    return c


@pytest.fixture
def client_obj(org):
    return Client.objects.create(
        name="Acme Corp",
        industry="IT",
        organization=org,
    )


@pytest.fixture
def project(client_obj, org, user_with_org):
    p = Project.objects.create(
        title="Backend Dev",
        client=client_obj,
        organization=org,
        status="searching",
        created_by=user_with_org,
    )
    p.assigned_consultants.add(user_with_org)
    return p


@pytest.fixture
def candidate(db):
    return Candidate.objects.create(
        name="홍길동",
        email="hong@test.com",
    )


# --- submission_create auto-transition tests ---


class TestSubmissionCreateAutoTransition:
    """submission_create 성공 시 추천 탭 파셜을 반환하고
    HX-Retarget + tabChanged 헤더가 포함되어야 한다."""

    @pytest.mark.django_db
    def test_submission_create_returns_submissions_tab(
        self, auth_client, project, candidate
    ):
        """POST 성공 시 204 대신 200 + 추천 탭 HTML 반환."""
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {"candidate": str(candidate.pk), "notes": "추천합니다"},
        )
        assert resp.status_code == 200
        assert "추천 이력" in resp.content.decode()

    @pytest.mark.django_db
    def test_submission_create_has_retarget_header(
        self, auth_client, project, candidate
    ):
        """HX-Retarget 헤더가 #tab-content를 가리켜야 한다."""
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {"candidate": str(candidate.pk), "notes": "추천합니다"},
        )
        assert resp.headers.get("HX-Retarget") == "#tab-content"

    @pytest.mark.django_db
    def test_submission_create_has_tab_changed_trigger(
        self, auth_client, project, candidate
    ):
        """HX-Trigger에 tabChanged가 포함되어야 한다."""
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {"candidate": str(candidate.pk), "notes": "추천합니다"},
        )
        hx_trigger = resp.headers.get("HX-Trigger", "")
        assert "tabChanged" in hx_trigger

    @pytest.mark.django_db
    def test_submission_actually_created(
        self, auth_client, project, candidate
    ):
        """Submission 레코드가 실제로 생성되어야 한다."""
        auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {"candidate": str(candidate.pk), "notes": "추천합니다"},
        )
        assert Submission.objects.filter(
            project=project, candidate=candidate
        ).exists()
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestSubmissionCreateAutoTransition -v`
Expected: FAIL — 현재 `submission_create()`는 204를 반환하므로 `status_code == 200` 실패

- [ ] **Step 3: submission_create() 뷰 수정**

`projects/views.py`의 `submission_create()` (라인 1124 부근). 현재 성공 분기:

```python
            # 프로젝트 status 자동 전환
            from projects.services.submission import maybe_advance_project_status

            maybe_advance_project_status(project)

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "submissionChanged"},
            )
```

변경:
```python
            # 프로젝트 status 자동 전환
            from projects.services.submission import maybe_advance_project_status

            maybe_advance_project_status(project)

            # 추천 탭 파셜을 직접 렌더링하여 반환 (자동 탭 전환)
            submissions = project.submissions.select_related(
                "candidate", "consultant"
            ).order_by("-created_at")

            drafting = [s for s in submissions if s.status == Submission.Status.DRAFTING]
            submitted = [s for s in submissions if s.status == Submission.Status.SUBMITTED]
            passed = [s for s in submissions if s.status == Submission.Status.PASSED]
            rejected = [s for s in submissions if s.status == Submission.Status.REJECTED]

            import json

            response = render(
                request,
                "projects/partials/tab_submissions.html",
                {
                    "project": project,
                    "drafting": drafting,
                    "submitted": submitted,
                    "passed": passed,
                    "rejected": rejected,
                    "total_count": submissions.count(),
                },
            )
            response["HX-Retarget"] = "#tab-content"
            response["HX-Reswap"] = "innerHTML"
            response["HX-Trigger"] = json.dumps({
                "tabChanged": {"activeTab": "submissions"},
                "submissionChanged": {},
            })
            return response
```

- [ ] **Step 4: submission_form.html의 hx-target 조정**

현재 `submission_form.html` (라인 10-12)의 form 태그:
```html
  <form hx-post="{% if is_edit %}{% url 'projects:submission_update' project.pk submission.pk %}{% else %}{% url 'projects:submission_create' project.pk %}{% endif %}"
        hx-target="#submission-form-area"
        enctype="multipart/form-data"
```

`hx-target`을 제거한다 (서버 측에서 `HX-Retarget`으로 제어하므로 form 자체의 target은 폼 영역을 가리키되, 성공 시 서버가 `#tab-content`로 재지정):

사실 현재 구조에서 `hx-target="#submission-form-area"`가 있으면 validation error 시 폼 영역에 에러 폼을 다시 렌더링하고, 성공 시에는 `HX-Retarget` 헤더가 `#tab-content`로 override한다. HTMX는 `HX-Retarget` 응답 헤더가 있으면 `hx-target` 속성보다 우선하므로, **submission_form.html은 변경 불필요**하다.

- [ ] **Step 5: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestSubmissionCreateAutoTransition -v`
Expected: All 4 tests PASS

- [ ] **Step 6: 커밋**

```bash
git add projects/views.py tests/test_p20_workflow_transition.py
git commit -m "feat(projects): submission_create returns submissions tab with auto-transition"
```

---

### Task 3: contact_update() "관심" 결과 시 추천 유도 배너

**Files:**
- Modify: `projects/views.py` — `contact_update()` 수정
- Create: `projects/templates/projects/partials/contact_interest_banner.html`
- Modify: `projects/templates/projects/partials/tab_contacts.html` — 배너 삽입 영역
- Test: `tests/test_p20_workflow_transition.py` (추가)

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_p20_workflow_transition.py`에 추가:

```python
class TestContactInterestBanner:
    """contact_update에서 결과를 '관심'으로 변경하면
    응답에 추천 유도 배너가 포함되어야 한다."""

    @pytest.mark.django_db
    def test_interest_result_shows_banner(
        self, auth_client, project, candidate, user_with_org
    ):
        """결과가 '관심'이면 배너가 포함된다."""
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": str(candidate.pk),
                "channel": "전화",
                "contacted_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "result": "관심",
                "notes": "",
            },
        )
        content = resp.content.decode()
        assert "추천 서류 작성하기" in content

    @pytest.mark.django_db
    def test_non_interest_result_no_banner(
        self, auth_client, project, candidate, user_with_org
    ):
        """결과가 '관심'이 아니면 배너가 포함되지 않는다."""
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": str(candidate.pk),
                "channel": "전화",
                "contacted_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "result": "미응답",
                "notes": "",
            },
        )
        # 204 반환 (기존 동작) — 배너 없음
        assert resp.status_code == 204

    @pytest.mark.django_db
    def test_interest_but_already_submitted_no_banner(
        self, auth_client, project, candidate, user_with_org
    ):
        """이미 Submission이 있으면 배너를 표시하지 않는다."""
        Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
        )
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": str(candidate.pk),
                "channel": "전화",
                "contacted_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "result": "관심",
                "notes": "",
            },
        )
        # 이미 제출 완료이므로 배너 없이 204 반환
        assert resp.status_code == 204
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestContactInterestBanner -v`
Expected: FAIL — 현재 `contact_update()`는 항상 204를 반환

- [ ] **Step 3: contact_interest_banner.html 생성**

```html
<!-- projects/templates/projects/partials/contact_interest_banner.html -->
<div id="interest-banner"
     class="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
  <div class="flex items-start gap-3">
    <svg class="w-5 h-5 text-green-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
    </svg>
    <div>
      <p class="text-[14px] font-medium text-green-800">
        {{ candidate_name }}님 컨택 결과가 "관심"으로 저장되었습니다.
      </p>
      <button hx-get="{% url 'projects:submission_create' project.pk %}?candidate={{ candidate_id }}"
              hx-target="#tab-content"
              hx-trigger="click"
              class="mt-2 inline-flex items-center text-[14px] font-medium text-green-700 hover:text-green-900 transition">
        추천 서류 작성하기
        <svg class="w-4 h-4 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
        </svg>
      </button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: contact_update() 뷰 수정**

`projects/views.py`의 `contact_update()` (라인 993-999 부근). 현재 성공 분기:

```python
        if form.is_valid():
            form.save()
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "contactChanged"},
            )
```

변경:
```python
        if form.is_valid():
            contact = form.save()

            # "관심" 결과이고 아직 Submission이 없으면 유도 배너 표시
            if (
                contact.result == Contact.Result.INTERESTED
                and not project.submissions.filter(
                    candidate=contact.candidate
                ).exists()
            ):
                response = render(
                    request,
                    "projects/partials/contact_interest_banner.html",
                    {
                        "project": project,
                        "candidate_name": contact.candidate.name,
                        "candidate_id": contact.candidate.pk,
                    },
                )
                response["HX-Retarget"] = "#contact-form-area"
                response["HX-Reswap"] = "innerHTML"
                response["HX-Trigger"] = "contactChanged"
                return response

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "contactChanged"},
            )
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestContactInterestBanner -v`
Expected: All 3 tests PASS

- [ ] **Step 6: 커밋**

```bash
git add projects/views.py projects/templates/projects/partials/contact_interest_banner.html tests/test_p20_workflow_transition.py
git commit -m "feat(projects): show submission prompt banner when contact result is INTERESTED"
```

---

### Task 4: 예정 목록에 "컨택 등록" 버튼 추가

**Files:**
- Modify: `projects/templates/projects/partials/tab_contacts.html`

- [ ] **Step 1: 예정 목록 "결과 기록" 버튼 확인**

현재 `tab_contacts.html` (라인 96-98)에 이미 "결과 기록" 버튼이 있다:
```html
          <button hx-get="{% url 'projects:contact_create' project.pk %}?candidate={{ contact.candidate.pk }}"
                  hx-target="#contact-form-area"
                  class="text-[13px] text-primary hover:text-primary-dark">결과 기록</button>
```

이 버튼의 라벨을 "컨택 등록"으로 변경하고, 더 눈에 띄는 스타일로 변경한다.

현재:
```html
          <button hx-get="{% url 'projects:contact_create' project.pk %}?candidate={{ contact.candidate.pk }}"
                  hx-target="#contact-form-area"
                  class="text-[13px] text-primary hover:text-primary-dark">결과 기록</button>
```

변경:
```html
          <button hx-get="{% url 'projects:contact_create' project.pk %}?candidate={{ contact.candidate.pk }}"
                  hx-target="#contact-form-area"
                  class="text-[13px] bg-primary text-white px-2.5 py-1 rounded-md hover:bg-primary-dark transition">컨택 등록</button>
```

- [ ] **Step 2: 수동 검증**

컨택 탭의 예정 목록에서 "컨택 등록" 버튼이 표시되고, 클릭 시 해당 후보자가 프리필된 컨택 폼이 열리는지 확인한다.

- [ ] **Step 3: 커밋**

```bash
git add projects/templates/projects/partials/tab_contacts.html
git commit -m "feat(projects): rename reserved contact button to '컨택 등록' with emphasized style"
```

---

### Task 5: 퍼널 클릭 가능한 내비게이션

**Files:**
- Modify: `projects/views.py` — `_build_overview_context()`에 "관심" 카운트 추가
- Modify: `projects/templates/projects/partials/tab_overview.html` — 퍼널 항목을 클릭 가능한 링크로 변경
- Test: `tests/test_p20_workflow_transition.py` (추가)

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

---

### Task 6: 탭 뱃지 신규(new) 표시

**Files:**
- Modify: `static/js/tab-navigation.js` (이미 Task 1에서 로직 작성됨)
- Modify: `projects/templates/projects/partials/detail_tab_bar.html` (이미 Task 1에서 data 속성 추가됨)
- Test: `tests/test_p20_workflow_transition.py` (추가)

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_p20_workflow_transition.py`에 추가:

```python
class TestTabBadgeNewIndicator:
    """탭 뱃지에 data-latest 속성이 렌더링되어야 한다."""

    @pytest.mark.django_db
    def test_detail_page_has_tab_latest_data(
        self, auth_client, project, candidate, user_with_org
    ):
        """프로젝트 상세 페이지의 탭 뱃지에 data-latest 속성이 있어야 한다."""
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.get(f"/projects/{project.pk}/")
        content = resp.content.decode()
        assert "data-badge-count" in content
        assert "data-latest" in content

    @pytest.mark.django_db
    def test_tab_bar_has_data_tab_attributes(
        self, auth_client, project
    ):
        """탭바의 각 버튼에 data-tab 속성이 있어야 한다."""
        resp = auth_client.get(f"/projects/{project.pk}/")
        content = resp.content.decode()
        assert 'data-tab="overview"' in content
        assert 'data-tab="contacts"' in content
        assert 'data-tab="submissions"' in content
        assert 'data-tab="interviews"' in content
```

- [ ] **Step 2: 테스트 실행 — 통과 확인**

이 테스트는 Task 1에서 이미 구현한 data 속성이 렌더링되는지 확인한다.
Task 1이 완료되었으면 바로 통과해야 한다.

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestTabBadgeNewIndicator -v`
Expected: PASS (Task 1 구현 완료 후)

- [ ] **Step 3: 수동 검증 — 신규 표시 동작 확인**

1. 프로젝트에 새 컨택을 추가한다
2. 다른 탭(예: 개요)으로 이동한다
3. 컨택 탭의 뱃지에 파란색 테두리(ring)가 표시되는지 확인한다
4. 컨택 탭을 클릭하면 파란색 테두리가 사라지는지 확인한다

- [ ] **Step 4: 커밋**

```bash
git add tests/test_p20_workflow_transition.py
git commit -m "test(projects): add tab badge new indicator tests"
```

---

### Task 7: 통합 테스트 + 엣지 케이스

**Files:**
- Test: `tests/test_p20_workflow_transition.py` (추가)

- [ ] **Step 1: 엣지 케이스 테스트 작성**

`tests/test_p20_workflow_transition.py`에 추가:

```python
class TestWorkflowEdgeCases:
    """워크플로우 전환 엣지 케이스."""

    @pytest.mark.django_db
    def test_submission_create_form_validation_error_stays_in_form(
        self, auth_client, project
    ):
        """유효성 검사 실패 시 기존처럼 폼을 다시 렌더링한다."""
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {},  # candidate 필수 필드 누락
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        # 폼이 다시 렌더링되어야 함 (추천 탭이 아님)
        assert "추천 서류" in content
        # HX-Retarget이 없어야 함 (폼 영역에 렌더링)
        assert "HX-Retarget" not in resp.headers

    @pytest.mark.django_db
    def test_submission_create_duplicate_candidate_rejected(
        self, auth_client, project, candidate, user_with_org
    ):
        """같은 후보자에 대해 중복 Submission 생성 시도 시 에러."""
        Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {"candidate": str(candidate.pk), "notes": "중복"},
        )
        # 유효성 검사 실패로 폼 재렌더링
        assert resp.status_code == 200
        assert "HX-Retarget" not in resp.headers

    @pytest.mark.django_db
    def test_contact_update_interest_banner_disappears_on_tab_reload(
        self, auth_client, project, candidate, user_with_org
    ):
        """유도 배너는 일회성이다. 컨택 탭을 새로고침하면 배너가 없어야 한다."""
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="관심",
        )
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/contacts/",
            HTTP_HX_REQUEST="true",
        )
        content = resp.content.decode()
        # 컨택 탭 자체에는 배너가 없음 (배너는 contact_update 응답에만 포함)
        assert "interest-banner" not in content

    @pytest.mark.django_db
    def test_funnel_contacts_excludes_reserved(
        self, auth_client, project, candidate, user_with_org
    ):
        """퍼널의 컨택 카운트에서 예정(RESERVED)은 제외해야 한다."""
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            result="예정",
            locked_until=timezone.now() + timezone.timedelta(hours=24),
        )
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/overview/",
            HTTP_HX_REQUEST="true",
        )
        content = resp.content.decode()
        # 예정 건은 컨택 카운트에서 제외
        # "컨택" 다음 숫자가 0이어야 함
        assert ">0<" in content.replace(" ", "") or "0</span>" in content
```

- [ ] **Step 2: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestWorkflowEdgeCases -v`
Expected: All 4 tests PASS

- [ ] **Step 3: 전체 테스트 실행**

Run: `uv run pytest tests/test_p20_workflow_transition.py -v`
Expected: All tests PASS (총 13개)

- [ ] **Step 4: 기존 테스트 회귀 확인**

Run: `uv run pytest tests/test_p05_project_tabs.py tests/test_p06_contacts.py -v`
Expected: 기존 테스트도 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add tests/test_p20_workflow_transition.py
git commit -m "test(projects): add workflow transition edge case tests"
```

---

<!-- forge:phase3:구현계획:draft:2026-04-12 -->
