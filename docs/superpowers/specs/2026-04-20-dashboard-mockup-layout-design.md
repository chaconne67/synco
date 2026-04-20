# Dashboard 목업 레이아웃 · Phase 1 (하드코딩)

## 목적

`/dashboard/` 콘텐츠 영역을 `assets/ui-sample/dashboard.html` 목업대로 교체. 사이드바·상단바는 유지. 모든 값은 하드코딩 — 실데이터 연결은 Phase 2에서 카드 단위로 별도 진행.

## 적용 범위

**변경**
- `projects/templates/projects/dashboard.html` — 새 partial로 `{% include %}` 교체
- `projects/templates/projects/partials/dash_full.html` — 전체 재작성 (기존 greeting/Overdue/Today/To-Do 전부 버림)
- `projects/views.py` 의 `dashboard()` 뷰 — context 최소화 (하드코딩이므로 쿼리 불필요)
- `main/urls.py` — 하위 라우트 제거
- `static/css/input.css` — S1 에서 `.progress.dark` 추가, S3 에서 `.cal-day` · `.cal-event` 컴포넌트 추가

**유지**
- `templates/common/base.html` — 사이드바·상단바
- `templates/common/nav_sidebar.html` — 그대로
- 상단바 breadcrumb_current · page_title 블록 = 기존("Dashboard") 유지
- `dashboard(request)` 뷰 자체 · URL `/dashboard/` 이름 · `membership_required` 데코레이터

**제거**
- 뷰: `dashboard_actions`, `dashboard_todo_partial`, `dashboard_team` (다른 곳에서 참조 없음 확인 후)
- URL: `dashboard/todo/`, `dashboard/actions/`, `dashboard/team/`
- 파일: `projects/templates/projects/partials/dash_actions.html`
- 파일: `projects/templates/projects/partials/action_item_card.html` (다른 곳 참조 없음 확인 후)
- 파일: `projects/templates/projects/dashboard/index.html` (사용 확인 후 제거 가능하면 제거)

## 공통 구현 원칙

- 디자인 시스템(`docs/design-system.md`) 토큰만 사용 — 임의 hex 금지
- **Tailwind 기본 font-size 토큰만** — `text-xs`/`text-sm`/`text-base`/`text-lg`/`text-xl`/`text-4xl` 등. 인라인 `text-[Xpx]` 절대 금지
- 카드는 `bg-surface rounded-card shadow-card p-6` 패턴
- 그리드 gap은 `gap-6`, 섹션 간격 `space-y-6`
- 메인 래퍼: `<div class="max-w-[1280px] mx-auto w-full"><div class="px-8 py-8 space-y-6">…</div></div>`
- 숫자 표시는 항상 `.tnum`
- 섹션 라벨은 `.eyebrow` (영문) / `.eyebrow-ko` (한글) — 둘 다 `input.css` 기존 정의 사용
- 아이콘은 Lucide stroke 스타일 인라인 SVG
- 모든 커스텀 CSS는 `static/css/input.css` `@layer components` 에 정의 — 템플릿 `<style>` 블록 금지

## 스테이지

각 스테이지 = 독립 커밋. 매 스테이지 직후 사용자 QA.

### S1 — 상단 3 stat cards
`<section class="grid grid-cols-12 gap-6">` 안에 col-span-4 × 3.

1. **Monthly Success** (`bg-surface rounded-card shadow-card p-6 flex flex-col`)
   - 상단: eyebrow "Monthly Success" + 16px line-chart SVG (`stroke="#94A3B8"`)
   - `mt-6 flex items-baseline gap-3`: `text-4xl leading-none font-bold tnum` `24` + `text-sm text-muted` `종료된 프로젝트`
   - `mt-6 pt-5 border-t border-line grid grid-cols-2 gap-4`:
     - 진행 중 — eyebrow-ko + `text-xl font-bold tnum` `12`
     - 성공률 — eyebrow-ko + `text-xl font-bold tnum` `82`(%는 text-sm muted)

2. **Estimated Revenue** (다크 강조 카드 — 페이지 내 유일)
   - `bg-ink text-white rounded-card shadow-lift p-6 flex flex-col`
   - eyebrow · 16px credit-card SVG · "목표 달성률" eyebrow-ko — 모두 `!text-muted` 로 색 override (다크카드 위 가독성)
   - `mt-6 text-4xl leading-none font-bold tnum` `₩ 842,500`
   - `mt-auto pt-6`: eyebrow-ko + `text-xs font-semibold tnum` `76%` 우측 + progress (dark 버전 — 아래 CSS 보강 참조)
   - CSS 보강: `input.css` 에 `.progress.dark { background: #1E293B; }` + `.progress.dark > span { background: #fff; }` 추가. 템플릿은 `<div class="progress dark"><span style="width:76%"></span></div>` (width만 인라인)

