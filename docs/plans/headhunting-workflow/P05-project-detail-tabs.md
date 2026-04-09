# P05: Project Detail Tabs

> **Phase:** 5 / 6
> **선행조건:** P03 (project CRUD — 상세 페이지 존재)
> **산출물:** 프로젝트 상세 6-탭 구조 (개요 + 서칭 완성, 나머지 4탭 골격)

---

## 목표

프로젝트 상세 페이지를 6개 탭 구조로 재편한다. 개요 탭과 서칭 탭을 완성하고,
컨택/추천/면접/오퍼 탭은 빈 골격만 배치한다(P06 및 후속 Phase에서 채움).

---

## URL 설계

| URL | View | Template | 설명 |
|-----|------|----------|------|
| `/projects/<uuid:pk>/` | `project_detail` | `projects/project_detail.html` | 상세 (탭 wrapper) |
| `/projects/<uuid:pk>/tab/overview/` | `project_tab_overview` | `partials/tab_overview.html` | 개요 탭 |
| `/projects/<uuid:pk>/tab/search/` | `project_tab_search` | `partials/tab_search.html` | 서칭 탭 |
| `/projects/<uuid:pk>/tab/contacts/` | `project_tab_contacts` | `partials/tab_contacts.html` | 컨택 탭 (골격) |
| `/projects/<uuid:pk>/tab/submissions/` | `project_tab_submissions` | `partials/tab_submissions.html` | 추천 탭 (골격) |
| `/projects/<uuid:pk>/tab/interviews/` | `project_tab_interviews` | `partials/tab_interviews.html` | 면접 탭 (골격) |
| `/projects/<uuid:pk>/tab/offers/` | `project_tab_offers` | `partials/tab_offers.html` | 오퍼 탭 (골격) |

탭 전환은 HTMX: `hx-get` + `hx-target="#tab-content"`. URL push 없음 (탭은 화면 내 전환).

---

## Template 구조

```
projects/templates/projects/
├── project_detail.html               # full page (탭 헤더 + #tab-content)
└── partials/
    ├── detail_tab_bar.html           # 탭 바 (6개 탭, 카운트 배지 포함)
    ├── tab_overview.html             # 개요 탭 — 완성
    ├── tab_search.html               # 서칭 탭 — 완성
    ├── tab_contacts.html             # 컨택 탭 — 골격
    ├── tab_submissions.html          # 추천 탭 — 골격
    ├── tab_interviews.html           # 면접 탭 — 골격
    └── tab_offers.html               # 오퍼 탭 — 골격
```

---

## UI 와이어프레임

### 탭 헤더 + 상세 레이아웃

```
┌─────────────────────────────────────────────────────┐
│  ← 목록    Rayence · 품질기획팀장         ● 서칭중    │
│  고객사: Rayence  |  담당: 전병권  |  의뢰일: 03/16   │
├────────┬────────┬────────┬────────┬────────┬────────┤
│  개요   │ 서칭   │ 컨택(3) │ 추천(1)│ 면접(0)│ 오퍼   │
├────────┴────────────────────────────────────────────┤
│ <div id="tab-content">                              │
│   (HTMX로 교체되는 탭 콘텐츠)                         │
│ </div>                                              │
└─────────────────────────────────────────────────────┘
```

- **← 목록**: `hx-get="/projects/"` + `hx-target="main"` + `hx-push-url="true"`
- **탭 배지**: 컨택/추천/면접 건수를 annotate로 계산하여 표시
- **상태 뱃지**: 색상 구분 (신규=blue, 서칭중=yellow, 추천=orange, 면접=purple, 오퍼=green, 클로즈=gray)
- 초기 로드 시 개요 탭 콘텐츠를 인라인 렌더링 (추가 요청 없이)

### 개요 탭

```
┌─ JD 요약 ──────────────────────────────────────┐
│  포지션: 품질기획팀장                             │
│  고객사: Rayence (의료기기, 중견, 경기)            │
│  요구조건:                                       │
│    경력 15년+  |  인서울 이상  |  남녀무관          │
│    필수자격: 품질경영기사                          │
│    키워드: ISO, 6시그마, 의료기기 품질              │
│                                                  │
│  [JD 전문 보기]  [수정]                           │
├─ 진행 현황 ────────────────────────────────────┤
│  서칭 → ●컨택(3) → 추천(1) → 면접(0) → 오퍼(0)  │
│  ▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░  진행률 시각화          │
├─ 담당 컨설턴트 ────────────────────────────────┤
│  전병권 (리드)  |  [+ 담당자 추가]                │
├─ 활동 로그 ────────────────────────────────────┤
│  04/03 전병권: 홍길동 컨택 (전화, 관심 있음)       │
│  04/02 전병권: 김영희 컨택 (이메일, 미응답)        │
│  03/16 전병권: 프로젝트 등록                      │
│  [더 보기]                                      │
└────────────────────────────────────────────────┘
```

