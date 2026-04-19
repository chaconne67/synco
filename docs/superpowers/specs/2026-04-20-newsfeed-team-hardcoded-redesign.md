# Newsfeed · Team 하드코딩 리디자인

## 목적
뉴스피드와 팀 메뉴 UI를 `assets/ui-sample/newsfeed.html`·`team.html` 목업 기준으로 교체. 디자인 시스템(`docs/design-system.md`) 준수. **모든 카드 콘텐츠 하드코딩** — DB 바인딩 없음.

## 적용 범위
1. `/news/` — 뉴스피드 전체 레이아웃 교체
2. `/team/` — 신규 URL, 팀 페이지 하드코딩
3. 사이드바 Team 링크 타깃을 `/org/` → `/team/`로 변경, owner-only 조건 제거 (전체 멤버가 조회)

## 공통 구현 원칙
- 각 템플릿은 `{% extends "common/base.html" %}` — 기존 사이드바/탑바 재사용
- 목업의 `<aside>` · `<header>` 부분은 버림. `content` 블록에 메인 영역만 하드코딩
- 목업 커스텀 CSS(`.cat`, `.art-tag`, `.hero-tile`, `.pulse-item`, `.badge`, `.stat`, `.kpi`, `.meta-tag` 등)는 `extra_head` 블록에 인라인 `<style>`로 포함
- 컬러·간격·폰트는 디자인 시스템 토큰만 사용 (임의 hex 금지)

## 뉴스피드 (`/news/`)
- 파일: `projects/templates/projects/news_feed.html` 전체 교체
- 레이아웃:
  - 페이지 헤더(eyebrow + H2 + 부제 + 우측 버튼 2개)
  - 카테고리 칩 바 (전체/인사/채용/업계동향/경제·실업) — 정적
  - 12-col 그리드: 좌 col-span-8 (Featured 1개 + 2-col 10개) / 우 col-span-4 (Industry Pulse 다크 KPI + 인기태그 + 주요이슈 + 저장한 기사)
- 뷰(`views_news.news_feed`)는 그대로. context는 하드코딩이므로 미사용 (HTMX 필터 등은 손대지 않음, 칩은 정적 `<button>`)

## 팀 (`/team/`)
- URL: `main/urls.py`에 `path("team/", team_view, name="team")` 추가
- 뷰: `accounts/views_team.py`에 `@login_required def team_view(request):` → `render(request, "accounts/team.html")`
- 템플릿: `accounts/templates/accounts/team.html`
- 레이아웃:
  - 페이지 헤더(eyebrow + H2 + 부제 "6명의 컨설턴트…" + 우측 버튼 2개)
  - 4-KPI 행 (팀 구성원 6 / 누적 후보자 5,989 / 거래 고객사 57 / 성사 7)
  - 6개 팀 카드 그리드 (col-span-4 × 6): 정호열·김현정·박정일·박지영·전병권·임성민
- **아바타는 스켈레톤 처리** — candidate_card_v2 패턴:
  ```html
  <div class="shrink-0 w-16 h-16 rounded-full bg-line flex items-center justify-center">
    <svg class="w-8 h-8 text-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
            d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
    </svg>
  </div>
  ```
  - 이니셜·그라데이션·status-dot 전부 제거
  - 이름·뱃지·실적·Top Clients는 하드코딩 유지

## 사이드바 업데이트
`templates/common/nav_sidebar.html`:
- Team 링크 `href` / `hx-get`: `/org/` → `/team/`
- `{% if membership and membership.role == 'owner' %}` 조건 제거 (팀 페이지는 전체 멤버 조회 가능)
- `data-nav` 값 `org` → `team`, 스크립트의 매칭 로직도 동기화

## 수용 기준
- [ ] `/news/` 접속 시 목업 레이아웃(Featured + 10 카드 + 우측 4 위젯) 렌더
- [ ] `/team/` 접속 시 KPI 4행 + 6 카드, 아바타 자리는 회색 원형 + 퍼슨 아이콘
- [ ] 사이드바 Team 클릭 시 `/team/`로 이동, active 상태 표시
- [ ] 디자인 시스템 토큰만 사용 (임의 hex 0개)
- [ ] 기존 `/news/` 기능(소스관리 버튼, HTMX 필터)은 무력화되어도 무방 (하드코딩 스프린트)