3. **Project Status** (`bg-surface rounded-card shadow-card p-6`)
   - eyebrow "Project Status" + 16px bar-chart SVG faint
   - `mt-6 ul space-y-4`:
     - `status-dot` success `#10B981` + `text-sm font-medium text-ink2` "진행" + right `text-lg font-bold tnum` `42`
     - warning `#F59E0B` + "심사" + `18`
     - info `#6366F1` + "완료" + `114`

### S2 — Team Performance + Recent Activity
`<section class="grid grid-cols-12 gap-6">`.

1. **Team Performance** — `<article class="col-span-8 bg-surface rounded-card shadow-card p-6">`
   - 상단 flex: eyebrow "Team Performance" / 우측 `<a class="text-xs font-semibold text-ink3 hover:underline">전체 멤버 보기 →</a>`
   - `mt-6 ul space-y-5`, 각 row `flex items-center gap-4`:
     - 44px 아바타 원 (`w-11 h-11 rounded-full bg-gradient-to-br from-[slate|amber|indigo]-200 to-[same]-500 text-white font-semibold text-sm`) + 이니셜
     - 이름 블록 `w-[180px] shrink-0`: `text-sm font-semibold` 이름 + eyebrow-ko 직함
     - 프로젝트 수 블록 `w-[140px] shrink-0`: eyebrow-ko "현재 프로젝트" + `text-sm font-semibold` "N건 진행 중"
     - flex-1 progress 블록: 내부 상단 flex 사이 eyebrow-ko "달성률" + `text-xs font-semibold tnum text-ink3` `92%` / `progress success`
   - 3개 멤버: Min-ho Kim (수석 컨설턴트, 8건, 92% success) · Sarah Park (시니어, 5건, 75% default) · Ji-won Lee (리서치, 12건, 48% info)

2. **Recent Activity** — `<article class="col-span-4 bg-surface rounded-card shadow-card p-6">`
   - 상단: eyebrow "Recent Activity" + 14px refresh 아이콘 버튼 `text-faint hover:text-ink`
   - `mt-5 ul space-y-4`, 각 item `flex gap-3`:
     - 28px 원형 아이콘 칩 `w-7 h-7 rounded-full bg-[emerald|indigo|amber|red]-50 text-[success|info|warning|danger]` + 14px 아이콘
     - 본문 `min-w-0`: `text-sm font-semibold leading-snug` 제목 + `mt-0.5 text-xs text-faint` 메타
   - 4개 아이템 (목업 그대로):
     1. success · 후보자 배치가 확정되었습니다 / 프로젝트 클라우드 / CTO 서치 · 2시간 전
     2. info · 새 후보자가 추가되었습니다 / 글로벌 핀테크 확장 · 5시간 전
     3. warning · 고객사 미팅 노트가 업데이트되었습니다 / 삼성전자 자문 프로젝트 · 어제
     4. danger · 프로젝트 마감일이 가까워지고 있습니다 / 재생에너지 헤드 서치 · 2일 전

### S3 — Weekly Schedule + Monthly Calendar
`<section class="grid grid-cols-12 gap-6">`.

1. **Weekly Schedule** — `<div class="col-span-4">`
   - 상단 eyebrow "Weekly Schedule" `mb-4`
   - `space-y-4`, 3 카드. 각 카드 = `bg-surface rounded-card shadow-card p-5`:
     - 상단 flex: 날짜 eyebrow-ko (1번 `!text-ink3`, 2번 `!text-info`, 3번 `!text-warning`) + 14px dots-menu 버튼
     - `mt-3 text-base font-semibold leading-snug` 제목 + `text-xs text-muted mt-1` 메타
   - 3개 아이템:
     1. 10월 23일 월요일 · 09:00 / 주간 파이프라인 리뷰 / 내부 팀 세션 · A 회의실 (ink3)
     2. 10월 25일 수요일 · 11:00 / 임원 인터뷰 / 후보자: 박해준 · Zoom (info)
     3. 10월 27일 금요일 · 14:00 / 고객사 브리핑: SK하이닉스 / 전략기획 · 본사 (warning)

2. **Monthly Calendar** — `<div class="col-span-8">`
   - 상단 eyebrow "Monthly Schedule" `mb-4`
   - `<article class="bg-surface rounded-card shadow-card overflow-hidden">`
   - 요일 헤더 `grid grid-cols-7 border-b border-hair`:
     - 일(`!text-red-600`) / 월·화·수·목·금(`!text-ink2`) / 토(`!text-blue-600`)
     - 각 `eyebrow eyebrow-ko text-center py-3`
   - 날짜 그리드 `grid grid-cols-7 [&>*]:-ml-0.5 [&>*]:-mt-0.5`
   - 구현: 2023년 10월 기준, trailing prev(24-30 muted) + Week1~5 + leading next(1-4 muted). today = 25일.
   - 이벤트 배치 (목업 동일):
     - 4일 · `이사회`
     - 23일 · `주간 리뷰`
     - 25일(today) · `인터뷰`
     - 27일 · `SK하이닉스`
   - CSS 새로 추가 (`input.css`):
     - `.cal-day` 셀 스타일 (design-system §4.11 블록 그대로)
     - `.cal-event` pill
     - 내부-only 보더 규칙 (nth-child)
     - 주말 컬러 (일 red-600, 토 blue-600)
     - today 원형 칩 + 이벤트 반전

