# Clients 메뉴 UI 리디자인 — Design Spec

**날짜:** 2026-04-19
**범위:** `clients` 앱 전체 화면 (리스트 + 상세 + 신규/수정 폼). 목업 `assets/ui-sample/clients-list.html` 기반. 상세/폼은 목업 없음 — 목업 토큰·패턴을 상세/폼에 확장 적용.
**기준:** `docs/design-system.md` 의 토큰·컴포넌트 규칙을 그대로 따른다. 목업과 문서가 충돌하면 목업이 우선.

## 1. 배경 & 목표

- 기존 `clients/templates/clients/*.html` 은 Phase D 이전 스타일. 디자인 시스템 토큰과 카드 hover 규칙이 일부만 반영돼 있음.
- 목업이 제시하는 정보 밀도(카테고리 칩 + 3-up 카드 + Offers/Success/Placed 통계 + 담당자/계약 요약)는 현재 리스트의 단순 "이름/업종" 카드보다 훨씬 높다. 컨설턴트가 리스트 한 화면으로 거래 현황을 파악할 수 있어야 한다.
- `Client.industry` 자유 텍스트를 고정 카테고리(11종)로 정규화해 칩 필터·집계를 가능하게 한다.
- 새 필드(website/logo/description) 로 카드 비주얼을 풍부하게 만든다.

## 2. 모델 변경

### 2.1 `Client`

| 필드 | 변경 |
|---|---|
| `industry` (CharField 자유 텍스트) | → `industry` (CharField with `IndustryCategory` choices) 로 교체 |
| `website` | **신규** `URLField(blank=True)` |
| `logo` | **신규** `ImageField(upload_to="clients/logos/", blank=True)` |
| `description` | **신규** `TextField(blank=True)` — 카드에 노출되는 2줄 요약 |

`size`, `region`, `contact_persons`, `notes`, `organization` 은 현행 유지.

### 2.2 `IndustryCategory` TextChoices (11개)

목업 순서 그대로(목업 칩의 "전체"는 UI-only, 실제 카테고리 아님):

```python
class IndustryCategory(models.TextChoices):
    BIO_PHARMA     = "바이오/제약",       "바이오 / 제약"
    HEALTHCARE     = "헬스케어/의료기기",  "헬스케어 / 의료기기"
    IT_SW          = "IT/SW",           "IT / SW"
    MATERIAL_PARTS = "소재/부품",        "소재 / 부품"
    FINANCE        = "금융/캐피탈",       "금융 / 캐피탈"
    CONSUMER       = "소비재/패션",       "소비재 / 패션"
    ENV_UTILITY    = "환경/유틸리티",     "환경 / 유틸리티"
    MOBILITY       = "모빌리티/제조",     "모빌리티 / 제조"
    MEDIA_ENTER    = "미디어/엔터",       "미디어 / 엔터"
    CONSTRUCTION   = "건설/부동산",       "건설 / 부동산"
    ETC            = "기타",             "기타"
```

DB 값은 value(예: `"바이오/제약"`) 사용. URL 쿼리는 enum name(`BIO_PHARMA`) 를 받아 `IndustryCategory[param].value` 로 변환해 쿼리에 주입 — URL 안정성과 한글 인코딩 회피 목적.

### 2.3 `Project.client` on_delete

현재 `CASCADE` — 고객사 삭제 시 모든 프로젝트가 동반 삭제. **삭제 플로우에서 가드**로 처리(아래 §6.5).

## 3. 마이그레이션

순서:

1. **M1 — 필드 추가**: `website`, `logo`, `description` 추가. 기존 `industry` 는 그대로.
2. **M2 — 데이터 마이그레이션**: 기존 `industry` 자유 텍스트를 키워드 매칭 사전으로 카테고리에 매핑.
   - 사전 예: `"반도체" → 소재/부품`, `"SW·소프트웨어·IT" → IT/SW`, `"제약·바이오·신약" → 바이오/제약`.
   - 매핑 불가 → `기타`.
   - 사전은 마이그레이션 파일 내 상수로 인라인. 외부 JSON 참조 금지.
3. **M3 — 스키마 전환**: `industry` 필드를 choices CharField 로 alter. 데이터는 M2 에서 정규화됐으므로 안전.

운영 DB 적용 전 `ssh ...showmigrations` 로 미적용 확인 → 승인 후 `./deploy.sh` 유도.

