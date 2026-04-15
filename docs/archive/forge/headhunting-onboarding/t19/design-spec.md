# t19: tabChanged 이벤트 시스템 + tab-navigation.js

> **Phase:** 3 — 워크플로우 연결
> **선행 조건:** Phase 1 (t01-t10), Phase 2 (t11-t18) 구현 완료

---

## 배경

현재 프로젝트 상세 페이지의 6개 탭(개요, 서칭, 컨택, 추천, 면접, 오퍼)은 각각 독립적으로 동작하며, 탭 간 전환이 수동이다. 워크플로우 자동 전환(컨택→추천 등)을 구현하려면, 서버 응답이 탭 콘텐츠를 교체할 때 **탭바의 활성 상태도 함께 갱신**하는 메커니즘이 필요하다.

또한 사용자가 마지막으로 탭을 본 이후 새로운 항목이 추가되었는지 시각적으로 표시하여, 변경 사항을 놓치지 않게 해야 한다.

## 요구사항

### tabChanged 이벤트 시스템

- `tabChanged` 커스텀 이벤트를 정의한다. 이벤트 detail에 `{ activeTab: "submissions" }` 등의 데이터가 포함된다.
- 이벤트 수신 시 탭바에서 해당 탭 버튼에 active 클래스를 적용하고, 나머지 탭에서 제거한다.
- 탭바 컨테이너에 `data-tab-bar` 속성, 각 버튼에 `data-tab` 속성을 추가하여 JavaScript에서 식별 가능하게 한다.

### 탭 뱃지 신규 표시 기반 데이터

- 각 탭 뱃지에 `data-badge-count`와 `data-latest` 속성을 추가하여, 클라이언트 JavaScript에서 최신 항목 생성일과 세션 스토리지의 lastViewed 타임스탬프를 비교할 수 있게 한다.
- `project_detail()` 뷰에 `tab_latest` 컨텍스트 데이터를 추가하여, 각 탭의 최신 항목 생성일을 템플릿에 전달한다.

### tab-navigation.js

- `tabChanged` 이벤트 핸들러: 탭바 활성 상태 갱신.
- 뱃지 신규 표시 초기화: 페이지 로드 시 `data-latest`와 sessionStorage의 `lastViewed_{project_id}_{tab}`을 비교하여 신규 항목이 있으면 뱃지에 시각적 표시(ring-2, ring-blue-400).
- 탭 전환 시 현재 탭의 lastViewed 타임스탬프를 sessionStorage에 업데이트하고 신규 표시를 제거.

## 제약사항

- 클라이언트 측 JavaScript만으로 처리한다 (서버 부하 없음).
- sessionStorage를 사용하므로 탭/창 간 공유되지 않는다.
- 이 태스크는 이벤트 시스템의 **기반(infrastructure)**이며, 실제 이벤트를 발행하는 것은 후속 태스크(t20, t21, t23)에서 수행한다.

---

## 앱별 변경 영향

| 앱/파일 | 변경 |
|---------|------|
| `static/js/tab-navigation.js` | 생성 — tabChanged 이벤트 핸들러, 뱃지 신규 표시 로직 |
| `projects/templates/projects/partials/detail_tab_bar.html` | 수정 — data-tab-bar, data-tab, data-badge-count, data-latest 속성 추가 |
| `projects/templates/projects/project_detail.html` | 수정 — tab-navigation.js script 태그 추가 |
| `projects/views.py` | 수정 — project_detail()에 tab_latest 컨텍스트 추가 |

<!-- forge:t19:설계:draft:2026-04-12 -->
