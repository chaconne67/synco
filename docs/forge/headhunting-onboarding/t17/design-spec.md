# t17: 사이드바 + 모바일 네비게이션 업데이트

> **Phase:** 2단계 — 통합 설정 + 조직 관리
> **선행 조건:** t15 (조직 관리 뷰 + URL)

---

## 배경

조직 관리 페이지(`/org/`)가 구축되었으나, 사이드바와 모바일 하단 네비게이션에 진입점이 없다. owner에게만 "조직 관리" 메뉴를 노출한다.

1단계에서 구현한 사이드바 역할 기반 필터링(`membership.role`)을 활용한다.

---

## 요구사항

### 사이드바 (`nav_sidebar.html`)

- "설정" 메뉴 아래에 "조직 관리" 메뉴 추가
- owner에게만 표시: `{% if membership and membership.role == 'owner' %}`
- 아이콘: 사람 그룹 SVG
- HTMX 네비게이션: `hx-get="/org/" hx-target="#main-content" hx-push-url="true"`
- `data-nav="org"` 속성 추가
- `updateSidebar()` JavaScript에 org 라우트 매칭 추가

### 모바일 하단 네비게이션 (`nav_bottom.html`)

- 설정 아이콘 앞에 "조직" 아이콘 추가
- owner에게만 표시
- 동일한 아이콘 및 HTMX 네비게이션
- `updateNav()` JavaScript에 org 라우트 매칭 추가

---

## 제약

- 기존 네비게이션 항목의 순서와 스타일을 유지한다.
- consultant/viewer에게는 "조직 관리" 메뉴가 보이지 않아야 한다.