## 4. 리스트 페이지 (`/clients/`)

### 4.1 레이아웃

```
[Page header]     Active Corporate Relationships
                  Clients                         [▾ Filters (N)] [+ Add Client]
                  등록된 고객사 N곳의 거래 이력과 …

[Category chips]  전체·N  바이오/제약·11  헬스케어·8  …  (가로 스크롤, 총 11개 + "전체")

[Filter panel]    (접힘 상태 기본. 펼치면 4섹션 칩 패널, §5)

[3-up card grid]  ┌─────────┐ ┌─────────┐ ┌─────────┐
                  │ client  │ │ client  │ │ client  │   col-span-4 × 3
                  └─────────┘ └─────────┘ └─────────┘
                  ... infinite scroll ...

[Sentinel]        hx-get next page on reveal
```

- `max-w-[1280px]`, `px-8 py-8 space-y-6`.
- 기존 상단 검색 input 은 **삭제**(전역 하단 검색바로 대체, `base.html` 이미 포함).

### 4.2 Page header

- eyebrow `"Active Corporate Relationships"` + H2 `"Clients"` (`text-3xl font-bold tracking-tight`, 디자인 시스템 Page title).
- 서브 카피: 조직 내 총 고객사 건수 + 안내 문구.
- 우측 버튼 2개: Filters(드롭다운 트리거, 활성 필터 개수 배지), Add Client(owner 만, `ink3` primary).

### 4.3 카테고리 칩

- `cat-chip` 컴포넌트(디자인 시스템 목업 CSS 그대로 — rounded-full, padding 9px 18px, active 시 `ink3`).
- 각 칩 텍스트: `"<라벨> · <count>"`. 0건 카테고리는 `aria-disabled` + 불투명도 저하, 클릭 비활성.
- "전체" 칩은 항상 첫 번째.
- 클릭 시 `hx-get="?cat=<value>"` + `hx-target="#client-grid"` + `hx-push-url="true"`. active 상태 재계산.

### 4.4 3-up 카드 그리드

- `grid grid-cols-12 gap-6`, 각 카드 `col-span-4`.
- 카드 컴포넌트는 §5 참조.
- 한 페이지 **9건** (3행). Infinite scroll.

### 4.5 Infinite scroll

- 하단 sentinel: `<div hx-get="{% url 'clients:client_list_page' %}?page={{ next_page }}&..." hx-trigger="revealed" hx-swap="outerHTML">loading…</div>`.
- 응답: 다음 페이지 카드 HTML + 다음 sentinel(있으면) or "모두 불러왔어요" 텍스트.
- 카테고리/필터 변경 시에는 sentinel 이 아닌 `#client-grid` 전체 교체.

### 4.6 빈 상태

- 카테고리/필터 적용 중 결과 0건 → `"<조건>에 해당하는 고객사가 없습니다"`.
- 전체 비어있음 + owner → "첫 고객사 등록" CTA(`/clients/new/`).
- 전체 비어있음 + member → 텍스트만.

## 5. 카드 컴포넌트 (`partials/client_card.html`)

### 5.1 구조 (2개 클릭 영역으로 분할)

```
┌────────────────────────────────────────┐
│ ▓ logo │  Name  [badge]       6 Active │  ← 상단 <a target="_blank" href="website">
│  tile  │  업종 · 지역          [⋯]    │     website 없으면 <div>
│ 56×56  │                              │
├────────────────────────────────────────┤
│ description 2줄 line-clamp              │  ← 하단 <a hx-get="client_detail">
│ [Offers 50] [Success 0] [Placed 0명]  │
│ [meta] [meta]         [📧] [⭐]        │
└────────────────────────────────────────┘
```

카드 hover lift(`top: -2px`, `shadow-lift`)는 전체에 적용. `transform` 금지(디자인 시스템 규칙).

### 5.2 로고 타일

- 56×56, `rounded-lg`, padding 8(이미지 있을 때).
- `client.logo` 있으면 `<img>` `object-fit:contain`, 흰 배경.
- 없으면 그라디언트 배경 + 이니셜 2자. 그라디언트 8종은 `static/css/input.css` `.client-logo-1`~`.client-logo-8`. 선택은 `hash(client.pk) % 8` 의 deterministic 템플릿태그로.

### 5.3 배지

`Client.size` → CSS 클래스 매핑:

| size | 클래스 | 색 |
|---|---|---|
| 대기업 | `badge enterprise` | slate (`#F1F5F9` / `#334155`) |
| 중견 | `badge midcap` | blue (`#DBEAFE` / `#1E40AF`) |
| 중소 | `badge sme` | orange (`#FFEDD5` / `#9A3412`) |
| 외국계 | `badge foreign` | violet (`#EDE9FE` / `#5B21B6`) |
| 스타트업 | `badge startup` | green (`#DCFCE7` / `#166534`) |

size 공란 → 배지 생략.

### 5.4 상단 영역 (회사 홈페이지 링크)

- `client.website` 있음 → `<a target="_blank" rel="noopener">` 래핑. 로고·회사명·배지·업종/지역·우상단 Active 카운트 전체를 포함.
- 없음 → `<div>` 로 래핑. 클릭 무반응 + `cursor: default`. hover 시 카드 lift 는 유지(하단 영역이 담당).

### 5.5 하단 영역 (프로젝트 리스트로)

- `<a hx-get="{% url 'clients:client_detail' pk %}" hx-target="#main-content" hx-push-url="true">` 래핑.
- description, 통계 3종, meta-tag, 우측 아이콘 버튼까지 포함.

### 5.6 통계 3종 (`.stat`)

- `Offers` = 해당 고객사 총 프로젝트 수.
- `Success` = `result="success"` 프로젝트 수.
- `Placed` = `Application.hired_at__isnull=False` 수. 단위 "명".
- Offers=0 → 하단 영역 내부 통계 자리에 `"거래 이력 없음"` placeholder 표시, 하단 `<a>` 는 유지하지만 상세 페이지에서도 빈 상태 렌더링.

### 5.7 케밥 메뉴 (우상단, owner 만)

- `⋯` 아이콘 버튼 → details/summary 또는 alpine.js 드롭다운.
- 메뉴: [수정] [삭제].
- `event.stopPropagation()` 으로 상단 `<a>` 전파 차단.
- 수정: `hx-get="{% url 'clients:client_update' pk %}"` 메인 교체.
- 삭제: confirm 모달 호출.

### 5.8 Meta tag + 우측 아이콘

- `meta-tag` 2개 최대:
  - 담당자 수: `"{{ contact_persons|length }}인 담당"` (0명이면 생략).
  - 계약 상태: `client.contracts.filter(status="체결").exists()` → `"계약 체결"`.
- 우측 아이콘 `📧` `⭐` 는 MVP 에서 시각 요소만. 클릭 비활성(`pointer-events-none` + `opacity-60`). 백로그: 이메일/즐겨찾기 구현.

## 6. 필터 드롭다운

### 6.1 트리거

페이지 헤더의 `[▾ Filters (N)]`. N = 활성 필터 개수(0 이면 숨김). 클릭 시 헤더 아래로 펼쳐지는 카드 패널(`bg-surface rounded-card shadow-lift p-6`).

### 6.2 섹션

| # | 섹션 | 타입 | 옵션 |
|---|---|---|---|
| 1 | 기업 규모 | multi-select chip | 대기업 / 중견 / 중소 / 외국계 / 스타트업 |
| 2 | 지역 | multi-select chip | `Client.region` distinct 값 (빈값 제외). 기본 6개 + "+ 더보기" 확장 |
| 3 | 거래 건수 | single-select radio chip | 전체 / 0건 / 1–5건 / 6–10건 / 10건+ |
| 4 | 성사 이력 | single-select radio chip | 전체 / 성사 있음 / 성사 없음(Offers>0,Success=0) / 거래 없음(Offers=0) |

### 6.3 액션

- 하단 좌측 `[초기화]`, 우측 `[적용하기]`(ink3 primary).
- 적용 시 HTMX 로 `#client-grid` 교체. 패널은 닫기.
- URL 쿼리 파라미터 스키마:
  - `?cat=BIO_PHARMA` (단일)
  - `&size=대기업,중견` (csv)
  - `&region=서울,경기` (csv)
  - `&offers=1-5` (enum: `0`, `1-5`, `6-10`, `10+`, 공란=전체)
  - `&success=has` (enum: `has`, `none`, `no_offers`, 공란=전체)

### 6.4 백엔드

`clients/services/client_queries.py::filter_clients(qs, **params)` 단일 진입점. 집계는 `.annotate()` 한 번만.

