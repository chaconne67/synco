# Task 7: 사이드바 역할별 메뉴 필터링

> **출처:** `docs/forge/headhunting-onboarding/phase1/design-spec-agreed.md`
> **선행 조건:** Task 1, 2 (구현 완료) -- context processor로 membership 주입

---

## 배경

현재 사이드바와 모바일 하단 네비게이션은 모든 사용자에게 동일한 메뉴를 표시한다. 역할별로 접근 가능한 메뉴만 표시해야 한다. view 단 접근 제어(Task 5)와 별개로, UI에서도 불필요한 메뉴를 숨겨 혼란을 방지한다.

---

## 요구사항

### 사이드바 메뉴 (역할별 필터링)

**Owner:**
```
├─ 대시보드
├─ 후보자
├─ 프로젝트
├─ 고객사
├─ 레퍼런스
├─ 프로젝트 승인 (N)    <-- 기존 "승인 요청" 이름 변경
├─ 뉴스피드
├─ 조직 관리            <-- 신규 (멤버 승인 포함)
└─ 설정
```

**Consultant:**
```
├─ 대시보드 (내 업무)
├─ 후보자
├─ 프로젝트 (배정된 것만)
├─ 고객사 (읽기 전용)
├─ 뉴스피드
└─ 설정
```

### 변경 사항

- 대시보드, 후보자, 프로젝트, 고객사, 뉴스피드, 설정 -- 모든 역할 표시
- 레퍼런스 -- owner only (`{% if membership and membership.role == 'owner' %}` 가드)
- 프로젝트 승인 (N) -- owner only, 기존 "승인 요청" 텍스트를 "프로젝트 승인"으로 변경
- 조직 관리 -- owner only (신규 항목, `/organization/` URL, 사람 아이콘)

### 모바일 하단 네비게이션

- 레퍼런스 링크에 동일한 owner-only 가드 적용
- 모바일 nav의 슬롯이 제한적이므로 조직 관리 등 owner-only 항목은 desktop sidebar에서만 표시

---

## 제약사항

- Task 2에서 구현된 context processor(`accounts.context_processors.membership`)가 모든 템플릿에 `membership` 변수를 주입하는 것을 전제한다.
- JavaScript `updateSidebar()` 함수에 `organization` key를 추가한다.
- 모바일 하단 네비게이션의 역할별 필터링은 Phase 1 범위 내에서 간단히 처리하고, 본격적인 모바일 대응은 Phase 2에서 한다.
