# synco Design System

> **Source of truth:** [`assets/ui-sample/dashboard.html`](../assets/ui-sample/dashboard.html)
> 이 문서는 위 목업에서 추출한 토큰과 컴포넌트 패턴이다. 모든 신규/리팩터링 화면은 이 문서를 기준으로 작성한다.

---

## 1. Foundations

### 1.1 Font

```
Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif
```

CDN: `https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css`

- **Antialiasing:** `-webkit-font-smoothing: antialiased` 전역 적용
- **Tabular numerals:** 숫자 카운터/금액/통계는 `.tnum` 유틸 (`font-feature-settings: "tnum" 1, "ss01" 1; font-variant-numeric: tabular-nums`)

### 1.2 Color Tokens

Tailwind config에 정의 (`tailwind.config.theme.extend.colors`):

| Token | Hex | 용도 |
|---|---|---|
| `canvas` | `#F8FAFC` | 페이지 배경, 셀 hover, 헤더 행 배경 |
| `surface` | `#FFFFFF` | 카드, 셀, 상단 헤더 |
| `ink` | `#0F172A` | 사이드바, 다크 강조 카드(KPI). **버튼·토글에는 사용 금지** (너무 진함) |
| `ink2` | `#1E293B` | 사이드바 hover/active, 버튼 hover, 아바타 배경 |
| `ink3` | `#334155` | **모든 primary 버튼/active 토글의 기본 배경**, 본문 텍스트 2차, 진행바 default fill |
| `muted` | `#64748B` | 메타 텍스트, 라벨, 아이콘 secondary |
| `faint` | `#94A3B8` | placeholder, 사이드바 비활성, eyebrow default |
| `hair` | `#E2E8F0` | 카드 디바이더, border default |
| `line` | `#F1F5F9` | 카드 내부 옅은 디바이더, chip 배경 |
| `success` | `#10B981` | active 상태, 성공 |
| `warning` | `#F59E0B` | review 상태, 주의 |
| `info` | `#6366F1` | completed/info 상태, 차트 보조 |
| `danger` | `#EF4444` | 에러, deadline 경고 |

**캘린더 전용 보더 색:** `#EEF2F7` (hair보다 한 단계 연함)

#### 의미적 계층 규칙

세 단계의 dark 잉크 톤을 **용도별로 엄격히 구분**한다:

| 톤 | 용도 |
|---|---|
| `ink` (#0F172A) — slate-900 | 사이드바 배경, 페이지 내 단 1개의 다크 강조 KPI 카드 (예: 대시보드 Estimated Revenue) |
| `ink2` (#1E293B) — slate-800 | 위 두 가지의 hover 상태, 버튼 hover, 헤더 사용자 아바타 배경 |
| `ink3` (#334155) — slate-700 | **모든 primary 버튼 / FAB / active 토글 / 다크 칩**의 기본 배경 |

- **버튼·토글에 절대 `ink`를 쓰지 말 것** — `#0F172A`는 사이드바·KPI 다크 카드에만 허용. 버튼에 쓰면 너무 진해 보이고 사이드바와 시각적으로 충돌.
- **버튼은 `ink3` → hover `ink2`** — 한 단계 진해지는 자연스러운 hover 피드백.
- **다크 잉크(`ink`)는 강조 1개당 1개만** — 페이지 내 다크 카드는 시선 앵커이므로 남발 금지.
- **브랜드 컬러는 잉크 톤** — 별도 brand purple/blue 없음. 액션·CTA는 모두 슬레이트 계열.
- **상태 컬러는 의미 전용** — success/warning/info/danger를 장식으로 쓰지 말 것.

### 1.3 Spacing

`4px` 베이스, `8px` 그리드. Tailwind 기본 스케일 사용.

| Token | px | 용도 |
|---|---|---|
| `space-1` | 4 | tag 내부, icon gap, dot 마진 |
| `space-2` | 8 | 버튼 v-padding, 이벤트 pill 위 마진 |
| `space-3` | 12 | 컨테이너 내부 작은 gap, 사이드바 link gap |
| `space-4` | 16 | 컴포넌트 내부 gap, 컨트롤 padding |
| `space-5` | 20 | 통계 카드 내부 vertical gap |
| `space-6` | 24 | **카드 padding 표준, 그리드 gap 표준, 사이드바 v-padding** |
| `space-8` | 32 | 메인 컨텐츠 edge padding |

**고정 패턴:**
- 카드 padding: `p-6` (24px)
- 메인 영역 edge: `px-8 py-8` (32px)
- 그리드 gap: `gap-6` (24px)
- 사이드바 nav padding: `px-4 py-6`

### 1.4 Border Radius

```js
borderRadius: { 'card': '16px' }
```

| Token | px | 용도 |
|---|---|---|
| `rounded-md` | 6 | (사용 안 함 — 일관성 위해 sm/lg/full로 통일) |
| `rounded-lg` | 8 | 사이드바 link, 작은 inner 컨테이너 |
| `rounded-card` | 16 | **모든 카드** (통계, 리스트, 캘린더 카드) |
| `rounded-full` | 9999 | 아바타, status dot, chip/pill, FAB, 알림 버튼, 진행바 |

### 1.5 Shadows

```js
boxShadow: {
  card: '0 1px 2px 0 rgba(15,23,42,0.04), 0 1px 3px 0 rgba(15,23,42,0.06)',
  lift: '0 4px 6px -1px rgba(15,23,42,0.08), 0 2px 4px -2px rgba(15,23,42,0.04)',
  fab:  '0 10px 15px -3px rgba(15,23,42,0.15), 0 4px 6px -2px rgba(15,23,42,0.08)',
}
```

| Token | 용도 |
|---|---|
| `shadow-card` | 모든 일반 카드의 기본 그림자 |
| `shadow-lift` | 다크 강조 카드, 한 단계 더 떠 있는 요소 |
| `shadow-fab` | 플로팅 액션 버튼 |

**hover lift (모든 카드 공통):**

> ⚠️ **`transform` 금지. `position: relative` + `top` 으로만 lift 한다.**
> `translateY` / `translate3d` 모두 hover 시점에 텍스트 안티앨리어싱 모드를 바꿔 글자가 흐려진다 (`translate3d` + `backface-visibility` + `will-change` 조합으로도 완전히 막히지 않음). `top` 기반 lift는 GPU 컴포지팅을 트리거하지 않아 텍스트가 항상 sub-pixel rendering 된다.

```css
.rounded-card {
  position: relative;
  top: 0;
  transition: top 200ms cubic-bezier(0.4, 0, 0.2, 1),
              box-shadow 200ms cubic-bezier(0.4, 0, 0.2, 1);
}
.rounded-card:hover {
  top: -2px;
  box-shadow: 0 12px 24px -10px rgba(15,23,42,0.18),
              0 4px 8px -4px rgba(15,23,42,0.08);
}
.bg-ink.rounded-card:hover {
  box-shadow: 0 16px 32px -12px rgba(15,23,42,0.45),
              0 6px 12px -6px rgba(15,23,42,0.2);
}
```

### 1.6 Motion

- **Easing:** `cubic-bezier(0.4, 0, 0.2, 1)` (ease-out 표준)
- **Transitions:**
  - **150ms** (`.15s ease`): 색상 변화 (사이드바 link, 셀 hover)
  - **200ms** (`cubic-bezier(0.4,0,0.2,1)`): 카드 lift (transform + shadow)
- 과시적 애니메이션 금지. 진입은 fade, 상태 변화는 색·그림자만.

---

## 2. Typography Scale

`<style>` 블록의 `.eyebrow` + Tailwind 임의값 조합. **모든 폰트 크기는 px 명시**(rem 변환 금지).

| Role | 클래스 / 인라인 | size | weight | 용도 |
|---|---|---|---|---|
| Stat number | `text-[40px] leading-none font-bold tnum` | 40 | 700 | 카드 핵심 KPI (24, ₩842,500) |
| Page title | `text-[22px] font-bold tracking-tight` | 22 | 700 | 상단 헤더 H1 |
| Stat secondary | `text-xl font-bold tnum` | 20 | 700 | sub stat (12, 82%) |
| Logo | `text-lg font-bold tracking-tight` | 18 | 700 | 사이드바 로고 |
| Card body strong | `text-[15px] font-semibold leading-snug` | 15 | 600 | 카드 내 주요 문구 (스케줄 제목) |
| Body | `text-sm` | 14 | 400 | 일반 본문, 상태 라벨 |
| Body strong | `text-sm font-semibold` | 14 | 600 | 이름, 메뉴 텍스트 |
| Calendar day number | `cal-day > .tnum` | 14 | 600 | 캘린더 날짜 숫자 |
| Body small | `text-xs` | 12 | 400/500 | 메타, 위치, 시간 |
| Chip | `chip` | 12 | 500 | 태그, 필터 pill |
| Eyebrow | `eyebrow` | 10 | 700 | 섹션 라벨 (UPPERCASE, letter-spacing 0.08em) |
| Calendar event | `cal-event` | 10 | 600 | 캘린더 이벤트 pill |

### `.eyebrow` 정의
```css
.eyebrow {
  font-size: 10px; font-weight: 700;
  letter-spacing: 0.08em; text-transform: uppercase;
  color: #94A3B8;  /* 기본은 faint, 진하게 필요 시 !text-ink3 추가 */
}
```

### 변형
- **요일 헤더처럼 진한 eyebrow:** `class="eyebrow !text-ink3"`
- **dark 카드 내부 eyebrow:** `style="color:#64748B"` (ink2 위에서 가독성)

---

## 3. Layout

### 3.1 Page Skeleton

```
┌─────────────────────────────────────────────┐
│  body (bg: canvas)                          │
│  ┌──────────┬─────────────────────────────┐ │
│  │ Sidebar  │  Right column               │ │
│  │ 260px    │  flex-1 (header + main)     │ │
│  │ ink bg   │                             │ │
│  │          │  ┌─────────────────────────┐│ │
│  │ logo     │  │ Header 72h (full width) ││ │
│  │ nav      │  └─────────────────────────┘│ │
│  │          │  ┌─────────────────────────┐│ │
│  │ settings │  │ Main max-w 1280         ││ │
│  └──────────┴──┴─────────────────────────┘ │
└─────────────────────────────────────────────┘
```

```html
<body class="min-h-screen">
  <div class="flex min-h-screen">
    <aside class="w-[260px] shrink-0 bg-ink text-white flex flex-col">…</aside>
    <div class="flex-1 min-w-0 flex flex-col">
      <header class="h-[72px] bg-surface border-b border-hair px-8 flex items-center justify-between">…</header>
      <main class="w-full max-w-[1280px] flex flex-col">
        <div class="px-8 py-8 space-y-6 flex-1">…sections…</div>
      </main>
    </div>
  </div>
</body>
```

**고정값:**
- 사이드바 너비: `260px`
- 헤더 높이: `72px`
- 메인 max-width: `1280px`
- 메인 padding: `px-8 py-8` (32px)
- 섹션 간격: `space-y-6` (24px)

### 3.2 Grid

- **표준:** `grid grid-cols-12 gap-6`
- **컬럼 분할 패턴:**
  - 3-up 통계: `col-span-4` × 3
  - 메인 + 사이드: `col-span-8` + `col-span-4`
  - 일정 + 캘린더: `col-span-4` + `col-span-8`

---

## 4. Components

### 4.1 Sidebar

```html
<aside class="w-[260px] shrink-0 bg-ink text-white flex flex-col">
  <!-- Logo -->
  <div class="px-6 py-6 border-b border-white/5">…</div>
  <!-- Nav -->
  <nav class="px-4 py-6 space-y-1 flex-1">
    <a class="sidebar-link is-active">
      <span class="dot"></span>
      <svg>…</svg>
      Dashboard
    </a>
  </nav>
</aside>
```

```css
.sidebar-link {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px; border-radius: 8px;
  color: #94A3B8; font-size: 13px; font-weight: 500;
  transition: background .15s ease, color .15s ease;
}
.sidebar-link:hover,
.sidebar-link.is-active { background: #1E293B; color: #fff; }
.sidebar-link .dot { width: 3px; height: 18px; border-radius: 2px; background: transparent; margin-right: -8px; }
.sidebar-link.is-active .dot { background: #fff; }
```

- **로고 영역:** `px-6 py-6`, 하단에 `border-b border-white/5`
- **Nav padding:** `px-4 py-6 space-y-1`
- **active 표시:** 좌측에 `3×18px` 흰색 dot + 배경 ink2

### 4.2 Top Header

```html
<header class="h-[72px] bg-surface border-b border-hair px-8 flex items-center justify-between">
  <div>
    <div class="eyebrow">데스크 · 헤드헌팅</div>
    <h1 class="text-[22px] font-bold tracking-tight mt-1">Executive Search Dashboard</h1>
  </div>
  <div class="flex items-center gap-5">
    <div class="text-right">…date/time…</div>
    <button class="w-9 h-9 rounded-full hover:bg-line flex items-center justify-center text-muted">…</button>
    <div class="flex items-center gap-3 pl-5 border-l border-hair">…user…</div>
  </div>
</header>
```

- 높이 `72px` 고정
- 페이지 타이틀: eyebrow 브래드크럼 + H1 22px/700
- 우측 액션: 32×32 둥근 아이콘 버튼들 + 좌측 디바이더 + 사용자 영역

### 4.3 Card (Standard)

```html
<article class="bg-surface rounded-card shadow-card p-6">
  <div class="flex items-start justify-between">
    <div class="eyebrow">Section Label</div>
    <svg width="16" height="16">…</svg>
  </div>
  <!-- content -->
</article>
```

- **컨테이너:** `bg-surface rounded-card shadow-card p-6`
- **상단:** eyebrow 라벨 + 우측 16px 아이콘 (color: `#94A3B8`)
- **hover:** 자동 lift (rounded-card에 전역 적용)

### 4.4 Card (Dark Accent)

페이지 내 **단 하나** 사용. 핵심 KPI 강조용.

```html
<article class="bg-ink text-white rounded-card shadow-lift p-6 flex flex-col">
  <div class="eyebrow" style="color:#64748B">Estimated Revenue</div>
  <div class="text-[40px] leading-none font-bold tnum mt-6">₩ 842,500</div>
  <div class="mt-auto pt-6">
    <div class="progress" style="background:#1E293B"><span style="width:76%; background:#fff"></span></div>
  </div>
</article>
```

- 배경 `bg-ink`, eyebrow는 `#64748B`로 가독성 확보
- 내부 progress 트랙은 `#1E293B`, fill은 `#fff`

### 4.5 Stat Number

```html
<div class="flex items-baseline gap-3">
  <span class="text-[40px] leading-none font-bold tnum">24</span>
  <span class="text-sm text-muted">Projects Closed</span>
</div>
```

- 메인 숫자 40px/700/tnum
- 라벨 14px/regular/muted, baseline 정렬

### 4.6 Status Dot + Label

```html
<li class="flex items-center justify-between">
  <div class="flex items-center gap-2">
    <span class="status-dot" style="background:#10B981"></span>
    <span class="text-sm">진행 (Active)</span>
  </div>
  <span class="text-lg font-bold tnum">42</span>
</li>
```

```css
.status-dot { width: 6px; height: 6px; border-radius: 999px; display: inline-block; }
```

- 점: 6×6 원
- success/warning/info/danger 색상 직접 사용

### 4.7 Progress Bar

```css
.progress { height: 4px; border-radius: 999px; background: #E2E8F0; overflow: hidden; }
.progress > span { display: block; height: 100%; background: #334155; border-radius: 999px; }
.progress.success > span { background: #10B981; }
.progress.info > span { background: #6366F1; }
```

```html
<div class="progress success"><span style="width:92%"></span></div>
```

- 트랙 4px / 라운드 full
- variant: default(ink3), `.success`(emerald), `.info`(indigo)

### 4.8 Avatar

```html
<div class="w-11 h-11 rounded-full bg-gradient-to-br from-slate-300 to-slate-500
            flex items-center justify-center text-white font-semibold text-sm">MK</div>
```

- 표준 크기: 44×44 (`w-11 h-11`)
- 헤더 사용자 영역: 40×40 (`w-10 h-10`, `bg-ink2`)
- 그라디언트 컬러는 사람별로 임의 (slate/amber/indigo) — 일관된 톤만 유지

### 4.9 Chip / Pill

```css
.chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: 999px;
  font-size: 12px; font-weight: 500; color: #334155;
  background: #F1F5F9;
}
.chip.is-active { background: #0F172A; color: #fff; }
```

- 일반: `line` 배경 + `ink3` 텍스트
- 활성: `ink` 배경 + 흰색 텍스트

### 4.10 Activity List Item

```html
<li class="flex gap-3">
  <div class="w-7 h-7 rounded-full bg-emerald-50 text-success flex items-center justify-center shrink-0 mt-0.5">
    <svg width="14" height="14">…</svg>
  </div>
  <div class="min-w-0">
    <div class="text-sm font-semibold leading-snug">Title</div>
    <div class="text-[11px] text-faint mt-0.5">Meta · 2h ago</div>
  </div>
</li>
```

- 좌측 아이콘 칩: 28×28, semantic color의 50 톤 배경 + 본 컬러 아이콘
- 메타 라인: 11px / faint, eyebrow 스타일 **사용 안 함**(소문자 그대로)

### 4.11 Calendar

```html
<article class="bg-surface rounded-card shadow-card overflow-hidden">
  <!-- Weekday header -->
  <div class="grid grid-cols-7 border-b-2 bg-canvas" style="border-bottom-color:#EEF2F7">
    <div class="eyebrow text-center py-3 !text-ink3">Sun</div>
    …
  </div>
  <!-- Date grid -->
  <div class="grid grid-cols-7 [&>*]:-ml-0.5 [&>*]:-mt-0.5">
    <div class="cal-day"><span class="tnum">1</span></div>
    <div class="cal-day today">
      <span class="tnum">25</span>
      <div class="cal-event">Interview</div>
    </div>
    …
  </div>
</article>
```

```css
.cal-day {
  aspect-ratio: 1/1;
  display: flex; flex-direction: column;
  padding: 12px 14px;
  border: 2px solid #EEF2F7;
  background: #FFFFFF;
  transition: background .15s ease;
}
.cal-day:hover { background: #F8FAFC; }
.cal-day > .tnum { font-size: 14px; font-weight: 600; color: #0F172A; line-height: 1; }
.cal-day.muted > .tnum { color: #CBD5E1; font-weight: 500; }
.cal-day.today > .tnum {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px;
  background: #0F172A; color: #fff;
  border-radius: 999px;
  font-size: 12px;
  margin: -5px -6px;
}
.cal-event {
  margin-top: 8px;
  font-size: 10px; padding: 4px 10px; border-radius: 999px;
  background: #F1F5F9; color: #334155; font-weight: 600;
  align-self: flex-start;
}
.cal-day.today .cal-event { background: #0F172A; color: #fff; }

/* Internal-only borders */
.cal-day:nth-child(-n+7)    { border-top: 0; margin-top: 0 !important; }
.cal-day:nth-child(7n+1)    { border-left: 0; }
.cal-day:nth-child(7n)      { border-right: 0; }
.cal-day:nth-last-child(-n+7) { border-bottom: 0; }
```

**규칙:**
- 카드는 `overflow-hidden`로 모서리 클리핑
- 셀은 흰색, 헤더 행은 캔버스 톤
- 보더는 **내부에만**, 4면 외곽은 0
- 보더 색은 일반 hair보다 한 단계 연한 `#EEF2F7`
- 셀 hover: 캔버스 톤으로 살짝 어두워짐
- today: 셀 전체가 아닌 **숫자만** ink 원형 칩 (26×26)
- today의 이벤트 pill만 ink 반전

### 4.12 Floating Action Button (FAB)

```html
<button class="fixed bottom-8 right-8 w-14 h-14 rounded-full bg-ink text-white
               shadow-fab hover:bg-ink2 transition-colors flex items-center justify-center">
  <svg width="22" height="22">…</svg>
</button>
```

- 56×56, ink 배경, shadow-fab
- hover 시 ink2로 색만 변경

### 4.13 Section Eyebrow Header

섹션 안에 라벨 + (선택) 우측 액션:

```html
<div class="flex items-center justify-between">
  <div class="eyebrow">Team Performance</div>
  <a href="#" class="text-xs font-semibold text-ink3 hover:underline">VIEW ALL MEMBERS →</a>
</div>
```

---

## 5. Iconography

- **라이브러리:** Lucide (인라인 SVG)
- **공통 속성:**
  - `fill="none"`
  - `stroke="currentColor"`
  - `stroke-width="2"` (디테일 강조 시 2.2~2.5)
  - `stroke-linecap="round" stroke-linejoin="round"`
- **사이즈:**
  - 14×14 — 인라인 컨트롤, activity item 내부
  - 16×16 — 카드 우상단 데코 아이콘
  - 18×18 — 사이드바 nav, 헤더 액션 버튼
  - 22×22 — FAB
- **컬러:** 카드 데코는 `#94A3B8` (faint), 인터랙티브는 `text-muted`/`text-ink`/semantic

---

## 6. 패턴 규칙 (Do/Don't)

### Do
- 카드 padding은 항상 `p-6`
- 그리드 gap은 항상 `gap-6`
- 숫자 표시는 항상 `.tnum`
- 모든 카드에 `rounded-card shadow-card`
- 섹션 라벨은 `eyebrow`로 통일
- hover lift는 자동 적용 (별도 클래스 불필요)

### Don't
- 카드에 `rounded-lg`/`rounded-xl` 직접 사용 금지 → `rounded-card`
- 임의의 그림자 정의 금지 → `shadow-card`/`shadow-lift`/`shadow-fab` 중 선택
- 임의 컬러 hex 금지 → 토큰 사용 (Tailwind 클래스 또는 `style`로 토큰 인용)
- 다크 카드 2개 이상 금지 (강조 분산)
- `Inter`, `Roboto`, `Noto Sans` 등 다른 폰트 사용 금지 → Pretendard 고정
- 보라/파랑 그라디언트 CTA 금지 → ink 단색
- 컬러풀한 브랜드 컬러 추가 금지

---

## 7. Tailwind 설정 사본

`tailwind.config.js`에 아래 그대로 반영 (현재는 CDN inline config, 빌드 시 동일 값으로):

```js
{
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Pretendard Variable"', 'Pretendard', '-apple-system',
               'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
      },
      colors: {
        canvas: '#F8FAFC', surface: '#FFFFFF',
        ink: '#0F172A', ink2: '#1E293B', ink3: '#334155',
        muted: '#64748B', faint: '#94A3B8',
        hair: '#E2E8F0', line: '#F1F5F9',
        success: '#10B981', warning: '#F59E0B',
        info: '#6366F1', danger: '#EF4444',
      },
      boxShadow: {
        card: '0 1px 2px 0 rgba(15,23,42,0.04), 0 1px 3px 0 rgba(15,23,42,0.06)',
        lift: '0 4px 6px -1px rgba(15,23,42,0.08), 0 2px 4px -2px rgba(15,23,42,0.04)',
        fab:  '0 10px 15px -3px rgba(15,23,42,0.15), 0 4px 6px -2px rgba(15,23,42,0.08)',
      },
      borderRadius: { card: '16px' },
    },
  },
}
```

---

## 8. 마이그레이션 체크리스트 (기존 템플릿 적용 시)

각 화면을 업데이트할 때 다음을 확인:

- [ ] 모든 폰트가 Pretendard로 통일됐는가
- [ ] 컬러가 위 토큰만 사용하는가 (임의 hex 0개)
- [ ] 카드는 `rounded-card shadow-card p-6` 패턴인가
- [ ] 사이드바 구조와 너비(260px)가 일치하는가
- [ ] 헤더 높이 72px, 메인 max-width 1280px인가
- [ ] 섹션 라벨이 `eyebrow` 클래스인가
- [ ] 숫자에 `.tnum`이 적용됐는가
- [ ] 페이지 내 다크 강조 카드가 1개 이하인가
- [ ] 상태 컬러를 의미 그대로 사용했는가 (장식 아님)
- [ ] hover 시 카드가 lift되는가 (rounded-card 적용 시 자동)
- [ ] 아이콘이 Lucide stroke 스타일인가
