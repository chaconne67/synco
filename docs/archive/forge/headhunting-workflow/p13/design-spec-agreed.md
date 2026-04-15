# P13: Dashboard (확정 설계서)

> **Phase:** 13
> **선행조건:** P01 (모델 기반), P03 (프로젝트 CRUD), P06 (컨택), P09 (면접/오퍼), P11 (승인 큐 + context processor + ProjectApproval SET_NULL)
> **산출물:** 대시보드 메인 화면 + 긴급도 자동 산정 + 관리자 팀 현황 + 사이드바 1순위 메뉴

---

## 목표

로그인 후 첫 화면을 대시보드로 변경한다. 컨설턴트에게 오늘의 액션, 이번 주 일정,
파이프라인 현황, 최근 활동을 제공하고, 관리자(OWNER)에게는 승인 요청 큐 요약과 팀 KPI를 추가 표시한다.

---

## URL 설계

| URL | Method | View | 설명 | 정의 위치 |
|-----|--------|------|------|----------|
| `/` | GET | `dashboard` | 대시보드 (로그인 후 기본 진입점) | `main/urls.py` |
| `/dashboard/` | GET | `dashboard` | 대시보드 (명시적 URL) | `projects/urls.py` |
| `/dashboard/actions/` | GET | `dashboard_actions` | 오늘의 액션 (HTMX partial, 새로고침) | `projects/urls.py` |
| `/dashboard/team/` | GET | `dashboard_team` | 팀 현황 (OWNER 전용, HTMX partial) | `projects/urls.py` |

**[D-R1-01 반영]** `/` 매핑은 `main/urls.py`에서 변경. `projects/urls.py`에는 `/dashboard/` 이하만 추가.

---

## 진입점 변경

**[D-R1-02 반영]** 기존 로그인 후 리다이렉트 대상을 대시보드로 변경:

1. `main/urls.py` — 루트 URL(`/`)을 `projects.views.dashboard`로 매핑 (기존 `redirect("/candidates/")` 대체)
2. `accounts/views.py` — `home()` 뷰의 `redirect("candidate_list")` → `redirect("dashboard")` 변경
3. `settings.py` — `LOGIN_REDIRECT_URL = "/"` 설정 (방어적 조치)

현재 인증 플로우:
- `login_page()` → 인증 시 `redirect("home")` → `home()` → `redirect("dashboard")`
- `kakao_callback()` → `redirect("home")` → `home()` → `redirect("dashboard")`

---

## 모델 변경

### 신규 필드 1개 추가 (P13 선행 마이그레이션)

**[D-R1-04 반영]** Contact 모델에 재컨택 예정일 필드 추가:

```python
# projects/models.py — Contact 클래스
next_contact_date = models.DateField(null=True, blank=True)  # 재컨택 예정일
```

기존 모델 조합으로 나머지 데이터 집계:
- `Project` — 상태별 카운트, 경과일 (`days_elapsed` 프로퍼티)
- `Contact` — 재컨택 예정(`next_contact_date`), 잠금 만료 임박(`locked_until`)
- `Submission` — 서류 검토 대기 (status="제출" + `submitted_at` 기준)
- `Interview` — 면접 일정 (`scheduled_at`)
- `Offer` — 오퍼 상태 (`status`, `created_at`)
- `ProjectApproval` — 승인 대기 (OWNER용)

---

## 관리자 판별 기준

**[D-R1-03 반영]** 관리자는 `Membership.Role.OWNER`로 판별합니다. `user.is_staff`를 사용하지 않습니다.

```python
def _is_owner(request) -> bool:
    try:
        return request.user.membership.role == "owner"
    except Exception:
        return False
```

이 기준은 승인 큐 표시, 팀 현황, 승인 뱃지 전체에 동일 적용됩니다.

---

## 서비스 계층

**[D-R1-07 반영]** 모든 서비스 함수에 `org: Organization` 파라미터 포함.

`projects/services/dashboard.py`:

```python
from accounts.models import Organization, User

def get_today_actions(user: User, org: Organization) -> list[dict]:
    """긴급도 자동 산정 후 오늘의 액션 목록 반환."""

def get_weekly_schedule(user: User, org: Organization) -> list[dict]:
    """이번 주 일정 (면접, 재컨택, 기한) 반환."""

def get_pipeline_summary(user: User, org: Organization) -> dict:
    """내 프로젝트 상태별 카운트 + 이번 달 클로즈 건수."""

def get_recent_activities(user: User, org: Organization, limit: int = 10) -> list[dict]:
    """최근 활동 로그 반환."""

def get_team_summary(admin_user: User, org: Organization) -> dict:
    """팀 전체 현황 + KPI (OWNER 전용)."""

def get_pending_approvals(org: Organization) -> QuerySet:
    """미처리 승인 요청 목록 (OWNER 전용)."""
```

---

## 긴급도 자동 산정 로직