## 7. 상세 페이지 (`/clients/<pk>/`)

### 7.1 레이아웃

```
[Profile header card — 전체 너비]
[Left col  담당자 + 계약 요약  col-span-4] [Right col  Engagements 프로젝트 리스트  col-span-8]
[Notes card — 전체 너비]
```

### 7.2 Profile header

- 로고 80×80 (리스트 카드보다 큼).
- H2 회사명 + size 배지.
- 업종 · 지역 라인.
- website 있으면 외부 링크 아이콘 + 도메인만 표시(`urlparse(website).netloc`).
- description 전체 노출(line-clamp 없음, max-w 720px).
- 통계 4종 가로 나열: Offers, Success, Placed, Active.
- 우상단 케밥(owner): [수정] [삭제].

### 7.3 Left col — 담당자 & 계약

- **담당자 카드**: `contact_persons` JSONField 리스트(`{name, position, phone, email}`). 각 항목 avatar(이니셜 원 28px `bg-ink2 text-white`) + 이름 + 직책(position) + 이메일/전화(클릭 시 `mailto:`/`tel:`).
  - 비어있음 + owner → "담당자 추가" 링크 → `/clients/<pk>/edit/#contacts` 앵커.
- **계약 요약 카드**: 기존 `partials/contract_section.html` 을 디자인 토큰으로 재스타일. 로직(`contract_create`/`update`/`delete`) 유지.
  - 각 항목: 시작일 – 종료일, status 배지(협의중/체결/만료/해지), terms 한 줄 요약.

### 7.4 Right col — Engagements 프로젝트 리스트

- 헤더: eyebrow `"Engagements"` + H3 `"프로젝트"` + 총 건수.
- 세그먼티드 컨트롤: `[진행중 N] [완료 M] [전체 K]`. 클릭 시 HTMX `hx-get="{% url 'clients:client_projects_panel' pk %}?status=..."` 으로 리스트만 교체.
- 리스트 아이템(세로 스택):
  - 제목(클릭 → `/projects/<pk>/`), phase 배지, status 배지, 시작일, Hired 수(`hired_at__isnull=False` 카운트), result 배지(성사/실패/미정).
- 페이지네이션 없음. 최근 20건만. 더 있으면 하단 `"전체 보기 →"` (현재 scope 밖, 백로그).

### 7.5 Notes card (전체 너비)

- `client.notes` 을 `white-space: pre-line` 으로 렌더. Markdown 미지원.
- owner → 우상단 `[편집]` → 수정 폼 `#notes` 앵커.

### 7.6 빈 상태

- 프로젝트 없음: "진행 중인 프로젝트가 없습니다" + owner → "새 프로젝트" CTA → `/projects/new/?client={{pk}}` 프리필.
- 계약 없음: "등록된 계약이 없습니다" + owner → "+ 계약 추가".
- 담당자 없음: 위 §7.3.

## 8. 신규/수정 폼

### 8.1 URL & 권한

`/clients/new/`, `/clients/<pk>/edit/`. owner 만 접근. member → 403 또는 리스트로 리다이렉트.

### 8.2 섹션 구성

단일 카드형 폼. `max-w-[720px]` 중앙.

1. **기본 정보**
   - 회사명 (required)
   - 업종 카테고리 (select, `IndustryCategory.choices`)
   - 기업 규모 (select, `Size.choices`, 빈 옵션 포함)
   - 지역 (text)
   - 웹사이트 URL (url input, `https://` 자동 prefix — 클라이언트 단 alpine.js 또는 view 단에서 normalize)
   - 로고 업로드 (file input)
     - 신규: 파일 선택 시 미리보기
     - 수정: 기존 로고 썸네일 + `[삭제]` 체크박스 + `[교체]` 파일 선택
     - 확장자 제한: jpg/jpeg/png/svg/webp. 최대 2MB. form `clean_logo()` 에서 검증.
   - 설명 (textarea 3줄, placeholder "카드 리스트에 노출되는 2줄 요약")

2. **담당자** (`contact_persons` JSONField 편집)
   - 동적 리스트 UI. alpine.js `x-data` 배열 + `<template x-for>` 반복.
   - 각 행: 이름 / 직책(position) / 전화 / 이메일 입력 + 우측 [삭제] 버튼. 스키마: `{name, position, phone, email}` (기존 JSONField 구조 유지)
   - 하단 `[+ 담당자 추가]` 빈 행 추가.
   - 저장 시: 빈 행(이름 공란) 제외. 정렬은 사용자 입력 순.
   - hidden input `contact_persons_json` 에 JSON 직렬화.

