# t24: 탭 뱃지 신규(new) 표시

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** t19에서 구현한 탭 뱃지 신규 표시의 **마크업 회귀를 자동 테스트**하고, **동작을 수동 검증**한다. 자동 테스트는 data 속성의 렌더링 정확성을 검증하며, JS 기반 동작(sessionStorage, ring 추가/제거)은 수동으로 확인한다.

**Design spec:** `docs/forge/headhunting-onboarding/t24/design-spec.md`

**depends_on:** t19

---

## Changes from Tempering

| Issue | Severity | Resolution |
|-------|----------|------------|
| R1-01: Manual verification conflicts with known limitation | CRITICAL | ACCEPTED — Step 3 revised to use funnel navigation (tabChanged dispatching flow) instead of regular tab click |
| R1-02: Tests only verify markup, not JS behavior | CRITICAL | ACCEPTED — Goal narrowed to "마크업 회귀(자동) + 동작 검증(수동)" |
| R1-03: Assertions too loose (whole-page string search) | CRITICAL | ACCEPTED — Assertions strengthened to verify attributes within specific tab button contexts |
| R1-04: Missing tabs in data-tab assertion (4 of 6) | MAJOR | ACCEPTED — All 6 tabs asserted |
| R1-05: No negative case (badge absent when count=0) | CRITICAL | ACCEPTED — Added negative test for empty project |
| R1-06: Manual verification lacks sessionStorage init | MINOR | ACCEPTED — Added prerequisite for fresh browser state |

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `tests/test_p20_workflow_transition.py` | 추가 | 탭 뱃지 data 속성 렌더링 테스트 (positive + negative) |

---

- [ ] **Step 1: 테스트 작성**

`tests/test_p20_workflow_transition.py`에 추가:

```python
class TestTabBadgeNewIndicator:
    """탭 뱃지 data 속성 렌더링 검증 (마크업 회귀 테스트)."""

    @pytest.mark.django_db
    def test_all_tabs_have_data_tab_attributes(
        self, auth_client, project
    ):
        """탭바의 모든 6개 버튼에 data-tab 속성이 있어야 한다."""
        resp = auth_client.get(f"/projects/{project.pk}/")
        content = resp.content.decode()
        for tab_name in ["overview", "search", "contacts", "submissions", "interviews", "offers"]:
            assert f'data-tab="{tab_name}"' in content, f"data-tab=\"{tab_name}\" not found"

    @pytest.mark.django_db
    def test_badge_present_with_data_attrs_when_count_positive(
        self, auth_client, project, candidate, user_with_org
    ):
        """컨택이 있으면 contacts 탭 뱃지에 data-badge-count와 data-latest가 렌더링된다."""
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

        # contacts 탭 버튼 블록 내에 data-badge-count와 data-latest가 존재해야 한다
        contacts_start = content.find('data-tab="contacts"')
        assert contacts_start != -1, "contacts tab button not found"
        # 다음 탭 버튼까지의 범위로 한정
        contacts_end = content.find('data-tab="submissions"', contacts_start)
        contacts_block = content[contacts_start:contacts_end]
        assert "data-badge-count" in contacts_block, "data-badge-count not in contacts tab"
        assert "data-latest" in contacts_block, "data-latest not in contacts tab"

    @pytest.mark.django_db
    def test_badge_absent_when_count_zero(
        self, auth_client, project
    ):
        """컨택이 없으면 contacts 탭 뱃지 span이 렌더링되지 않아야 한다."""
        resp = auth_client.get(f"/projects/{project.pk}/")
        content = resp.content.decode()

        # contacts 탭 버튼 블록 내에 data-badge-count가 없어야 한다
        contacts_start = content.find('data-tab="contacts"')
        assert contacts_start != -1, "contacts tab button not found"
        contacts_end = content.find('data-tab="submissions"', contacts_start)
        contacts_block = content[contacts_start:contacts_end]
        assert "data-badge-count" not in contacts_block, "badge should not render when count=0"
```

- [ ] **Step 2: 테스트 실행 — 통과 확인**

이 테스트는 t19에서 이미 구현한 data 속성이 올바르게 렌더링되는지 확인한다.
t19가 완료되었으면 바로 통과해야 한다.

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestTabBadgeNewIndicator -v`
Expected: PASS

- [ ] **Step 3: 수동 검증 — 신규 표시 동작 확인**

**전제조건:** 새 시크릿/인코그니토 탭에서 검증하거나, 개발자 도구 콘솔에서 `sessionStorage.clear()` 실행 후 검증한다.

1. 프로젝트에 새 컨택을 추가한다
2. 개요 탭에서 퍼널의 "컨택" 링크를 클릭한다 (이 경로는 tabChanged를 dispatch한다)
3. 다시 개요 탭으로 돌아간다 (퍼널의 다른 링크 클릭 또는 개요 탭 버튼)
4. 컨택 탭의 뱃지에 파란색 테두리(ring-2 ring-blue-400)가 **표시되지 않는지** 확인한다 (방금 방문했으므로 lastViewed가 업데이트됨)
5. 새 컨택을 추가한 후 페이지를 새로고침한다
6. 개요 탭에서 컨택 탭의 뱃지에 파란색 테두리(ring)가 **표시되는지** 확인한다 (새 컨택의 created_at > lastViewed)
7. 퍼널의 "컨택" 링크를 클릭하여 컨택 탭으로 이동한다
8. 파란색 테두리가 **사라지는지** 확인한다 (tabChanged가 dispatch되어 lastViewed 업데이트)

- [ ] **Step 4: 커밋**

```bash
git add tests/test_p20_workflow_transition.py
git commit -m "test(projects): add tab badge new indicator tests"
```

<!-- forge:t24:impl-plan:complete:2026-04-13T14:30:00+09:00 -->
