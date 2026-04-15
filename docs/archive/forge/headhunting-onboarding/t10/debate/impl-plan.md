# Task 10: 전체 통합 검증

**Goal:** Phase 1의 모든 태스크(Task 3~9) 완료 후, 테스트/린트/마이그레이션/수동 검증으로 전체 시스템 동작을 확인한다.

**Design spec:** `docs/forge/headhunting-onboarding/t10/design-spec.md`

**depends_on:** Task 3, Task 4, Task 5, Task 6, Task 7, Task 8, Task 9

---

## File Map

이 태스크는 코드 변경 없이 검증만 수행한다.

---

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 2: Run lint**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: No errors

- [ ] **Step 3: Check migrations**

Run: `uv run python manage.py makemigrations --check --dry-run`
Expected: "No changes detected"

- [ ] **Step 4: Manual verification checklist**

Start dev server: `./dev.sh`

1. 카카오 로그인 -> Membership 없음 -> 초대코드 입력 화면 표시
2. 유효한 owner 코드 입력 -> 즉시 대시보드
3. 유효한 consultant 코드 입력 -> 승인 대기 화면
4. Django admin에서 Membership.status=active 변경 -> 대시보드 접근 가능
5. Django admin에서 Membership.status=rejected 변경 -> 거절 안내 화면
6. consultant로 로그인 -> 사이드바에 레퍼런스/조직관리 메뉴 없음
7. consultant로 /clients/new/ 직접 접근 -> 403
8. consultant로 프로젝트 목록 -> 배정된 것만 표시
9. owner로 프로젝트 생성 -> 담당 컨설턴트 선택 가능
10. 사이드바 "프로젝트 승인" 표시 확인 (기존 "승인 요청"에서 변경됨)