3. **메모**
   - plain textarea 6줄.

### 8.3 하단 액션 바 (sticky bottom)

- 좌측 [취소] → 리스트로.
- 우측 [저장] (primary ink3).
- 수정 시 좌측 [삭제] (text danger, confirm 모달 트리거).

### 8.4 저장 흐름

- `ClientForm(ModelForm)` + 커스텀 `contact_persons_json` 처리.
- 로고 업로드: `clients/services/client_create.py::apply_logo_upload(client, uploaded_file, delete=False)`. delete 체크 시 기존 파일 삭제 후 `logo=None`. 교체 시 이전 파일 unlink.
- 성공 → `/clients/<pk>/` 상세로 redirect.
- HTMX 요청 시: `HttpResponse("")` + `HX-Redirect` 헤더로 상세 이동.

### 8.5 삭제

- 상세/리스트 케밥 또는 수정 폼 [삭제] 버튼.
- Confirm 모달: 제목 `"{{ client.name }} 삭제"` + 본문 `"이 고객사를 삭제하면 연결된 프로젝트 {{ project_count }}건도 함께 삭제됩니다."` (Project.client = CASCADE 현실 반영).
- **가드**: `client.projects.exists()` → 삭제 차단, 모달에 `"프로젝트가 있어 삭제할 수 없습니다. 프로젝트를 먼저 정리하거나 조직 관리자에게 문의하세요."` 표시. 강제 삭제 옵션은 제공하지 않음.
- 프로젝트 없음 → 기존 `client_delete` 뷰로 삭제, 리스트로 redirect.

## 9. 서비스 / 쿼리 계층

### 9.1 `clients/services/client_queries.py` (신규)

```python
def list_clients_with_stats(
    org, *,
    categories=None,    # list[IndustryCategory] | None
    sizes=None,         # list[Size]
    regions=None,       # list[str]
    offers_range=None,  # "0" | "1-5" | "6-10" | "10+" | None
    success_status=None,  # "has" | "none" | "no_offers" | None
) -> QuerySet[Client]: ...

def category_counts(org) -> dict[str, int]: ...  # choices value → count

def available_regions(org) -> list[str]: ...

def client_stats(client) -> dict: ...  # offers, success, placed, active

def client_projects(client, *, status_filter="all") -> QuerySet[Project]:
    # status_filter: "active" | "closed" | "all"
    ...
```

- 집계는 `.annotate(offers_count=Count('projects'), success_count=Count('projects', filter=Q(projects__result='success')), placed_count=Count('projects__applications', filter=Q(projects__applications__hired_at__isnull=False)), active_count=Count('projects', filter=Q(projects__status='open')))` 한 번에.
- offers_range 필터는 annotate 후 `.filter(offers_count__...)`.
- success_status 필터는 annotate 조합.

### 9.2 `clients/services/client_create.py` (신규)

```python
def normalize_contact_persons(raw_list: list[dict]) -> list[dict]: ...
def apply_logo_upload(client: Client, uploaded_file, *, delete: bool = False) -> None: ...
```

## 10. 뷰 & URL

### 10.1 `clients/views.py`

| 뷰 | 변경 |
|---|---|
| `client_list` | 재작성. full page + HTMX grid 교체 분기. 필터 파라미터 처리 |
| `client_list_page` | **신규** — infinite scroll 페이지(카드 + 다음 sentinel) |
| `client_detail` | 재작성. 상단 프로필 + 좌/우/하단 섹션 |
| `client_projects_panel` | **신규** — 상세 우측 프로젝트 세그먼티드 컨트롤 HTMX |
| `client_create` / `client_update` | 재스타일 + 로고 업로드 처리 + 담당자 JSON 정규화 |
| `client_delete` | 기존 유지. 단 프로젝트 존재 시 가드 추가 |
| `contract_*` | 기존 유지 |

### 10.2 `clients/urls.py` 추가

```
path("page/", views.client_list_page, name="client_list_page")
path("<uuid:pk>/projects/", views.client_projects_panel, name="client_projects_panel")
```

## 11. 정적 자산

