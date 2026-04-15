# P02: Client Management

> **Phase:** 2 / 6
> **선행조건:** P01 (models and app foundation)
> **산출물:** Client CRUD 화면 + 사이드바 메뉴

---

## 목표

고객사(Client) CRUD 화면을 구현한다. HTMX 네비게이션 패턴을 적용하고
사이드바에 고객사 메뉴를 추가한다.

---

## URL 설계

| URL | View | Template | 설명 |
|-----|------|----------|------|
| `/clients/` | `client_list` | `clients/client_list.html` | 고객사 목록 |
| `/clients/new/` | `client_create` | `clients/partials/client_form.html` | 등록 폼 |
| `/clients/<uuid:pk>/` | `client_detail` | `clients/client_detail.html` | 상세 |
| `/clients/<uuid:pk>/edit/` | `client_update` | `clients/partials/client_form.html` | 수정 폼 |
| `/clients/<uuid:pk>/delete/` | `client_delete` | — | 삭제 (POST) |

`clients/urls.py`에 정의, 프로젝트 `urls.py`에 `path("clients/", include("clients.urls"))` 추가.

---

## View 구현

```python
# clients/views.py
def client_list(request):
    """고객사 목록. 검색(name, industry) + 페이지네이션."""

def client_create(request):
    """고객사 등록. GET=폼, POST=저장 후 상세로 redirect."""

def client_detail(request, pk):
    """고객사 상세. 계약 이력, 진행중 프로젝트 목록 포함."""

def client_update(request, pk):
    """고객사 수정. GET=폼(기존값), POST=저장."""

def client_delete(request, pk):
    """삭제 확인 후 목록으로 redirect."""
```

모든 뷰는 `request.htmx` 판별:
- HTMX 요청 → partial template 반환
- 일반 요청 → full page (base.html 포함) 반환

---

## Template 구조

```
clients/templates/clients/
├── client_list.html              # 목록 (full page wrapper)
├── client_detail.html            # 상세 (full page wrapper)
└── partials/
    ├── client_list_content.html  # 목록 내용 (hx-target="main")
    ├── client_detail_content.html # 상세 내용
    └── client_form.html          # 등록/수정 공용 폼
```

---

## UI 와이어프레임

### 고객사 목록

```
┌─ 고객사 ────────────────────────── [+ 등록] ─┐
│                                              │
│  검색: [__________________] [검색]            │
│                                              │
│  ┌──────────┬──────┬──────┬──────┐          │
│  │ 고객사명   │ 업종  │ 규모  │ 지역  │          │
│  ├──────────┼──────┼──────┼──────┤          │
│  │ Rayence  │의료기기│ 중견  │ 경기  │          │
│  │ LG전자    │전자   │ 대기업 │ 서울  │          │
│  │ 삼성SDI   │전자   │ 대기업 │ 경기  │          │
│  └──────────┴──────┴──────┴──────┘          │
│                                              │
│  ← 1 2 3 →                                  │
└──────────────────────────────────────────────┘
```

### 고객사 상세

```
┌─ Rayence ──────────────── [수정] [삭제] ─┐
│                                          │
│  업종: 의료기기  |  규모: 중견  |  지역: 경기 │
│  담당자: 인사팀 이부장 (02-1234-5678)      │
│                                          │
│  메모:                                   │
│  코스닥 상장. 의료영상 장비 제조.            │
│                                          │
├─ 계약 이력 ──────────────────────────────┤
│  2026.01 ~ 진행중  |  체결                │
│  2025.03 ~ 2025.12  |  만료               │
│                                          │
├─ 진행중 프로젝트 ─────────────────────────┤
│  품질기획팀장  |  서칭중  |  전병권          │
│  해외영업매니저  |  신규  |  김소연          │
└──────────────────────────────────────────┘
```

### 등록/수정 폼

```
┌─ 고객사 등록 ─────────────────────────────┐
│                                           │
│  고객사명: [________________]              │
│  업종:     [________________]              │
│  규모:     [대기업 ▾]                      │
│  지역:     [________________]              │
│                                           │
│  담당자 정보 (복수 입력 가능):               │
│  이름: [______] 직책: [______]             │
│  전화: [______] 이메일: [______]           │
│  [+ 담당자 추가]                           │
│                                           │
│  메모:                                    │
│  [____________________________]           │
│  [____________________________]           │
│                                           │
│  [저장]  [취소]                            │
└───────────────────────────────────────────┘
```

---

## 사이드바 변경

기존 사이드바 템플릿(`templates/base.html` 또는 sidebar partial)에 메뉴 추가:

```html
<a hx-get="/clients/" hx-target="main" hx-push-url="true">
  🏢 고객사
</a>
```

메뉴 순서: 대시보드 > 프로젝트 > 고객사 > 후보자 DB (P03에서 프로젝트 메뉴 추가)

---

## HTMX 패턴

- 목록 행 클릭 → `hx-get="/clients/<pk>/"` + `hx-target="main"` + `hx-push-url="true"`
- 등록 버튼 → `hx-get="/clients/new/"` + `hx-target="main"` + `hx-push-url="true"`
- 폼 제출 → `hx-post` + 성공 시 `HX-Redirect` 응답
- 검색 → `hx-get="/clients/?q=..."` + `hx-target` 목록 영역 + `hx-trigger="keyup changed delay:300ms"`

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| CRUD 동작 | 등록 → 목록에 표시 → 상세 확인 → 수정 → 삭제 |
| HTMX 네비게이션 | hx-get 요청 시 partial 반환, URL push 동작 |
| 검색 | 고객사명/업종 키워드 검색 결과 확인 |
| 사이드바 | 고객사 메뉴 클릭 시 목록 화면 전환 |
| 상세 페이지 | 계약 이력 + 진행중 프로젝트 표시 |

---

## 산출물

- `clients/views.py` — CRUD 뷰 5개
- `clients/urls.py` — URL 패턴
- `clients/forms.py` — ClientForm
- `clients/templates/clients/` — 목록/상세/폼 템플릿
- 사이드바 템플릿 수정
- 테스트 파일
