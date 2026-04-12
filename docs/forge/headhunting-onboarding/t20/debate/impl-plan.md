# t20: submission_create() 성공 시 추천 탭 자동 전환

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** submission_create() 뷰가 성공 시 추천 탭 파셜을 직접 반환하고 HX-Retarget + tabChanged 헤더를 추가하여, 추천 등록 후 자동으로 추천 탭으로 전환되게 한다.

**Design spec:** `docs/forge/headhunting-onboarding/t20/design-spec.md`

**depends_on:** t19

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/views.py` | 수정 | `submission_create()` 성공 시 추천 탭 파셜 반환 + HX-Retarget + tabChanged |
| `tests/test_p20_workflow_transition.py` | 생성 | 자동 전환, HX-Retarget, tabChanged 헤더, Submission 생성 확인 테스트 |

---

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

<!-- forge:t20:구현계획:draft:2026-04-12 -->
