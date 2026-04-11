# Task 10: 전체 통합 검증

> **출처:** `docs/forge/headhunting-onboarding/phase1/design-spec-agreed.md`
> **선행 조건:** Task 3~9 전체

---

## 배경

Phase 1의 모든 태스크(Task 3~9)가 완료된 후, 전체 시스템이 설계 의도대로 동작하는지 통합 검증을 수행한다. 자동화 테스트, 린트, 마이그레이션 검증, 수동 검증을 포함한다.

---

## 요구사항

### 자동화 검증

1. 전체 테스트 스위트 통과
2. 린트 (ruff check + format) 통과
3. 마이그레이션 일관성 확인 (미적용 마이그레이션 없음)

### 수동 검증 체크리스트

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

---

## 제약사항

- 이 태스크는 코드 변경 없이 검증만 수행한다.
- 검증 중 발견된 문제는 해당 태스크로 돌아가 수정한다.
