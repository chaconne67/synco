# t20: submission_create() 성공 시 추천 탭 자동 전환

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** submission_create() 뷰가 성공 시 추천 탭 파셜을 직접 반환하고 HX-Retarget + tabChanged 헤더를 추가하여, 추천 등록 후 자동으로 추천 탭으로 전환되게 한다.

**Design spec:** `docs/forge/headhunting-onboarding/t20/design-spec.md`

**depends_on:** t19

---

## Changes from Tempering

| Issue | Severity | Resolution |
|-------|----------|------------|
| R1-01: Test fixture missing interested_contact + owned_by | CRITICAL | ACCEPTED — Fixtures must include `owned_by=org` and `Contact` with `result=INTERESTED` matching test_p07 pattern |
| R1-02: Existing tests (test_p07) will break | CRITICAL | ACCEPTED — Must update `tests/test_p07_submissions.py` assertions that expect 204 |
| R1-03: Step 4 self-contradictory | MAJOR | ACCEPTED — Rewritten as clear no-op explanation |
| R1-04: Code duplication with project_tab_submissions() | CRITICAL | ACCEPTED — Call existing `project_tab_submissions()` instead of copying logic |
| R1-05: Weak tabChanged test — no JSON parsing | CRITICAL | ACCEPTED — Parse JSON, verify exact structure |
| R1-06: import json inside function body | MAJOR | ACCEPTED — Already imported at file top (line 1), no change needed |
| R1-07: Line number inaccuracy | MINOR | ACCEPTED — Corrected references |
| R1-08: Fragile string assertion | MAJOR | REBUTTED — Stable heading text, standard verification pattern |
| R1-09: Missing HX-Reswap test | MINOR | ACCEPTED — Added to test |
| R1-10: Overly split test methods | MINOR | REBUTTED — Project convention, better diagnostics |

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/views.py` | 수정 | `submission_create()` 성공 시 `project_tab_submissions()` 호출 + HX-Retarget + tabChanged |
| `tests/test_p20_workflow_transition.py` | 생성 | 자동 전환, HX-Retarget, tabChanged JSON 구조, HX-Reswap, Submission 생성 확인 테스트 |
| `tests/test_p07_submissions.py` | 수정 | 기존 204 → 200 응답 계약 업데이트 |

---

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_p20_workflow_transition.py
"""P20: Workflow transition tests.

Tests for submission_create auto-transition to submissions tab.
"""

import json

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
def candidate(org):
    return Candidate.objects.create(
        name="홍길동",
        owned_by=org,
    )


@pytest.fixture
def interested_contact(project, candidate, user_with_org):
    """컨택 결과 '관심'인 Contact — SubmissionForm이 후보자를 선택 가능하게 함."""
    return Contact.objects.create(
        project=project,
        candidate=candidate,
        consultant=user_with_org,
        channel=Contact.Channel.PHONE,
        contacted_at=timezone.now(),
        result=Contact.Result.INTERESTED,
    )


# --- submission_create auto-transition tests ---


class TestSubmissionCreateAutoTransition:
    """submission_create 성공 시 추천 탭 파셜을 반환하고
    HX-Retarget + tabChanged 헤더가 포함되어야 한다."""

    @pytest.mark.django_db
    def test_submission_create_returns_submissions_tab(
        self, auth_client, project, candidate, interested_contact
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
        self, auth_client, project, candidate, interested_contact
    ):
        """HX-Retarget 헤더가 #tab-content를 가리켜야 한다."""
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {"candidate": str(candidate.pk), "notes": "추천합니다"},
        )
        assert resp.headers.get("HX-Retarget") == "#tab-content"
        assert resp.headers.get("HX-Reswap") == "innerHTML"

    @pytest.mark.django_db
    def test_submission_create_has_structured_tab_changed_trigger(
        self, auth_client, project, candidate, interested_contact
    ):
        """HX-Trigger에 구조화된 tabChanged + submissionChanged가 포함되어야 한다."""
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {"candidate": str(candidate.pk), "notes": "추천합니다"},
        )
        hx_trigger = resp.headers.get("HX-Trigger", "{}")
        payload = json.loads(hx_trigger)
        assert payload["tabChanged"] == {"activeTab": "submissions"}
        assert "submissionChanged" in payload

    @pytest.mark.django_db
    def test_submission_actually_created(
        self, auth_client, project, candidate, interested_contact
    ):
        """Submission 레코드가 실제로 생성되어야 한다."""
        auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {"candidate": str(candidate.pk), "notes": "추천합니다"},
        )
        assert Submission.objects.filter(
            project=project, candidate=candidate
        ).exists()

    @pytest.mark.django_db
    def test_invalid_form_still_returns_form(
        self, auth_client, project
    ):
        """폼 유효성 실패 시 기존 동작 유지 — HX-Retarget 없이 폼 재렌더링."""
        resp = auth_client.post(
            f"/projects/{project.pk}/submissions/new/",
            {},  # 빈 데이터 → validation error
        )
        # 유효성 실패 시 폼을 다시 렌더링 (200 with form HTML, no HX-Retarget)
        assert resp.status_code == 200
        assert "HX-Retarget" not in resp.headers
        assert "HX-Reswap" not in resp.headers
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestSubmissionCreateAutoTransition -v`
Expected: FAIL — 현재 `submission_create()`는 204를 반환하므로 `status_code == 200` 실패

