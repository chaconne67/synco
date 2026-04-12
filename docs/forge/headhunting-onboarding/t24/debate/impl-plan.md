# t24: 탭 뱃지 신규(new) 표시

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** t19에서 구현한 탭 뱃지 신규 표시 기능이 올바르게 동작하는지 테스트를 작성하고 수동 검증을 수행한다.

**Design spec:** `docs/forge/headhunting-onboarding/t24/design-spec.md`

**depends_on:** t19

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `tests/test_p20_workflow_transition.py` | 추가 | 탭 뱃지 data 속성 렌더링 테스트 |

---

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

<!-- forge:t24:구현계획:draft:2026-04-12 -->
