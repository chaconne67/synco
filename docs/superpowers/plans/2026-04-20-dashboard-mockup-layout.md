# Dashboard Mockup Layout — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/dashboard/` 콘텐츠 영역을 [`assets/ui-sample/dashboard.html`](../../../assets/ui-sample/dashboard.html) 목업대로 교체. 모든 값 하드코딩. 사이드바·상단바 미변경.

**Architecture:** 기존 `projects/templates/projects/partials/dash_full.html` 를 완전 재작성. `dashboard()` 뷰 context를 비우고, 더 이상 필요 없는 3개 HTMX 뷰·URL·partial·테스트를 S4 에서 제거. 커스텀 CSS는 `static/css/input.css` 의 `@layer components` 에만 추가.

**Tech Stack:** Django template · Tailwind (CDN config + `input.css` 빌드) · HTMX (기존 네비게이션 유지)

**Spec:** [docs/superpowers/specs/2026-04-20-dashboard-mockup-layout-design.md](../specs/2026-04-20-dashboard-mockup-layout-design.md)

---

## 전제 · 제약

- Django dev server 와 Tailwind watch 는 **사용자가 이미 실행 중** (dev.sh). 에이전트가 `runserver` 또는 `npx tailwindcss --watch` 를 띄우지 않는다
- 시각 QA 는 **각 스테이지 커밋 직후 사용자가 수동 수행**. 에이전트는 브라우저로 테스트하지 않음
- UI 변경 후에는 수정된 URL 을 보고만 한다 — 사용자가 로컬 브라우저로 확인
- 이 작업은 순수 템플릿·CSS·뷰 정리 → 새로운 Python 단위 테스트 추가는 없다. 기존 테스트가 제거 대상 뷰를 참조하는 경우 S4 에서 동기 삭제

## 파일 맵

### 수정
| 파일 | 역할 |
|---|---|
| `projects/templates/projects/partials/dash_full.html` | **전체 재작성**. 3개 `<section>` (S1·S2·S3) |
| `projects/views.py` | `dashboard()` 뷰 context 최소화, 3개 뷰 함수 제거 (S4) |
| `main/urls.py` | `dashboard_todo`·`dashboard_actions`·`dashboard_team` 라우트 및 import 제거 (S4) |
| `static/css/input.css` | `@layer components` 에 `.progress.dark` (S1) · `.cal-day` · `.cal-event` · 요일 컬러 규칙 (S3) 추가 |

### 삭제 (S4)
| 파일 | 삭제 근거 |
|---|---|
| `projects/templates/projects/partials/dash_actions.html` | `dashboard_actions` 뷰 전용. 뷰 제거 시 고아 |
| `projects/templates/projects/partials/dash_admin.html` | `dashboard_team` 뷰 전용 |
| `projects/templates/projects/partials/dashboard_todo_list.html` | `dashboard_todo_partial` 뷰 전용 |
| `projects/templates/projects/dashboard/index.html` | 현재 어떤 뷰에서도 렌더 안 됨(grep 확인) |

### 유지 (삭제 금지)
| 파일 | 이유 |
|---|---|
| `projects/templates/projects/partials/action_item_card.html` | `application_actions_list.html` 에서 `{% include %}` 사용 중 |
| `projects/services/dashboard.py` | `get_project_kanban_cards` (views.py:115) 와 `get_today_actions` (voice/action_executor.py) 에서 사용 |

### 테스트 파일 (S4 에서 업데이트)
| 파일 | 조치 |
|---|---|
| `tests/test_views_dashboard.py` | `reverse("dashboard_todo")` 참조 1건 — 해당 테스트 제거 |
| `tests/test_p13_dashboard.py` | `test_dashboard_actions_partial`, `test_dashboard_team_owner_only` + dashboard context 의존 테스트 — 제거 또는 스킵 |
| `tests/accounts/test_rbac.py` | `test_consultant_cannot_access_dashboard_team`, `test_consultant_can_access_dashboard_actions` — 2개 메서드 제거 |

---

## Task 1 · S1 — 상단 3 stat cards

**Files:**
- Modify: `static/css/input.css` (progress.dark 규칙 추가)
- Rewrite: `projects/templates/projects/partials/dash_full.html`
- Modify: `projects/views.py:2141-2191` (dashboard 뷰 context 비움)