**진행 현황 퍼널:** Contact, Submission, Interview 카운트를 단계별로 시각화.

**활동 로그:** Contact, Submission, Interview 생성/변경 이력을 통합 타임라인으로 표시.
최근 10건 표시, "더 보기"로 전체 로드.

### 서칭 탭

```
┌─ 요구조건 기반 자동 필터 ─────────────────────────┐
│  JD에서 추출된 필터가 미리 세팅됨:                   │
│  [경력 15년+ ×] [인서울 ×] [품질경영기사 ×]         │
│                                                   │
│  [필터 수정]  [후보자 DB 검색 실행]                  │
│                                                   │
├─ 검색 결과 (24명) ────────────────────────────────┤
│  ☑ 홍길동  16년  현) 메디톡스 품질부장    ⚠ 컨택됨   │
│  ☑ 김영희  14년  현) 오스템 QA팀장        🔒 예정    │
│  ☐ 박철수  18년  현) 삼성메디슨 품질기획             │
│  ☐ 이순신  12년  현) GE헬스케어 QA매니저             │
│  ... (스크롤)                                      │
│                                                   │
│  [선택한 후보자 컨택 예정 등록 →]                    │
└───────────────────────────────────────────────────┘
```

**기존 candidates 검색 연동:**
- Project.requirements JSON에서 필터 조건 추출
- `candidates.services.search` 모듈의 검색 함수 호출
- 결과에 해당 프로젝트의 Contact 이력 매칭하여 상태 표시

**컨택 상태 표시:**
- ⚠ 컨택됨: 이 프로젝트에서 이미 컨택 완료된 후보자
- 🔒 예정: 이 프로젝트에서 컨택 예정 등록된 후보자 (다른 컨설턴트)
- ℹ (다른 프로젝트): 다른 프로젝트에서 컨택 이력 있음 (툴팁으로 표시)
- (없음): 컨택 이력 없는 후보자

### 골격 탭 (컨택/추천/면접/오퍼)

```
┌─────────────────────────────────────────────┐
│                                             │
│  이 탭은 준비 중입니다.                       │
│  (Phase 6에서 구현 예정)                      │
│                                             │
└─────────────────────────────────────────────┘
```

각 골격 탭에 해당 모델의 기본 목록만 표시 (있는 경우):
- 컨택: Contact 목록 (간단한 테이블)
- 추천: Submission 목록
- 면접: Interview 목록
- 오퍼: Offer 목록

---

## View 구현

```python
# projects/views.py
def project_detail(request, pk):
    """탭 wrapper + 개요 탭 인라인 렌더링."""

def project_tab_overview(request, pk):
    """개요: JD 요약, 퍼널, 담당자, 활동 로그."""

def project_tab_search(request, pk):
    """서칭: requirements → 필터 세팅 → candidates 검색 → 컨택 상태 매칭."""

def project_tab_contacts(request, pk):
    """컨택: Contact 목록 (기본). P06에서 완성."""

def project_tab_submissions(request, pk):
    """추천: Submission 목록 (기본). 후속 Phase에서 완성."""

def project_tab_interviews(request, pk):
    """면접: Interview 목록 (기본). 후속 Phase에서 완성."""

def project_tab_offers(request, pk):
    """오퍼: Offer 목록 (기본). 후속 Phase에서 완성."""
```

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| 탭 전환 | 6개 탭 클릭 시 각 콘텐츠 로드 |
| 개요 탭 | JD 요약, 퍼널 카운트, 활동 로그 정확성 |
| 서칭 탭 | requirements 기반 필터 자동 세팅 |
| 검색 연동 | candidates 검색 결과 표시 + 컨택 상태 매칭 |
| 탭 배지 | 컨택/추천/면접 카운트 정확성 |
| 초기 로드 | 상세 진입 시 개요 탭이 추가 요청 없이 렌더링 |

---

## 산출물

- `projects/views.py` — detail + 6개 탭 뷰
- `projects/urls.py` — 탭 URL 추가
- `projects/templates/projects/partials/tab_*.html` — 6개 탭 템플릿
- `projects/templates/projects/partials/detail_tab_bar.html`
- 테스트 파일
