# Dashboard Phase 2a — 실데이터 연결 (단순 카드)

**작성일:** 2026-04-20
**선행:** Phase 1 완료 (`docs/superpowers/specs/2026-04-20-dashboard-mockup-layout-design.md`)
**후속:** Phase 2b — S1-2 Revenue, S2-2 Recent Activity (별도 스펙)

## 목표

Phase 1 에서 완성된 대시보드 하드코딩 목업(`projects/templates/projects/partials/dash_full.html`)의 카드 4종(S1-1, S1-3, S2-1, S3 좌/우)에 실데이터를 연결한다. 새 모델·마이그레이션 없이 기존 Project/Application/ActionItem/Interview/Membership 만으로 집계.

## 스코프

### 포함 (Phase 2a)

- **S1-1 Monthly Success** — 이번 달 성공 프로젝트 집계
- **S1-3 Project Status** — 프로젝트 단계별 개수
- **S2-1 Team Performance** — 조직 멤버 성과 리스트
- **S3 Weekly Schedule** — 이번 주 일정 카드
- **S3 Monthly Calendar** — 이번 달 캘린더 이벤트

### 제외 (Phase 2b 로 이관)

- **S1-2 Estimated Revenue** — `expected_fee` 집계 + "목표 달성률" 정의 필요
- **S2-2 Recent Activity** — 이벤트 타입 분류·문구 템플릿 설계 필요

Phase 2b 카드는 하드코딩 상태로 유지하고 2a 에서는 건드리지 않는다.

## 아키텍처

### 뷰

`projects/views.py:dashboard()` 를 수정하여 서비스에서 컨텍스트를 받아 템플릿에 전달한다.

```
@login_required
@membership_required
def dashboard(request):
    ctx = get_dashboard_context(request.org, request.user, request.membership)
    if getattr(request, "htmx", None):
        return render(request, "projects/partials/dash_full.html", ctx)
    return render(request, "projects/dashboard.html", ctx)
```

구현 시 `request.org` / `request.membership` 실제 attribute 이름은 `@membership_required` 데코레이터 확인 후 매핑.

### 서비스 레이어

`projects/services/dashboard.py` 기존 파일에 추가:

- **공개 API**: `get_dashboard_context(org, user, membership) -> dict`
- **Private helpers** (같은 파일, 언더스코어 prefix):
  - `_scope_projects(org, user, scope_owner)` — 권한 스코프 공통 쿼리셋
  - `_monthly_success(org, user, scope_owner)` — S1-1
  - `_project_status_counts(org, user, scope_owner)` — S1-3
  - `_team_performance(org)` — S2-1 (스코프 무관, 항상 전체)
  - `_weekly_schedule(org, user, scope_owner)` — S3 좌
  - `_monthly_calendar(org, user, scope_owner)` — S3 우

### 권한 스코프 규칙

`Membership.role` 기준:
- **owner** → 조직 전체 프로젝트·이벤트 집계
- **consultant** → 본인이 `Project.assigned_consultants` M2M 에 속한 프로젝트만 집계. ActionItem/Interview 는 해당 프로젝트 체인으로 필터.
- **viewer** → 현재 Phase 2a 에서는 consultant 와 동일 취급(본인 담당만). Viewer 가 헤드헌팅 업무를 하지 않으므로 실질적으로 빈 대시보드.

S2-1 Team Performance 만 스코프 무관하게 owner+consultant 전체 표시 (동료 서로 보기 용도). Viewer 는 목록에서 제외.

## 카드별 집계 규칙

### S1-1 Monthly Success

목업 표시 3개 값의 의미:

- **큰 숫자(목업: 24)** = 이번 달 성공 건수
  - 쿼리: `status=CLOSED AND result="success" AND closed_at >= 이번달 1일 00:00` 의 개수
- **진행 중(목업: 12)** = 살아있는 프로젝트 총 개수 (스코프 내)
  - 쿼리: `status=OPEN` 의 개수
- **성공률(목업: 82%)** = 이번 달 종료 건 중 성공 비율
  - `이번 달 성공 / (이번 달 성공 + 이번 달 실패)`
  - 분모 0 → 템플릿에 "—" 표시

### S1-3 Project Status

목업 3줄 (누적, 월 필터 없음):

- **진행(success dot)** = `status=OPEN AND phase=SEARCHING`
- **심사(warning dot)** = `status=OPEN AND phase=SCREENING`
- **완료(info dot)** = `status=CLOSED` (success/fail 합산)

### S2-1 Team Performance

조직의 Membership(role in [owner, consultant]) 전체를 한 줄씩.

각 멤버 줄에 표시:
- **아바타** — 회색 원 div (추후 photo 필드로 교체 예정). Phase 1 의 gradient 스타일 삭제.
- **이름** — 한글명. 저장 관행 확인 후 `last_name + first_name` 조합 또는 `get_full_name()` / `username` fallback.
- **역할 라벨** — `Membership.role` 한글 변환:
  - `owner` → "대표"
  - `consultant` → "컨설턴트"
- **현재 프로젝트** — 이 멤버가 `assigned_consultants` 로 속한 `status=OPEN` 프로젝트 개수. 텍스트: "N건 진행 중".
- **성공률 + progress bar** — 누적 성공률 = `본인 담당 CLOSED+success / 본인 담당 CLOSED`. 분모 0 → "—" + 막대 width 0%.
  - 막대 색: `≥80%` success / `≥60%` default / 이하 info (목업 색 분포 재현).

**정렬**: 성공률 desc, 표본 없는(분모 0) 멤버는 맨 아래.