### S4 — 정리
- `projects/views.py`: `dashboard_actions` · `dashboard_todo_partial` · `dashboard_team` 함수 제거 (사용처 없음 확인 후)
- `main/urls.py`: 해당 3개 라우트 제거 + 임포트 정리
- `projects/templates/projects/partials/dash_actions.html` 삭제
- `projects/templates/projects/partials/action_item_card.html` — 다른 템플릿에서 참조 없는지 grep 확인 후 삭제
- `projects/templates/projects/dashboard/index.html` — 라우트에서 참조되는지 확인 후 판단
- `dashboard(request)` 뷰 본문 단순화: `return render(request, "projects/dashboard.html")` 수준

## 타이포 매핑 (목업 → Tailwind 토큰)

| 목업 원본 | 치환 토큰 | 비고 |
|---|---|---|
| `text-[40px]` (stat hero) | `text-4xl` (36px) | 디자인 시스템 §1.2 준수 |
| `text-[15px]` (weekly item 제목) | `text-base` (16px) | 반올림 |
| `text-[22px]` (헤더) | 해당 없음 | 상단바 미변경 |
| `text-[13px]` (sidebar) | 해당 없음 | 사이드바 미변경 |
| `text-[10px]` (cal-event) | `.cal-event` CSS에서 `font-size:10px` | 클래스 내부라 OK |

## 컬러 / 스타일 규칙

- **인라인 `style=`는 progress bar의 동적 `width:Npx` 한 용도만 허용.** 그 외 모든 색·배경은 Tailwind 토큰 클래스 또는 `input.css` 컴포넌트 클래스로 표현
- 컬러 override 시 `!important` 수정자 사용 (예: `!text-muted`, `!text-ink3`) — `.eyebrow`의 CSS 색상을 덮어쓰기 위함
- 주말 컬러는 Tailwind 기본 팔레트 (`red-600`/`blue-600`) 허용 — 빨강/파랑이라는 관용 시각 코드는 상태 토큰에 없음
- **금지**: 좌측 border-stripe, 그라디언트 CTA, `rounded-xl`/`rounded-lg` 직접 사용(카드), 임의 그림자, 임의 hex, 인라인 `text-[Xpx]`
- Status 컬러는 의미 전용 (success=진행, warning=심사/주의, info=완료/정보, danger=경고)

## 하드코딩 데이터 상수

| 항목 | 값 |
|---|---|
| Monthly Success / 종료 | 24 |
| Monthly Success / 진행중 | 12 |
| Monthly Success / 성공률 | 82% |
| Estimated Revenue | ₩ 842,500 |
| Estimated Revenue / 목표 달성률 | 76% |
| Project Status | 진행 42 / 심사 18 / 완료 114 |
| Team | Min-ho Kim 8건 92% · Sarah Park 5건 75% · Ji-won Lee 12건 48% |
| Recent Activity | 4건 (success / info / warning / danger) |
| Weekly Schedule | 3건 (10/23 · 10/25 · 10/27) |
| Monthly Calendar | 2023-10, today=25, 4개 이벤트 |

## QA 체크리스트 (사용자 수동)

각 스테이지 커밋 직후:
- [ ] 레이아웃이 목업과 시각적으로 일치
- [ ] max-w-1280 · px-8 py-8 · gap-6 · space-y-6 적용
- [ ] 카드 `rounded-card shadow-card p-6`
- [ ] 다크 카드는 Estimated Revenue 1개뿐
- [ ] 숫자에 `.tnum`
- [ ] 인라인 `text-[Xpx]` 0건 (grep으로 확인)
- [ ] 인라인 `style="color:#...` / `style="background:#..."` 0건 (`style="width:..."`만 허용)
- [ ] hover lift 동작 (카드 2px 상승 + shadow 증가)
- [ ] S4 후 기존 Overdue/Today/To-Do 섹션 · 관련 뷰·URL·partial 전부 제거

## 범위 외 (Phase 2에서 처리)

- Monthly Success / Estimated Revenue / Project Status / Team Performance / Recent Activity / Weekly Schedule / Monthly Calendar 각각의 실쿼리 연결
- 각 카드별 클릭/드릴다운 라우팅
- 날짜 동적 계산 (today, 이전/다음달 flip)
- 데이터 없을 때 empty state