**[D-R1-04 반영]** 현재 모델 필드 기준으로 재정의:

| 우선순위 | 조건 | 사용 필드 | 표시 |
|---------|------|----------|------|
| **1 (빨강)** | 재컨택 예정일이 오늘이거나 과거 | `Contact.next_contact_date` | 재컨택 (오늘/D+N 지연) |
| **2 (빨강)** | 면접 일정이 오늘~내일 | `Interview.scheduled_at` | 면접 임박 |
| **3 (빨강)** | 서류 제출 후 검토 대기 2일 이상 | `Submission.status="제출"` + `submitted_at` | 서류 검토 필요 |
| **4 (빨강)** | 잠금 만료 1일 이내 | `Contact.locked_until` | 컨택 잠금 만료 임박 |
| **5 (노랑)** | 면접 일정 이번 주 | `Interview.scheduled_at` | 면접 예정 |
| **6 (노랑)** | 재컨택 예정 이번 주 | `Contact.next_contact_date` | 재컨택 예정 |
| **7 (노랑)** | 오퍼 회신 대기 7일 이상 | `Offer.status="협상중"` + `created_at` | 오퍼 회신 대기 |
| **8 (초록)** | 신규 프로젝트 (D+3 이내) | `Project.status="new"` + `created_at` | 서칭 시작 필요 |
| **9 (초록)** | 기타 진행 중 | `Project.status` | 정상 진행 |

구현: `projects/services/urgency.py` — 각 프로젝트의 관련 Contact, Interview, Submission, Offer를 조회하여 가장 높은 긴급도 액션 1개를 결정.

---

## 컨설턴트 대시보드 UI

```
+-- 대시보드 -- 전병권님 ------------------- 2026년 4월 7일 --+
|                                                            |
+-- 오늘의 액션 -----------------------------------------------+
|  [빨강] 홍길동 재컨택 (Rayence 품질기획)          예정: 오늘  |
|  [빨강] 이순신 제출서류 검토 필요                 대기: 2일   |
|  [빨강] LG전자 경영기획 -- 서칭 시작               신규: D+2  |
+-- 이번 주 ---------------------------------------------------+
|  [노랑] 삼성SDI 홍길동 2차면접                   04/12 (화)  |
|  [노랑] 김영희 재컨택 (Rayence 품질기획)         04/09 예정   |
|  [노랑] SK하이닉스 -- 오퍼 회신 대기               D+41       |
+-- 내 파이프라인 ---------------------------------------------+
|  신규(1) → 서칭(2) → 추천(1) → 면접(1) → 오퍼(1)             |
|  진행 중: 6건  |  이번 달 클로즈: 1건                          |
+-- 최근 활동 -------------------------------------------------+
|  10분 전  홍길동 컨택 기록 추가 (Rayence)                     |
|  2시간 전  LG전자 경영기획 프로젝트 등록                       |
|  어제     이순신 제출서류 AI 초안 생성                         |
+--------------------------------------------------------------+
```

---

## 관리자(OWNER) 추가 섹션

**[D-R1-05 반영]** 인라인 액션 버튼 대신 승인 큐 페이지 링크로 이동.

```
+-- 승인 요청 (2건) -------------------------------------------+
|  전병권 → Rayence 품질기획팀장                                |
|  박준혁 → LG전자 경영기획                                    |
|  [승인 큐 보기 →]                                            |
+-- 팀 전체 현황 ----------------------------------------------+
|  +----------+----+----+----+----+------+                     |
|  | 컨설턴트  |진행 |컨택 |추천 |면접 |클로즈|                     |
|  +----------+----+----+----+----+------+                     |
|  | 전병권    | 3  | 12 | 4  | 2  | 1   |                     |
|  | 김소연    | 2  | 8  | 3  | 1  | 0   |                     |
|  | 박준혁    | 3  | 6  | 5  | 2  | 1   |                     |
|  +----------+----+----+----+----+------+                     |
|  팀 KPI: 컨택→추천 32% | 추천→면접 58% | 평균 클로즈 38일      |
+--------------------------------------------------------------+
```

**승인 큐 링크:** `hx-get="/projects/approvals/"` + `hx-target="#main-content"` + `hx-push-url="true"`

---

## 사이드바 변경

**[D-R1-06 반영]** HTMX target을 `#main-content`로 수정.

사이드바 최상단에 대시보드 메뉴 추가:

```html
<a href="/"
   hx-get="/" hx-target="#main-content" hx-push-url="true"
   data-nav="dashboard"
   class="sidebar-tab ...">
  대시보드
</a>
```

순서: 대시보드 > 후보자 > 프로젝트 > 고객사 > 설정

**승인 뱃지:** P11에서 구현된 context processor (`pending_approval_count`)를 재사용하여 OWNER에게 승인 건수 표시.

**하단 네비 (모바일):** 동일 패턴으로 대시보드 메뉴 추가. 기존 4개 → 5개.