### S3 Weekly Schedule (좌)

이번 주 월요일 00:00 ~ 다음 주 월요일 00:00 범위의 이벤트를 시간 오름차순으로 최대 5개 카드.

**이벤트 소스 합집합**:
- `Interview.scheduled_at`
- `ActionItem.scheduled_at` (due_at 은 사용하지 않음)

**카드 표시 규칙**:
- 상단 라벨(날짜+시간) 색: Interview=info / ActionItem action_type 이 고객사 관련이면 warning / 그 외 ink3
- 제목: Interview 는 "임원 인터뷰" 같은 타입 라벨, ActionItem 은 `title`
- 부제: Interview 는 "후보자: {candidate.name} · {location}", ActionItem 은 "{project.title} · {client.name}"

**빈 상태**: "이번 주 일정이 없습니다" 빈 카드 1개.

### S3 Monthly Calendar (우)

이번 달 7×6 그리드. 월 이동은 Phase 2a 범위 밖.

**서비스가 내려주는 구조**: `monthly_calendar = [{"date": int, "is_today": bool, "is_outside": bool, "event_label": str | None}, ...]` 의 42개(또는 35~42) 항목 리스트. 트레일링 이전 달 / 이번 달 / 리딩 다음 달 모두 포함.

**이벤트 라벨 규칙** (하루에 여러 건이어도 한 줄):
1. 해당 날짜에 Interview 가 있으면 → "인터뷰" (N건이면 "인터뷰 N")
2. Interview 없고 ActionItem(`scheduled_at`) 있으면 → "일정 N"
3. 둘 다 없으면 → `None` (라벨 안 그림)

**셀 스타일**:
- `is_outside=True` → `cal-day muted`
- `is_today=True` → `cal-day today`
- 그 외 → `cal-day`

스코프: Owner=조직 전체, Consultant=본인 담당 프로젝트의 Interview + 본인 assignee ActionItem.

## 템플릿 변경 범위

`dash_full.html` 구조는 유지, 값만 교체:

- S1-1, S1-3: 숫자 자리만 `{{ ... }}` 로 교체
- S2-1: `<li>` 1개를 `{% for %}` 반복으로 변환, 아바타 div 에서 gradient 클래스 제거
- S3 Weekly: 카드 3개를 `{% for %}` 반복으로 변환, 이벤트 타입별 색 분기 `{% if %}`
- S3 Monthly Calendar: `cal-day` 42개를 `{% for cell in monthly_calendar %}` 로 변환

Phase 2b 카드(S1-2 dark tile, S2-2 Recent Activity 리스트)는 변경 없음.

## 빈 상태

- S1-1 성공률 분모 0 → "—"
- S2-1 멤버 성공률 분모 0 → "—", progress width 0%
- S2-1 멤버 혼자 → 본인 한 줄만
- S3 Weekly 이벤트 0 → "이번 주 일정이 없습니다" 빈 카드
- S3 Monthly 이벤트 0 날짜 → 날짜 숫자만 (기존 그대로)

## 테스트 전략

`tests/test_dashboard_phase2a.py` 신규 파일. pytest-django `Client` 로 `GET /dashboard/` 실제 요청 기반 검증 (내부 helper 직접 호출 안 함).

**테스트 케이스 최소 셋**:
- Owner 로그인 + 프로젝트/Application/Interview/ActionItem fixture → 각 카드 숫자 HTML 문자열 assert
- Consultant 로그인 → 본인 담당 프로젝트만 집계되는지 (타 consultant 프로젝트 제외 확인)
- 빈 조직 → "—" · "이번 주 일정이 없습니다" 렌더
- S2-1 팀 순서 → 성공률 desc, 표본 없는 멤버 맨 아래
- S3 Monthly Calendar 오늘 날짜 셀에 `today` 클래스 포함

## 태스크 분할

1. **P2a-1**: `_scope_projects` + `get_dashboard_context` 뼈대 + 뷰 연결 (빈 dict 반환, 기존 하드코딩 유지)
2. **P2a-2**: S1-1 Monthly Success — 서비스 + 템플릿 + 테스트
3. **P2a-3**: S1-3 Project Status — 서비스 + 템플릿 + 테스트
4. **P2a-4**: S2-1 Team Performance — 서비스 + 템플릿 + 테스트
5. **P2a-5**: S3 Weekly Schedule — 서비스 + 템플릿 + 테스트
6. **P2a-6**: S3 Monthly Calendar — 서비스 + 템플릿 + 테스트

각 Task 는 서비스 helper + 템플릿 교체 + 테스트를 하나의 커밋으로.

## 디자인 시스템 준수

- `<style>` 블록 금지, Tailwind 유틸리티만 사용
- 인라인 `text-[Xpx]`, hex 색 금지 (SVG stroke 는 허용)
- progress 막대 width 만 `style="width:{{ pct }}%"` 허용
- 기존 Phase 1 클래스(`eyebrow`, `tnum`, `progress`, `status-dot`, `cal-day`, `cal-event`) 재사용

## 오픈 이슈

- **한글명 저장 관행** — 실제 User 레코드에 한글이 `last_name+first_name` 분리 저장인지, `username` 하나에 통으로 저장인지 구현 단계에서 샘플 데이터 확인 후 표시 로직 확정.
- **ActionItem.action_type 고객사 관련 구분** — S3 Weekly 에서 warning 색 분기 기준이 되는 action_type 코드값. 구현 단계에서 `ActionType` 레코드 스캔 후 화이트리스트 확정.
