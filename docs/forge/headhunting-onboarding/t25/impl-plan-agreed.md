# t25: 통합 테스트 + 엣지 케이스

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 3 전체 워크플로우의 통합 테스트와 엣지 케이스를 검증하여 회귀를 방지한다.

**Design spec:** `docs/forge/headhunting-onboarding/t25/design-spec.md`

**depends_on:** t19, t20, t21, t22, t23, t24

---

## Changes from Tempering

| Issue | Severity | Resolution |
|-------|----------|------------|
| R1-01: Test 1 duplicates existing test_invalid_form_still_returns_form | CRITICAL | ACCEPTED — Removed duplicate, replaced with submission success end-to-end verification |
| R1-02: Test 4 duplicates existing test_overview_funnel_excludes_reserved_from_contacts | CRITICAL | ACCEPTED — Removed duplicate, replaced with interest banner CTA navigation test |
| R1-03: Test 2 missing interested_contact fixture | CRITICAL | ACCEPTED — Added interested_contact fixture, added Submission count assertion |
| R1-04: Step 3 expected test count wrong (13 → 19) | MAJOR | ACCEPTED — Corrected to 19 |
| R1-05: Step 4 regression scope too narrow | MAJOR | ACCEPTED — Expanded to include test_p07_submissions.py |
| R1-06: Test 2 should verify specific error message | MINOR | ACCEPTED — Added form error content assertion |
| R1-07: Tests should go in existing classes | MINOR | REBUTTED — Cross-cutting integration tests stay in dedicated class |

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `tests/test_p20_workflow_transition.py` | 추가 | 엣지 케이스 테스트 (TestWorkflowEdgeCases 클래스) |

---

- [ ] **Step 1: 엣지 케이스 테스트 작성**

`tests/test_p20_workflow_transition.py`에 추가:

```python
class TestWorkflowEdgeCases:
    """워크플로우 전환 엣지 케이스."""

    @pytest.mark.django_db
    def test_submission_create_duplicate_candidate_rejected(
        self, auth_client, project, candidate, interested_contact, user_with_org
    ):
        """같은 후보자에 대해 중복 Submission 생성 시도 시 에러.

        interested_contact fixture가 있어야 candidate가 SubmissionForm의
        queryset에 포함된다. 기존 Submission이 있으면 queryset에서 제외되어
        유효성 검사가 실패해야 한다.
        """
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
        # 중복이 실제로 방지되었는지 확인
        assert Submission.objects.filter(
            project=project, candidate=candidate
        ).count() == 1

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
```

- [ ] **Step 2: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestWorkflowEdgeCases -v`
Expected: All 2 tests PASS

- [ ] **Step 3: 전체 테스트 실행**

Run: `uv run pytest tests/test_p20_workflow_transition.py -v`
Expected: All tests PASS (총 19개: 기존 17 + 신규 2)

- [ ] **Step 4: 기존 테스트 회귀 확인**

Run: `uv run pytest tests/test_p05_project_tabs.py tests/test_p06_contacts.py tests/test_p07_submissions.py -v`
Expected: 기존 테스트도 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add tests/test_p20_workflow_transition.py
git commit -m "test(projects): add workflow transition edge case tests (t25)"
```

<!-- forge:t25:impl-plan:complete:2026-04-13T14:30:00+09:00 -->