### 11.1 CSS (`static/css/input.css` `@layer components`)

- `.cat-chip` / `.cat-chip.is-active` — 이미 존재하거나 후보자에서 재사용 중인 형태면 재사용. 없으면 신규.
- `.badge.enterprise` / `.midcap` / `.sme` / `.foreign` / `.startup` — 기업 규모 배지.
- `.client-logo-1` ~ `.client-logo-8` — 그라디언트 배경 8종.
- `.stat` / `.stat .num` / `.stat .lbl` — 카드 내 통계 블록. 후보자에서 유사 패턴 있으면 공용화.
- `.meta-tag` — 회색 pill.

### 11.2 Templates 신규

- `clients/templates/clients/partials/client_card.html`
- `clients/templates/clients/partials/client_filter_dropdown.html`
- `clients/templates/clients/partials/client_list_page.html` — infinite scroll 페이지 응답용
- `clients/templates/clients/partials/client_projects_panel.html` — 상세 우측 HTMX 응답용
- `clients/templates/clients/partials/contract_section.html` — **재스타일**(기존 파일 수정)

기존 `client_list.html`, `client_detail.html`, `client_form.html` 은 전면 재작성.

### 11.3 Templatetag (`clients/templatetags/clients_tags.py` 신규)

- `logo_class(client)` — `hash(client.pk) % 8 + 1` 기반 `.client-logo-N` 클래스 반환.
- `client_initials(client)` — 회사명 첫 2자 대문자.
- `size_badge_class(size)` — size 값 → CSS 클래스.

## 12. 테스트

### 12.1 신규 파일

- `tests/test_clients_models.py` — 필드·choices·logo upload_to 경로 검증.
- `tests/test_clients_queries.py` — `list_clients_with_stats` annotate 정확성, 필터 조합, `category_counts`, `client_stats`, `client_projects`.
- `tests/test_clients_views_list.py` — 카테고리 칩, 필터 드롭다운, infinite scroll 페이지 엔드포인트, 빈 상태.
- `tests/test_clients_views_detail.py` — 프로필, 담당자/계약, 프로젝트 세그먼티드 컨트롤.
- `tests/test_clients_views_form.py` — 신규/수정, 로고 업로드/삭제/교체, 담당자 JSON 왕복, owner 가드.
- `tests/test_clients_views_delete.py` — 프로젝트 있을 때 차단, 없을 때 성공.

### 12.2 기존 유지

- 계약 CRUD 테스트는 유지. `contract_section.html` 재스타일은 HTML 변경이므로 테스트에서 셀렉터만 조정.

## 13. 비-목표 / 백로그

- 카드 우측 `📧` `⭐` 아이콘의 실제 기능(이메일 작성·즐겨찾기) — 시각 요소만 MVP.
- 상세 페이지 프로젝트 리스트의 "전체 보기 →" 무한 스크롤 — 최근 20건 제한.
- 로고 이미지 썸네일 자동 생성·웹 최적화(WebP 변환) — 원본 업로드만.
- 멀티 로고/갤러리 — 1:1 ImageField 만.
- 카테고리 12개 외 확장 — 별도 마이그레이션.

## 14. 의존성

- `Pillow` — ImageField 처리용. 현재 `pyproject.toml` 에 **미포함**. 이번 작업에서 `uv add Pillow` 로 추가.
- 모델 변경 3단계 마이그레이션.
- 프로젝트 앱 영향 없음(Project.client FK 유지). 단 `Project.client.on_delete=CASCADE` 는 §8.5 삭제 가드로 실질적으로 회피.

## 15. 작업 순서 (구현 계획의 골격)

1. 모델 변경 + 마이그레이션 3단계 + 테스트.
2. `clients/services/client_queries.py` + 단위 테스트.
3. `clients/services/client_create.py` + 단위 테스트.
4. `clients/templatetags/clients_tags.py` + CSS 토큰(`@layer components`) 추가.
5. 리스트 페이지 재작성 + partials(`client_card.html`, `client_filter_dropdown.html`, `client_list_page.html`) + 뷰.
6. 상세 페이지 재작성 + `client_projects_panel` + `contract_section.html` 재스타일.
7. 신규/수정 폼 재작성 + 로고 업로드.
8. 삭제 플로우 가드.
9. 수동 브라우저 QA (URL 목록 핸드오프 문서에 기록).