- [ ] **Step 1: `input.css` 에 `.progress.dark` 추가**

`static/css/input.css` 의 `@layer components` 안에서 기존 `.progress.info` 규칙 **다음** (Grep 으로 `.progress.info` 찾을 것, 현재 line 111 근처) 에 아래 블록 삽입:

```css
  .progress.dark { background: #1E293B; }
  .progress.dark > span { background: #FFFFFF; }
```

- [ ] **Step 2: `dashboard()` 뷰 단순화**

`projects/views.py` 의 `dashboard` 함수(line 2141-2191) 전체를 아래로 교체:

```python
@login_required
@membership_required
def dashboard(request):
    """대시보드 메인 화면 (Phase 1: 하드코딩 목업)."""
    if getattr(request, "htmx", None):
        return render(request, "projects/partials/dash_full.html")
    return render(request, "projects/dashboard.html")
```

라인 2148-2187 의 service import 와 context 빌드 로직을 전부 제거. `_get_org`·`get_today_actions` 등은 이 뷰에서 더 이상 참조하지 않는다.

- [ ] **Step 3: `dash_full.html` 을 S1 버전으로 재작성**

`projects/templates/projects/partials/dash_full.html` 을 아래로 **전체 교체**:

```html
{# Dashboard content — Phase 1 hardcoded mockup. Real data wiring in Phase 2. #}
<div class="max-w-[1280px] mx-auto w-full">
  <div class="px-8 py-8 space-y-6">

    {# ============ S1: TOP ROW — 3 stat cards ============ #}
    <section class="grid grid-cols-12 gap-6">

      {# Monthly Success #}
      <article class="col-span-4 bg-surface rounded-card shadow-card p-6 flex flex-col">
        <div class="flex items-start justify-between">
          <div class="eyebrow">Monthly Success</div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
        </div>
        <div class="mt-6 flex items-baseline gap-3">
          <span class="text-4xl leading-none font-bold tnum">24</span>
          <span class="text-sm text-muted">종료된 프로젝트</span>
        </div>
        <div class="mt-6 pt-5 border-t border-line grid grid-cols-2 gap-4">
          <div>
            <div class="eyebrow eyebrow-ko">진행 중</div>
            <div class="mt-1 text-xl font-bold tnum">12</div>
          </div>
          <div>
            <div class="eyebrow eyebrow-ko">성공률</div>
            <div class="mt-1 text-xl font-bold tnum">82<span class="text-sm text-muted font-medium">%</span></div>
          </div>
        </div>
      </article>

      {# Estimated Revenue (dark accent — page-unique) #}
      <article class="col-span-4 bg-ink text-white rounded-card shadow-lift p-6 flex flex-col">
        <div class="flex items-start justify-between">
          <div class="eyebrow !text-muted">Estimated Revenue</div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748B" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" x2="22" y1="10" y2="10"/></svg>
        </div>
        <div class="mt-6">
          <div class="text-4xl leading-none font-bold tnum">₩ 842,500</div>
        </div>
        <div class="mt-auto pt-6">
          <div class="flex items-center justify-between mb-2">
            <div class="eyebrow eyebrow-ko !text-muted">목표 달성률</div>
            <div class="text-xs font-semibold tnum">76%</div>
          </div>
          <div class="progress dark"><span style="width:76%"></span></div>
        </div>
      </article>

      {# Project Status #}
      <article class="col-span-4 bg-surface rounded-card shadow-card p-6">
        <div class="flex items-start justify-between">
          <div class="eyebrow">Project Status</div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><rect width="4" height="7" x="7" y="10" rx="1"/><rect width="4" height="12" x="15" y="5" rx="1"/></svg>
        </div>
        <ul class="mt-6 space-y-4">
          <li class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="status-dot bg-success"></span>
              <span class="text-sm font-medium text-ink2">진행</span>
            </div>
            <span class="text-lg font-bold tnum">42</span>
          </li>
          <li class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="status-dot bg-warning"></span>
              <span class="text-sm font-medium text-ink2">심사</span>
            </div>
            <span class="text-lg font-bold tnum">18</span>
          </li>
          <li class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="status-dot bg-info"></span>
              <span class="text-sm font-medium text-ink2">완료</span>
            </div>
            <span class="text-lg font-bold tnum">114</span>
          </li>
        </ul>
      </article>
    </section>

  </div>
</div>
```