- [ ] **Step 3: submission_create() 뷰 수정**

`projects/views.py`의 `submission_create()` 함수. 현재 성공 분기 (라인 1180-1188):

```python
            # 프로젝트 status 자동 전환
            from projects.services.submission import maybe_advance_project_status

            maybe_advance_project_status(project)

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "submissionChanged"},
            )
```

변경 — 기존 `project_tab_submissions()` 뷰를 재사용하여 코드 중복 방지:

```python
            # 프로젝트 status 자동 전환
            from projects.services.submission import maybe_advance_project_status

            maybe_advance_project_status(project)

            # 추천 탭 파셜을 직접 렌더링하여 반환 (자동 탭 전환)
            # 기존 project_tab_submissions 뷰를 재사용하여 로직 중복 방지
            response = project_tab_submissions(request, pk)
            response["HX-Retarget"] = "#tab-content"
            response["HX-Reswap"] = "innerHTML"
            response["HX-Trigger"] = json.dumps({
                "tabChanged": {"activeTab": "submissions"},
                "submissionChanged": {},
            })
            return response
```

**참고:** `json`은 이미 파일 최상단(라인 1)에서 import되어 있고, `project_tab_submissions`은 같은 파일 내 함수이므로 추가 import 불필요.

- [ ] **Step 4: submission_form.html — 변경 불필요**

`submission_form.html`의 `hx-target="#submission-form-area"`는 그대로 유지한다. HTMX 동작:
- **폼 유효성 실패 시:** 서버가 HX-Retarget 없이 폼 HTML을 반환 → HTMX는 `hx-target="#submission-form-area"`에 렌더링
- **성공 시:** 서버가 `HX-Retarget: #tab-content` 헤더를 반환 → HTMX는 응답 헤더가 `hx-target` 속성을 override하여 `#tab-content`에 렌더링

따라서 이 파일은 변경하지 않는다.

- [ ] **Step 5: 기존 테스트 업데이트**

`tests/test_p07_submissions.py`의 기존 HTMX 동작 테스트를 새 응답 계약에 맞게 업데이트한다.

**5a: TestHTMXBehavior 클래스의 test_create_returns_204_with_trigger (라인 736-746)**

현재:
```python
    def test_create_returns_204_with_trigger(
        self, auth_client, project, candidate, interested_contact
    ):
        """생성 성공 시 204 + HX-Trigger: submissionChanged."""
        url = reverse("projects:submission_create", args=[project.pk])
        resp = auth_client.post(
            url,
            {"candidate": str(candidate.pk), "template": "xd_ko"},
        )
        assert resp.status_code == 204
        assert resp.headers.get("HX-Trigger") == "submissionChanged"
```

변경:
```python
    def test_create_returns_200_with_tab_transition(
        self, auth_client, project, candidate, interested_contact
    ):
        """생성 성공 시 200 + 추천 탭 파셜 반환 + HX-Trigger에 submissionChanged 포함."""
        url = reverse("projects:submission_create", args=[project.pk])
        resp = auth_client.post(
            url,
            {"candidate": str(candidate.pk), "template": "xd_ko"},
        )
        assert resp.status_code == 200
        hx_trigger = json.loads(resp.headers.get("HX-Trigger", "{}"))
        assert "submissionChanged" in hx_trigger
```

**5b: TestSubmissionCRUD 등 다른 테스트의 204 assertion**

라인 262, 310, 370, 408, 435 등에서 `assert resp.status_code == 204`를 `assert resp.status_code == 200`으로 변경한다. 이 테스트들은 `submission_create`를 호출하므로 응답 코드가 변경된다.

**주의:** `submission_update`, `submission_delete`, `submission_submit`, `submission_feedback` 등 다른 뷰의 204는 변경하지 않는다 — 이 할일에서 변경하는 것은 `submission_create` 뷰뿐이다. 각 테스트가 어떤 URL을 호출하는지 확인 후 `submission_create` 관련 것만 업데이트한다.

**참고:** `test_p07_submissions.py` 상단에 `import json`이 없으면 추가한다.

- [ ] **Step 6: 테스트 실행 — 전체 통과 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py tests/test_p07_submissions.py -v`
Expected: All tests PASS (새 테스트 + 기존 테스트 모두)

- [ ] **Step 7: 전체 테스트 스위트 확인**

Run: `uv run pytest -v`
Expected: 전체 테스트 스위트 PASS — 다른 파일에서 submission_create 204를 기대하는 테스트가 없는지 확인

- [ ] **Step 8: 커밋**

```bash
git add projects/views.py tests/test_p20_workflow_transition.py tests/test_p07_submissions.py
git commit -m "feat(projects): submission_create returns submissions tab with auto-transition"
```

<!-- forge:t20:impl-plan:complete:2026-04-12T23:30:00+09:00 -->