**사이드바 JS 업데이트:** `updateSidebar()` 함수에 `dashboard` 키 추가.

```javascript
var active = (key === 'dashboard' && path === '/') ||
             (key === 'candidates' && path.startsWith('/candidates')) ||
             // ...
```

---

## 템플릿 구조

| 템플릿 | 설명 |
|--------|------|
| `projects/templates/projects/dashboard.html` | 전체 대시보드 레이아웃 |
| `projects/templates/projects/partials/dash_actions.html` | 오늘의 액션 섹션 |
| `projects/templates/projects/partials/dash_schedule.html` | 이번 주 일정 |
| `projects/templates/projects/partials/dash_pipeline.html` | 파이프라인 미니 차트 |
| `projects/templates/projects/partials/dash_activity.html` | 최근 활동 |
| `projects/templates/projects/partials/dash_admin.html` | OWNER 섹션 (승인 큐 요약 + 팀 현황) |

모든 템플릿은 `{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}` 동적 extends 패턴 사용.

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| 진입점 변경 | 로그인 후 `/` 접근 시 대시보드 표시 |
| home() 리다이렉트 | `home` URL이 대시보드로 이동 |
| 오늘의 액션 | next_contact_date/면접 임박/서류 대기 건 표시 확인 |
| 긴급도 정렬 | 빨강 > 노랑 > 초록 순서 |
| 파이프라인 | 내 프로젝트 상태별 카운트 정확 |
| 최근 활동 | 컨택/등록/서류 생성 등 최신순 표시 |
| OWNER 승인 큐 | OWNER 사용자에게만 승인 요청 섹션 노출 |
| 승인 큐 링크 | `/projects/approvals/`로 이동 |
| 팀 현황 | 컨설턴트별 진행/컨택/추천/면접/클로즈 카운트 |
| 팀 KPI | 전환율 계산 (컨택→추천, 추천→면접) |
| 사이드바 | 대시보드 메뉴 1순위, 승인 뱃지 (OWNER만) |
| 하단 네비 | 대시보드 메뉴 추가 |
| 조직 격리 | 모든 쿼리에 organization=org 필터 확인 |
| 비로그인 | 미인증 시 로그인 페이지로 리다이렉트 |

---

## 산출물

| 파일 | 작업 | 설명 |
|------|------|------|
| `projects/models.py` | 수정 | Contact에 `next_contact_date` 필드 추가 |
| `projects/migrations/XXXX_*.py` | 생성 | next_contact_date 마이그레이션 |
| `projects/services/dashboard.py` | 생성 | 대시보드 데이터 집계 서비스 |
| `projects/services/urgency.py` | 생성 | 긴급도 자동 산정 로직 |
| `projects/views.py` | 수정 | dashboard, dashboard_actions, dashboard_team 뷰 |
| `projects/urls.py` | 수정 | `/dashboard/`, `/dashboard/actions/`, `/dashboard/team/` URL |
| `main/urls.py` | 수정 | 루트 URL(`/`)을 대시보드로 변경 |
| `main/settings.py` | 수정 | `LOGIN_REDIRECT_URL = "/"` |
| `accounts/views.py` | 수정 | `home()` redirect 대상 변경 |
| `projects/templates/projects/dashboard.html` | 생성 | 대시보드 메인 |
| `projects/templates/projects/partials/dash_actions.html` | 생성 | 오늘의 액션 |
| `projects/templates/projects/partials/dash_schedule.html` | 생성 | 이번 주 일정 |
| `projects/templates/projects/partials/dash_pipeline.html` | 생성 | 파이프라인 |
| `projects/templates/projects/partials/dash_activity.html` | 생성 | 최근 활동 |
| `projects/templates/projects/partials/dash_admin.html` | 생성 | OWNER 섹션 |
| `templates/common/nav_sidebar.html` | 수정 | 대시보드 메뉴 추가 + 승인 뱃지 |
| `templates/common/nav_bottom.html` | 수정 | 대시보드 메뉴 추가 |
| `tests/test_p13_dashboard.py` | 생성 | 대시보드 테스트 |

## 프로젝트 컨텍스트 (확정된 패턴)

1. **Organization 격리:** 모든 queryset에 `organization=org` 필터. `_get_org(request)` 헬퍼 사용
2. **@login_required:** 모든 view에 적용
3. **동적 extends:** `{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}`
4. **HTMX target:** `hx-target="#main-content"` (전체 네비), `hx-target="#tab-content"` (탭 전환)
5. **UI 텍스트:** 한국어 존대말
6. **관리자 판별:** `request.user.membership.role == "owner"` (NOT `user.is_staff`)
7. **승인 큐:** `/projects/approvals/` (P11 구현)
8. **승인 뱃지:** P11 context processor (`pending_approval_count`) 재사용
9. **조직 격리 체이닝:** Project(organization=org) → 하위 모델

<!-- forge:p13:설계담금질:complete:2026-04-08T23:59:00+09:00 -->
