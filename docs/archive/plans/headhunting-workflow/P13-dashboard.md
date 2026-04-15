# P13: Dashboard

> **Phase:** 13
> **선행조건:** P01 (모델 기반), P03 (프로젝트 CRUD), P06 (컨택), P09 (면접/오퍼), P11 (승인 큐)
> **산출물:** 대시보드 메인 화면 + 긴급도 자동 산정 + 관리자 팀 현황 + 사이드바 1순위 메뉴

---

## 목표

로그인 후 첫 화면을 대시보드로 변경한다. 컨설턴트에게 오늘의 액션, 이번 주 일정,
파이프라인 현황, 최근 활동을 제공하고, 관리자에게는 승인 요청 큐와 팀 KPI를 추가 표시한다.

---

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/` | GET | `dashboard` | 대시보드 (로그인 후 기본 진입점) |
| `/dashboard/` | GET | `dashboard` | 대시보드 (명시적 URL) |
| `/dashboard/actions/` | GET | `dashboard_actions` | 오늘의 액션 (HTMX partial, 새로고침) |
| `/dashboard/team/` | GET | `dashboard_team` | 팀 현황 (관리자 전용, HTMX partial) |

---

## 진입점 변경

기존 로그인 후 리다이렉트 대상을 대시보드로 변경:

- `accounts/views.py` — `LOGIN_REDIRECT_URL = "/"` 또는 login view의 `next` 기본값 변경
- `settings.py` — `LOGIN_REDIRECT_URL = "/"`
- 루트 URL(`/`)을 `dashboard` 뷰에 매핑

---

## 모델 추가

신규 모델 없음. 기존 모델 조합으로 데이터 집계:
- `Project` — 상태별 카운트, 경과일
- `Contact` — 재컨택 예정, 잠금 만료 임박
- `Submission` — 서류 검토 대기
- `Interview` — 면접 일정
- `ProjectApproval` — 승인 대기 (관리자)

---

## 서비스 계층

`projects/services/dashboard.py`:

```python
def get_today_actions(user: User) -> list[dict]:
    """긴급도 자동 산정 후 오늘의 액션 목록 반환."""

def get_weekly_schedule(user: User) -> list[dict]:
    """이번 주 일정 (면접, 재컨택, 기한) 반환."""

def get_pipeline_summary(user: User) -> dict:
    """내 프로젝트 상태별 카운트 + 이번 달 클로즈 건수."""

def get_recent_activities(user: User, limit: int = 10) -> list[dict]:
    """최근 활동 로그 반환."""

def get_team_summary(admin_user: User) -> dict:
    """팀 전체 현황 + KPI (관리자 전용)."""

def get_pending_approvals() -> QuerySet:
    """미처리 승인 요청 목록 (관리자 전용)."""
