# Task 10: 전체 통합 검증 (확정 구현계획서)

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

Run:
```bash
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py migrate --check
```
Expected: "No changes detected" and "No unapplied migrations"

- [ ] **Step 4: Manual verification checklist**

Start dev server: `./dev.sh`

### 4.1 온보딩 플로우 (Happy path)

1. 카카오 로그인 -> Membership 없음 -> 초대코드 입력 화면 표시
2. 유효한 owner 코드 입력 -> 즉시 대시보드
3. 유효한 consultant 코드 입력 -> 승인 대기 화면

### 4.2 초대코드 Negative path

4. 존재하지 않는(invalid) 초대코드 입력 -> 오류 메시지 확인

### 4.3 Membership 상태 전환

5. Django admin에서 Membership.status=active 변경 -> 대시보드 접근 가능
6. active 상태 사용자가 /accounts/pending/ 접근 -> 대시보드로 리디렉션
7. Django admin에서 Membership.status=rejected 변경 -> 거절 안내 화면
8. rejected 사용자 로그아웃 후 재로그인 -> 거절 안내 화면 재표시

### 4.4 역할별 접근 제어

9. consultant로 로그인 -> 사이드바에 레퍼런스/조직관리 메뉴 없음
10. consultant로 /clients/new/ 직접 접근 -> 403
11. consultant로 프로젝트 목록 -> 배정된 것만 표시
12. consultant로 미배정 프로젝트 detail URL 직접 접근 -> 403 또는 404 확인
    (Note: 현재 코드는 organization 소속이면 접근 가능 — Phase 1 gap으로 기록)
13. owner로 프로젝트 생성 -> 담당 컨설턴트 선택 가능

### 4.5 빈 화면 CTA (Task 9 검증)

14. owner (프로젝트/고객사 없음) 대시보드 -> "고객사를 등록하고 첫 프로젝트를 시작하세요" + 고객사 등록 버튼
15. consultant (배정 프로젝트 없음) 대시보드 -> "배정된 프로젝트가 없습니다. 관리자가 프로젝트를 배정하면 여기에 표시됩니다."
16. owner 프로젝트 목록 (빈 상태) -> "새 프로젝트 만들기" 버튼
17. consultant 프로젝트 목록 (빈 상태) -> "배정된 프로젝트가 없습니다."
18. owner 고객사 목록 (빈 상태) -> "첫 고객사를 등록하세요" + 등록 버튼

### 4.6 사이드바 라벨 확인

19. (사전 조건: pending approval 프로젝트 1개 생성)
20. owner로 로그인 -> 사이드바에 "프로젝트 승인" 표시 확인 (기존 "승인 요청"에서 변경됨)

<!-- forge:t10:구현담금질:complete:2026-04-12T21:30:00+09:00 -->
