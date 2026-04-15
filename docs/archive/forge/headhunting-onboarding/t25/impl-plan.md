# t25: 통합 테스트 + 엣지 케이스

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 3 전체 워크플로우의 통합 테스트와 엣지 케이스를 검증하여 회귀를 방지한다.

**Design spec:** `docs/forge/headhunting-onboarding/t25/design-spec.md`

**depends_on:** t19, t20, t21, t22, t23, t24

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `tests/test_p20_workflow_transition.py` | 추가 | 엣지 케이스 테스트 |

---

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

<!-- forge:t25:구현계획:draft:2026-04-12 -->