```

---

## 긴급도 자동 산정 로직

| 우선순위 | 조건 | 표시 |
|---------|------|------|
| **1 (빨강)** | 재컨택 예정일이 오늘이거나 과거 | 📞 재컨택 (오늘/D+N 지연) |
| **2 (빨강)** | 면접 일정이 오늘~내일 | 🗓️ 면접 임박 |
| **3 (빨강)** | 서류 검토 대기 2일 이상 | 📄 서류 검토 필요 |
| **4 (빨강)** | 잠금 만료 1일 이내 | ⏳ 컨택 잠금 만료 임박 |
| **5 (노랑)** | 면접 일정 이번 주 | 🗓️ 면접 예정 |
| **6 (노랑)** | 재컨택 예정 이번 주 | 📞 재컨택 예정 |
| **7 (노랑)** | 오퍼 회신 대기 7일 이상 | ⏳ 오퍼 회신 대기 |
| **8 (초록)** | 신규 프로젝트 (D+3 이내) | 📋 서칭 시작 필요 |
| **9 (초록)** | 기타 진행 중 | 정상 진행 |

구현: `projects/services/urgency.py` — 각 프로젝트의 관련 Contact, Interview, Submission을 조회하여 가장 높은 긴급도 액션 1개를 결정.

---

## 컨설턴트 대시보드 UI

```
┌─ 대시보드 ─ 전병권님 ──────────────── 2026년 4월 7일 ──┐
│                                                        │
├─ 오늘의 액션 ──────────────────────────────────────────┤
│  🔴 📞 홍길동 재컨택 (Rayence 품질기획)       예정: 오늘  │
│  🔴 📄 이순신 제출서류 검토 필요              대기: 2일   │
│  🔴 📋 LG전자 경영기획 — 서칭 시작            신규: D+2  │
├─ 이번 주 ──────────────────────────────────────────────┤
│  🟡 🗓️ 삼성SDI 홍길동 2차면접               04/12 (화)  │
│  🟡 📞 김영희 재컨택 (Rayence 품질기획)      04/09 예정   │
│  🟡 ⏳ SK하이닉스 — 오퍼 회신 대기            D+41       │
├─ 내 파이프라인 ────────────────────────────────────────┤
│  신규(1) → 서칭(2) → 추천(1) → 면접(1) → 오퍼(1)       │
│  ■        ■■       ■        ■        ■                │
│  진행 중: 6건  |  이번 달 클로즈: 1건                    │
├─ 최근 활동 ────────────────────────────────────────────┤
│  10분 전  홍길동 컨택 기록 추가 (Rayence)                │
│  2시간 전  LG전자 경영기획 프로젝트 등록                  │
│  어제     이순신 제출서류 AI 초안 생성                    │
└────────────────────────────────────────────────────────┘
```

---

## 관리자 추가 섹션

```
├─ 승인 요청 (2건) ──────────────────────────────────────┤
│  전병권 → Rayence 품질기획팀장     [승인] [합류] [반려]   │
│  박준혁 → LG전자 경영기획          [승인] [합류] [반려]   │
├─ 팀 전체 현황 ─────────────────────────────────────────┤
│  ┌──────────┬────┬────┬────┬────┬────┐                │
│  │ 컨설턴트  │진행 │컨택 │추천 │면접 │클로즈│                │
│  ├──────────┼────┼────┼────┼────┼────┤                │
│  │ 전병권    │ 3  │ 12 │ 4  │ 2  │ 1  │                │
│  │ 김소연    │ 2  │ 8  │ 3  │ 1  │ 0  │                │
│  │ 박준혁    │ 3  │ 6  │ 5  │ 2  │ 1  │                │
│  └──────────┴────┴────┴────┴────┴────┘                │
│  팀 KPI: 컨택→추천 32% | 추천→면접 58% | 평균 클로즈 38일│
└────────────────────────────────────────────────────────┘
```

관리자 판별: `user.is_staff` 또는 별도 permission group (`headhunting_admin`).

---

## 사이드바 변경

사이드바 최상단에 대시보드 메뉴 추가:

```
│  📊  대시보드                │  ← 1순위, active 표시
│  📋  프로젝트               │
│  🏢  고객사                 │
│  👤  후보자 DB              │
│  📰  뉴스피드              │
```

`hx-get="/"` + `hx-target="main"` + `hx-push-url="true"`.
미처리 승인 건수 뱃지: 관리자인 경우 사이드바에 `(N)` 표시.

---

## 템플릿 구조

| 템플릿 | 설명 |
|--------|------|
| `projects/templates/projects/dashboard.html` | 전체 대시보드 레이아웃 |
| `projects/templates/projects/partials/dash_actions.html` | 오늘의 액션 섹션 |
| `projects/templates/projects/partials/dash_schedule.html` | 이번 주 일정 |
| `projects/templates/projects/partials/dash_pipeline.html` | 파이프라인 미니 차트 |
| `projects/templates/projects/partials/dash_activity.html` | 최근 활동 |
| `projects/templates/projects/partials/dash_admin.html` | 관리자 섹션 (승인 큐 + 팀 현황) |

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| 진입점 변경 | 로그인 후 `/` 접근 시 대시보드 표시 |
| 오늘의 액션 | 재컨택 예정일/면접 임박/서류 대기 건 표시 확인 |
| 긴급도 정렬 | 빨강 > 노랑 > 초록 순서 |
| 파이프라인 | 내 프로젝트 상태별 카운트 정확 |
| 최근 활동 | 컨택/등록/서류 생성 등 최신순 표시 |
| 관리자 승인 큐 | staff 사용자에게만 승인 요청 섹션 노출 |
| 팀 현황 | 컨설턴트별 진행/컨택/추천/면접/클로즈 카운트 |
| 팀 KPI | 전환율 계산 (컨택→추천, 추천→면접) |
| 사이드바 | 대시보드 메뉴 1순위, 승인 뱃지 |
| 비로그인 | 미인증 시 로그인 페이지로 리다이렉트 |

---

## 산출물

- `projects/views.py` — dashboard, dashboard_actions, dashboard_team 뷰
- `projects/urls.py` — 대시보드 URL + 루트 URL 매핑
- `projects/services/dashboard.py` — 대시보드 데이터 집계 서비스
- `projects/services/urgency.py` — 긴급도 자동 산정 로직
- `projects/templates/projects/dashboard.html` — 대시보드 메인
- `projects/templates/projects/partials/dash_*.html` — 섹션별 partial (5개)
- `accounts/` — LOGIN_REDIRECT_URL 변경
- 사이드바 템플릿 수정 (대시보드 메뉴 추가 + 승인 뱃지)
- 테스트 파일