노트:
- SVG `stroke="#94A3B8"` 와 `stroke="#64748B"` 는 SVG `stroke` 속성이며 템플릿 CSS 아님 → Tailwind 토큰 변환 대상 아님. 그대로 유지.
- `.status-dot` 는 기존 `input.css` 정의 사용. `bg-success`·`bg-warning`·`bg-info` Tailwind 클래스로 색 지정.

- [ ] **Step 4: ruff 실행**

```bash
uv run ruff check projects/views.py
uv run ruff format projects/views.py
```

Expected: no errors, 0 files reformatted (or 1 file formatted).

- [ ] **Step 5: 사용자 시각 QA 대기**

에이전트는 여기서 멈춘다. 보고할 내용:
- 변경 파일 목록
- 확인 URL: `http://localhost:8000/dashboard/`
- 기대 화면: 상단 3 cards (Monthly Success / Estimated Revenue 다크 / Project Status). 중간·하단 영역은 비어 있음
- 사용자 QA 후 수정 반영 → 승인 받으면 Step 6 으로

- [ ] **Step 6: Commit**

```bash
git add static/css/input.css projects/views.py projects/templates/projects/partials/dash_full.html
git commit -m "$(cat <<'EOF'
feat(dashboard): S1 top 3 stat cards (hardcoded mockup)

Monthly Success / Estimated Revenue (dark) / Project Status 카드
목업대로 구현. dashboard 뷰 context 최소화.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 · S2 — Team Performance + Recent Activity

**Files:**
- Modify: `projects/templates/projects/partials/dash_full.html` (S1 section 아래에 S2 section 추가)

- [ ] **Step 1: `dash_full.html` 에 S2 section 추가**

Task 1 에서 작성된 `dash_full.html` 의 **S1 섹션 `</section>` 직후** (`</section>` 한 줄 뒤, 아직 `</div>` 전)에 아래 블록 삽입:

```html
    {# ============ S2: MIDDLE ROW — team + activity ============ #}
    <section class="grid grid-cols-12 gap-6">

      {# Team Performance #}
      <article class="col-span-8 bg-surface rounded-card shadow-card p-6">
        <div class="flex items-center justify-between">
          <div class="eyebrow">Team Performance</div>
          <a href="#" class="text-xs font-semibold text-ink3 hover:underline">전체 멤버 보기 →</a>
        </div>

        <ul class="mt-6 space-y-5">
          <li class="flex items-center gap-4">
            <div class="w-11 h-11 rounded-full bg-gradient-to-br from-slate-300 to-slate-500 flex items-center justify-center text-white font-semibold text-sm">MK</div>
            <div class="w-[180px] shrink-0">
              <div class="text-sm font-semibold">Min-ho Kim</div>
              <div class="eyebrow eyebrow-ko mt-0.5 !text-faint">수석 컨설턴트</div>
            </div>
            <div class="w-[140px] shrink-0">
              <div class="eyebrow eyebrow-ko">현재 프로젝트</div>
              <div class="text-sm font-semibold mt-0.5">8건 진행 중</div>
            </div>
            <div class="flex-1">
              <div class="flex items-center justify-between mb-1.5">
                <div class="eyebrow eyebrow-ko">달성률</div>
                <div class="text-xs font-semibold tnum text-ink3">92%</div>
              </div>
              <div class="progress success"><span style="width:92%"></span></div>
            </div>
          </li>

          <li class="flex items-center gap-4">
            <div class="w-11 h-11 rounded-full bg-gradient-to-br from-amber-200 to-amber-500 flex items-center justify-center text-white font-semibold text-sm">SP</div>
            <div class="w-[180px] shrink-0">
              <div class="text-sm font-semibold">Sarah Park</div>
              <div class="eyebrow eyebrow-ko mt-0.5 !text-faint">시니어 컨설턴트</div>
            </div>
            <div class="w-[140px] shrink-0">
              <div class="eyebrow eyebrow-ko">현재 프로젝트</div>
              <div class="text-sm font-semibold mt-0.5">5건 진행 중</div>
            </div>
            <div class="flex-1">
              <div class="flex items-center justify-between mb-1.5">
                <div class="eyebrow eyebrow-ko">달성률</div>
                <div class="text-xs font-semibold tnum text-ink3">75%</div>
              </div>
              <div class="progress"><span style="width:75%"></span></div>
            </div>
          </li>

          <li class="flex items-center gap-4">
            <div class="w-11 h-11 rounded-full bg-gradient-to-br from-indigo-200 to-indigo-500 flex items-center justify-center text-white font-semibold text-sm">JL</div>
            <div class="w-[180px] shrink-0">
              <div class="text-sm font-semibold">Ji-won Lee</div>
              <div class="eyebrow eyebrow-ko mt-0.5 !text-faint">리서치 어소시에이트</div>
            </div>
            <div class="w-[140px] shrink-0">
              <div class="eyebrow eyebrow-ko">현재 프로젝트</div>
              <div class="text-sm font-semibold mt-0.5">12건 진행 중</div>
            </div>
            <div class="flex-1">
              <div class="flex items-center justify-between mb-1.5">
                <div class="eyebrow eyebrow-ko">달성률</div>
                <div class="text-xs font-semibold tnum text-ink3">48%</div>
              </div>
              <div class="progress info"><span style="width:48%"></span></div>
            </div>
          </li>
        </ul>
      </article>

      {# Recent Activity #}
      <article class="col-span-4 bg-surface rounded-card shadow-card p-6">
        <div class="flex items-center justify-between">
          <div class="eyebrow">Recent Activity</div>
          <button class="text-faint hover:text-ink" type="button" aria-label="새로고침">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
          </button>
        </div>
        <ul class="mt-5 space-y-4">
          <li class="flex gap-3">
            <div class="w-7 h-7 rounded-full bg-emerald-50 text-success flex items-center justify-center shrink-0 mt-0.5">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <div class="min-w-0">
              <div class="text-sm font-semibold leading-snug">후보자 배치가 확정되었습니다</div>
              <div class="text-xs text-faint mt-0.5">프로젝트 클라우드 / CTO 서치 · 2시간 전</div>
            </div>
          </li>
          <li class="flex gap-3">
            <div class="w-7 h-7 rounded-full bg-indigo-50 text-info flex items-center justify-center shrink-0 mt-0.5">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </div>
            <div class="min-w-0">
              <div class="text-sm font-semibold leading-snug">새 후보자가 추가되었습니다</div>
              <div class="text-xs text-faint mt-0.5">글로벌 핀테크 확장 · 5시간 전</div>
            </div>
          </li>
          <li class="flex gap-3">
            <div class="w-7 h-7 rounded-full bg-amber-50 text-warning flex items-center justify-center shrink-0 mt-0.5">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
            </div>
            <div class="min-w-0">
              <div class="text-sm font-semibold leading-snug">고객사 미팅 노트가 업데이트되었습니다</div>
              <div class="text-xs text-faint mt-0.5">삼성전자 자문 프로젝트 · 어제</div>
            </div>
          </li>
          <li class="flex gap-3">
            <div class="w-7 h-7 rounded-full bg-red-50 text-danger flex items-center justify-center shrink-0 mt-0.5">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            </div>
            <div class="min-w-0">
              <div class="text-sm font-semibold leading-snug">프로젝트 마감일이 가까워지고 있습니다</div>
              <div class="text-xs text-faint mt-0.5">재생에너지 헤드 서치 · 2일 전</div>
            </div>
          </li>
        </ul>
      </article>
    </section>
```

노트:
- `w-[180px]`, `w-[140px]` 는 목업 고정 폭. 타이포 인라인값이 아니라 레이아웃 폭이므로 허용
- `.progress.success`, `.progress.info` 는 기존 `input.css` 정의 사용
- `!text-faint` 는 `.eyebrow` CSS 색을 더 연하게 override. 직함을 희미하게 처리하는 목업 스타일 반영

- [ ] **Step 2: 사용자 시각 QA 대기**

보고:
- URL: `http://localhost:8000/dashboard/`
- 기대 화면: 상단 3 cards + 중간 row (Team Performance col-8 / Recent Activity col-4)

- [ ] **Step 3: Commit**

```bash
git add projects/templates/projects/partials/dash_full.html
git commit -m "$(cat <<'EOF'
feat(dashboard): S2 team performance + recent activity (hardcoded)

3명 팀원 progress + 4건 activity 아이템. 목업 동일.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 · S3 — Weekly Schedule + Monthly Calendar

**Files:**
- Modify: `static/css/input.css` (calendar CSS 블록 추가)
- Modify: `projects/templates/projects/partials/dash_full.html` (S2 section 아래 S3 section 추가)

- [ ] **Step 1: `input.css` 에 calendar CSS 추가**

`@layer components` 안 **기존 `.status-dot` 규칙(line 115 근처) 다음** 에 아래 블록 삽입:

```css
  .cal-day {
    aspect-ratio: 1/1;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    justify-content: flex-start;
    padding: 12px 14px;
    color: #0F172A;
    border: 2px solid #EEF2F7;
    background: #FFFFFF;
    transition: background .15s ease;
    position: relative;
  }
  .cal-day:hover { background: #F8FAFC; }
  .cal-day > .tnum {
    font-size: 14px;
    font-weight: 600;
    color: #0F172A;
    line-height: 1;
    letter-spacing: -0.01em;
  }
  .cal-day.muted > .tnum { color: #CBD5E1; font-weight: 500; }
  .cal-day.today > .tnum {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    background: #0F172A;
    color: #fff;
    border-radius: 999px;
    font-size: 12px;
    margin: -5px -6px;
  }
  .cal-event {
    margin-top: 8px;
    font-size: 10px;
    line-height: 1.2;
    padding: 4px 10px;
    border-radius: 999px;
    background: #F1F5F9;
    color: #334155;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
    align-self: flex-start;
  }
  .cal-day.today .cal-event { background: #0F172A; color: #fff; }
  /* Internal-only borders: remove all four outer edges */
  .cal-day:nth-child(-n+7)     { border-top: 0; margin-top: 0 !important; }
  .cal-day:nth-child(7n+1)     { border-left: 0; }
  .cal-day:nth-child(7n)       { border-right: 0; }
  .cal-day:nth-last-child(-n+7){ border-bottom: 0; }
  /* Weekend colors — Sunday red, Saturday blue */
  .cal-day:nth-child(7n+1):not(.today) > .tnum { color: #DC2626; }
  .cal-day:nth-child(7n):not(.today)   > .tnum { color: #2563EB; }
  .cal-day.muted:nth-child(7n+1) > .tnum { color: #FCA5A5; }
  .cal-day.muted:nth-child(7n)   > .tnum { color: #93C5FD; }
```

노트: `.cal-event` 내부의 `font-size: 10px` 는 CSS 클래스 내부라서 "인라인 text-[Xpx] 금지" 규칙 대상 아님. 디자인 시스템 §4.11 블록 그대로.

- [ ] **Step 2: `dash_full.html` 에 S3 section 추가**

Task 2 에서 추가한 S2 section `</section>` 직후에 아래 블록 삽입:

```html
    {# ============ S3: BOTTOM ROW — schedule + calendar ============ #}
    <section class="grid grid-cols-12 gap-6">

      {# Weekly Schedule #}
      <div class="col-span-4">
        <div class="eyebrow mb-4">Weekly Schedule</div>
        <div class="space-y-4">
          <div class="bg-surface rounded-card shadow-card p-5">
            <div class="flex items-start justify-between">
              <div class="eyebrow eyebrow-ko !text-ink3">10월 23일 월요일 · 09:00</div>
              <button class="text-faint hover:text-ink" type="button" aria-label="메뉴">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>
              </button>
            </div>
            <div class="mt-3 text-base font-semibold leading-snug">주간 파이프라인 리뷰</div>
            <div class="text-xs text-muted mt-1">내부 팀 세션 · A 회의실</div>
          </div>

          <div class="bg-surface rounded-card shadow-card p-5">
            <div class="flex items-start justify-between">
              <div class="eyebrow eyebrow-ko !text-info">10월 25일 수요일 · 11:00</div>
              <button class="text-faint hover:text-ink" type="button" aria-label="메뉴">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>
              </button>
            </div>
            <div class="mt-3 text-base font-semibold leading-snug">임원 인터뷰</div>
            <div class="text-xs text-muted mt-1">후보자: 박해준 · Zoom</div>
          </div>

          <div class="bg-surface rounded-card shadow-card p-5">
            <div class="flex items-start justify-between">
              <div class="eyebrow eyebrow-ko !text-warning">10월 27일 금요일 · 14:00</div>
              <button class="text-faint hover:text-ink" type="button" aria-label="메뉴">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>
              </button>
            </div>
            <div class="mt-3 text-base font-semibold leading-snug">고객사 브리핑: SK하이닉스</div>
            <div class="text-xs text-muted mt-1">전략기획 · 본사</div>
          </div>
        </div>
      </div>

      {# Monthly Calendar #}
      <div class="col-span-8">
        <div class="eyebrow mb-4">Monthly Schedule</div>
        <article class="bg-surface rounded-card shadow-card overflow-hidden">

          <div class="grid grid-cols-7 border-b border-hair">
            <div class="eyebrow eyebrow-ko text-center py-3 !text-red-600">일</div>
            <div class="eyebrow eyebrow-ko text-center py-3 !text-ink2">월</div>
            <div class="eyebrow eyebrow-ko text-center py-3 !text-ink2">화</div>
            <div class="eyebrow eyebrow-ko text-center py-3 !text-ink2">수</div>
            <div class="eyebrow eyebrow-ko text-center py-3 !text-ink2">목</div>
            <div class="eyebrow eyebrow-ko text-center py-3 !text-ink2">금</div>
            <div class="eyebrow eyebrow-ko text-center py-3 !text-blue-600">토</div>
          </div>

          <div class="grid grid-cols-7 [&>*]:-ml-0.5 [&>*]:-mt-0.5">
            {# trailing days of previous month #}
            <div class="cal-day muted"><span class="tnum">24</span></div>
            <div class="cal-day muted"><span class="tnum">25</span></div>
            <div class="cal-day muted"><span class="tnum">26</span></div>
            <div class="cal-day muted"><span class="tnum">27</span></div>
            <div class="cal-day muted"><span class="tnum">28</span></div>
            <div class="cal-day muted"><span class="tnum">29</span></div>
            <div class="cal-day muted"><span class="tnum">30</span></div>

            {# Week 1 #}
            <div class="cal-day"><span class="tnum">1</span></div>
            <div class="cal-day"><span class="tnum">2</span></div>
            <div class="cal-day"><span class="tnum">3</span></div>
            <div class="cal-day">
              <span class="tnum">4</span>
              <div class="cal-event">이사회</div>
            </div>
            <div class="cal-day"><span class="tnum">5</span></div>
            <div class="cal-day"><span class="tnum">6</span></div>
            <div class="cal-day"><span class="tnum">7</span></div>

            {# Week 2 #}
            <div class="cal-day"><span class="tnum">8</span></div>
            <div class="cal-day"><span class="tnum">9</span></div>
            <div class="cal-day"><span class="tnum">10</span></div>
            <div class="cal-day"><span class="tnum">11</span></div>
            <div class="cal-day"><span class="tnum">12</span></div>
            <div class="cal-day"><span class="tnum">13</span></div>
            <div class="cal-day"><span class="tnum">14</span></div>

            {# Week 3 #}
            <div class="cal-day"><span class="tnum">15</span></div>
            <div class="cal-day"><span class="tnum">16</span></div>
            <div class="cal-day"><span class="tnum">17</span></div>
            <div class="cal-day"><span class="tnum">18</span></div>
            <div class="cal-day"><span class="tnum">19</span></div>
            <div class="cal-day"><span class="tnum">20</span></div>
            <div class="cal-day"><span class="tnum">21</span></div>

            {# Week 4 #}
            <div class="cal-day"><span class="tnum">22</span></div>
            <div class="cal-day">
              <span class="tnum">23</span>
              <div class="cal-event">주간 리뷰</div>
            </div>
            <div class="cal-day"><span class="tnum">24</span></div>
            <div class="cal-day today">
              <span class="tnum">25</span>
              <div class="cal-event">인터뷰</div>
            </div>
            <div class="cal-day"><span class="tnum">26</span></div>
            <div class="cal-day">
              <span class="tnum">27</span>
              <div class="cal-event">SK하이닉스</div>
            </div>
            <div class="cal-day"><span class="tnum">28</span></div>

            {# Week 5 + leading next month #}
            <div class="cal-day"><span class="tnum">29</span></div>
            <div class="cal-day"><span class="tnum">30</span></div>
            <div class="cal-day"><span class="tnum">31</span></div>
            <div class="cal-day muted"><span class="tnum">1</span></div>
            <div class="cal-day muted"><span class="tnum">2</span></div>
            <div class="cal-day muted"><span class="tnum">3</span></div>
            <div class="cal-day muted"><span class="tnum">4</span></div>
          </div>
        </article>
      </div>
    </section>
```

- [ ] **Step 3: 사용자 시각 QA 대기**

보고:
- URL: `http://localhost:8000/dashboard/`
- 기대 화면: 상단 3 cards + 중간 team/activity + 하단 weekly schedule(col-4) / monthly calendar(col-8 with today=25)

- [ ] **Step 4: Commit**

```bash
git add static/css/input.css projects/templates/projects/partials/dash_full.html
git commit -m "$(cat <<'EOF'
feat(dashboard): S3 weekly schedule + monthly calendar (hardcoded)

주간 3건 + 2023-10 캘린더 (today=25, 4개 이벤트). cal-day CSS
입력.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 · S4 — 정리 (dead code 제거)

**Files:**
- Delete: `projects/templates/projects/partials/dash_actions.html`
- Delete: `projects/templates/projects/partials/dash_admin.html`
- Delete: `projects/templates/projects/partials/dashboard_todo_list.html`
- Delete: `projects/templates/projects/dashboard/index.html`
- Modify: `projects/views.py` (3 뷰 함수 제거)
- Modify: `main/urls.py` (3 라우트 + import 제거)
- Modify: `tests/test_views_dashboard.py`
- Modify: `tests/test_p13_dashboard.py`
- Modify: `tests/accounts/test_rbac.py`

- [ ] **Step 1: `projects/views.py` 에서 3개 뷰 함수 제거**

`projects/views.py` 의 `dashboard_actions` (line 2194-2212), `dashboard_todo_partial` (line 2215-2239), `dashboard_team` (line 2242-2253) 함수 **전체**를 삭제. 세 함수 사이의 빈 줄도 정리.

결과적으로 `dashboard` 함수 바로 뒤에 `# --- P16: Work Continuity ---` 주석(line 2256 근처)이 바로 오도록.

- [ ] **Step 2: `main/urls.py` 정리**

`main/urls.py` line 9-12:

```python
from projects.views import (
    dashboard,
    dashboard_actions,
    dashboard_team,
    dashboard_todo_partial,
    ...
)
```

→ `dashboard_actions`, `dashboard_team`, `dashboard_todo_partial` 세 이름 제거. (파일 구조 실제로 보고 정확히 삭제. import 가 블록이 아니라 여러 줄이거나 다른 순서일 수 있음.)

그리고 `urlpatterns` 에서 line 21-23 의 라우트 3개 삭제:

```python
    path("dashboard/todo/", dashboard_todo_partial, name="dashboard_todo"),
    path("dashboard/actions/", dashboard_actions, name="dashboard_actions"),
    path("dashboard/team/", dashboard_team, name="dashboard_team"),
```

- [ ] **Step 3: 고아 partial·템플릿 삭제**

```bash
rm projects/templates/projects/partials/dash_actions.html
rm projects/templates/projects/partials/dash_admin.html
rm projects/templates/projects/partials/dashboard_todo_list.html
rm projects/templates/projects/dashboard/index.html
rmdir projects/templates/projects/dashboard 2>/dev/null || true
```

- [ ] **Step 4: `tests/accounts/test_rbac.py` — 2개 테스트 제거**

`tests/accounts/test_rbac.py` 에서 아래 2개 메서드 **전체** 삭제:

- `test_consultant_cannot_access_dashboard_team` (line 194 시작)
- `test_consultant_can_access_dashboard_actions` (line 206 시작)

각각 메서드 def 부터 다음 메서드 def (또는 class 끝) 직전까지 블록 삭제. `Read` 로 정확한 범위 확인 후 `Edit` 로 제거.

- [ ] **Step 5: `tests/test_p13_dashboard.py` — 제거 대상 뷰 테스트 삭제**

`tests/test_p13_dashboard.py` 에서 아래 메서드 **전체** 삭제:
- `test_dashboard_actions_partial` (line 359)
- `test_dashboard_team_owner_only` (line 364)

또한 같은 파일에서 `dashboard()` 뷰가 더 이상 제공하지 않는 context (`today_actions`, `overdue_actions`, `upcoming_actions`, `pending_approvals`, `is_owner`, `has_projects`, `has_clients`) 를 검증하는 테스트가 있으면 **그 테스트도 삭제**. `Read` 로 전체 스캔 후 해당 context 키를 assert 하는 test 메서드를 제거.

services 함수 자체를 테스트하는 부분(`get_today_actions` 등을 직접 호출해서 반환값 검증) 은 **유지** — 서비스는 다른 코드에서 계속 사용.

- [ ] **Step 6: `tests/test_views_dashboard.py` — `dashboard_todo` 참조 테스트 삭제**

line 114 의 `reverse("dashboard_todo")` 를 포함한 테스트 메서드 **전체** 삭제. 동일 파일에 제거된 뷰 (`dashboard_actions`, `dashboard_team`, `dashboard_todo_partial`) 를 호출하는 테스트가 더 있으면 같이 삭제. 파일의 다른 테스트 (`dashboard` 자체 GET 검증) 는 context 검증이 없다면 유지.

- [ ] **Step 7: 전체 테스트 실행**

```bash
uv run pytest -x --tb=short 2>&1 | tail -50
```

Expected: 모든 테스트 PASS. 실패 시 실패 원인을 읽고 — 삭제된 뷰/URL 을 참조하는 테스트가 남아있으면 해당 테스트 삭제하고 재실행. 어떤 dashboard 외 기능 테스트가 실패하면 즉시 보고하고 대응.

- [ ] **Step 8: ruff 실행**

```bash
uv run ruff check projects/views.py main/urls.py tests/
uv run ruff format projects/views.py main/urls.py tests/
```

Expected: no errors.

- [ ] **Step 9: 사용자 시각 QA 대기**

보고:
- URL: `http://localhost:8000/dashboard/` — 변경 없음 (S1-S3 그대로)
- 제거된 URL: `/dashboard/todo/`, `/dashboard/actions/`, `/dashboard/team/` 접근 시 404 기대
- pytest 결과 요약 (PASS 수, 삭제된 테스트 수)

- [ ] **Step 10: Commit**

```bash
git add projects/views.py main/urls.py projects/templates/projects/ tests/
git commit -m "$(cat <<'EOF'
refactor(dashboard): remove legacy HTMX partials + tests

dashboard_actions / dashboard_todo_partial / dashboard_team 뷰·URL·
partial·테스트 전부 제거. Phase 1 목업 레이아웃과 충돌하는
잔존물 정리. services/dashboard.py는 kanban·voice에서 계속
사용되므로 유지.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

스펙 커버리지 체크 완료:
- ✅ 사이드바·상단바 유지 — base.html 미변경
- ✅ 하드코딩 목업 값 — Task 1-3 에서 스펙 "하드코딩 데이터 상수" 섹션의 값 그대로
- ✅ Tailwind 기본 font-size 토큰만 — 인라인 `text-[Xpx]` 없음 (w-[180px]/w-[140px]/max-w-[1280px] 는 레이아웃 폭)
- ✅ 인라인 `style=` 는 progress `width` 1 용도만 — Task 1 다크 progress, Task 2 3개 team progress, Task 1 76% 다크 progress
- ✅ 컬러 override 는 `!text-*` 수정자 — `!text-muted`/`!text-ink3`/`!text-info`/`!text-warning`/`!text-faint`/`!text-red-600`/`!text-blue-600`/`!text-ink2`
- ✅ 카드는 `bg-surface rounded-card shadow-card p-6` (weekly schedule만 p-5 — 디자인 시스템 §4.3 변형 허용)
- ✅ `.progress.dark` (Task 1) · `.cal-day`·`.cal-event` (Task 3) CSS 추가
- ✅ `dashboard()` 뷰 context 최소화 (Task 1 Step 2)
- ✅ S4 에서 뷰 3개 · URL 3개 · partial 4개 · 테스트 메서드 4+개 제거
- ✅ `action_item_card.html` 보존 (application_actions_list.html 의존성)
- ✅ `services/dashboard.py` 보존 (kanban·voice 의존성)

Placeholder / 구체성 체크:
- ✅ TBD/TODO 0건
- ✅ 모든 파일 경로 절대 지정
- ✅ 모든 커밋 메시지 완전 기재
- ✅ 모든 HTML 블록 완전 기재 (생략 없음)

Phase 2 (실데이터 연결) 는 스펙 "범위 외" 섹션에 명시된 대로 이 계획에서 다루지 않음.
