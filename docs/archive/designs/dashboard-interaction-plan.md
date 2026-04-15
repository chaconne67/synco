# Dashboard Interaction Plan

> **목표**: `assets/ui-sample/dashboard.html` 목업의 각 요소를 클릭했을 때 열릴
> 서브 페이지·모달·액션을 체계적으로 기획한다. 현재 Phase 1 단순화 모델과 P13
> 기획서가 요구하는 확장 모델을 함께 반영한다.
>
> **작성일**: 2026-04-15
> **소스**: `docs/plans/headhunting-workflow/P13-dashboard.md` · P06 · P07 · P09 ·
> P16 · `docs/forge/headhunting-workflow/p13/design-spec-agreed.md` ·
> `docs/designs/20260411-main-dashboard/`

---

## 1. 전제와 범위

- 현재 `projects.models` 의 `ProjectPhase` 는 `searching/screening` 2단계로 단순화된
  Phase 1 버전이며, P13 기획서는 `NEW → SEARCHING → RECOMMENDING → INTERVIEWING →
  NEGOTIATING → CLOSED_SUCCESS` 의 풍부한 상태 그래프를 전제한다. 본 기획서는
  **P13 비전을 기준**으로 작성하고, 현재 모델로 즉시 바인딩 가능한 것과 확장이
  필요한 것을 구분한다.
- 본 문서는 **디자인/기획** 레이어이며, 코드 구현 순서는 별도 plan 문서에서
  다룬다.
- 대시보드는 컨설턴트의 하루가 시작되는 지점이다. 모든 인터랙션은 "여기서
  클릭 → 실제 업무 화면" 의 **1~2 step 직행성**을 원칙으로 한다.

---

## 2. 위젯별 인터랙션 지도

현재 목업에 존재하는 모든 위젯과 P13 기획서가 요구하는 추가 위젯을 포함한다.
**형식 표기**: T=페이지 이동, M=모달/drawer, I=인라인 액션.

### 2.1 상단 KPI 로우

| # | 위젯 | 클릭 타겟 | 형식 | 모델 바인딩 |
|---|---|---|---|---|
| A1 | Monthly Success (24) | `projects.html?filter=closed&result=success&period=month` | T | `Project.filter(status=CLOSED, result=SUCCESS, closed_at__month=now)` |
| A2 | Monthly Success · In Progress 12 | `projects.html?filter=active` | T | `Project.filter(status=OPEN)` |
| A3 | Monthly Success · Success Rate 82% | `reports/performance.html` | T | 집계: success / (success+fail) |
| A4 | Estimated Revenue (₩842,500) | `reports/revenue.html` | T | 신규 `ProjectFee` 모델 |
| A5 | Revenue · Target Progress 76% | `settings/revenue-target.html` 모달 | M | 신규 `OrgTarget.monthly_revenue` |
| A6 | Project Status · 진행 42 | `projects.html?phase=searching,screening&status=open` | T | Project |
| A7 | Project Status · 심사 18 | `projects.html?phase=screening` | T | Project |
| A8 | Project Status · 완료 114 | `projects.html?status=closed` | T | Project |

### 2.2 Team Performance (중앙 좌측, col-span-8)

| # | 위젯 | 클릭 타겟 | 형식 | 모델 |
|---|---|---|---|---|
| B1 | 카드 전체 | `team.html` | T | Membership |
| B2 | 멤버 행 (아바타+이름) | `team-member-detail` 모달 또는 `team.html#member` | T/M | User + 집계 |
| B3 | "8 active" 숫자 | `projects.html?owner={user_id}` | T | `Project.assigned_consultants` |
| B4 | Completion 92% 바 | 멤버 상세 drawer (KPI 내역) | M | 컨설턴트 KPI 뷰 |
| B5 | "VIEW ALL MEMBERS →" 링크 | `team.html` | T | — |

### 2.3 Recent Activity (중앙 우측, col-span-4)

| # | 위젯 | 클릭 타겟 | 형식 | 모델 |
|---|---|---|---|---|
| C1 | 카드 헤더 영역 | `activity-log.html` (풀 히스토리) | T | 신규 `ActivityLog` |
| C2 | "Candidate placement confirmed" | `projects/{id}#offer-tab` | T | `Application.hired_at` |
| C3 | "New candidate added" | `candidate-detail.html?id={id}` | T | Candidate |
| C4 | "Client meeting notes updated" | `clients/{id}#notes` | T | `Client.notes` |
| C5 | "Project deadline approaching" | `projects/{id}` + deadline 경고 배너 | T | `Project.deadline` |
| C6 | 새로고침 아이콘 (우측 상단) | 카드 내부 재조회 | I | — |

### 2.4 Weekly Schedule (하단 좌측, col-span-4)

| # | 위젯 | 클릭 타겟 | 형식 | 모델 |
|---|---|---|---|---|
| D1 | "Weekly Pipeline Review" 카드 | 팀 미팅 상세 모달 | M | 신규 `Meeting` |
| D2 | "Executive Interview" 카드 | `interview-detail` 모달 | M | Interview |
| D3 | "Client Briefing: SK Hynix" | `clients/{id}?meeting={meeting_id}` | T | Client + Meeting |
| D4 | 카드 우측 `···` 버튼 | 컨텍스트 메뉴 (편집·취소·일정 변경) | M | — |

### 2.5 Monthly Schedule (하단 우측 캘린더, col-span-8)

| # | 위젯 | 클릭 타겟 | 형식 | 모델 |
|---|---|---|---|---|
| E1 | 날짜 셀 (이벤트 있음) | 당일 이벤트 리스트 drawer | M | Interview + Meeting scheduled_at |
| E2 | 빈 날짜 셀 | 이벤트 추가 모달 | M | Meeting 생성 |
| E3 | 이벤트 pill (예: Board Mtg) | 이벤트 상세 모달 | M | Meeting/Interview |
| E4 | Today pill (25일) | 오늘의 이벤트 drawer | M | — |
| E5 | 월 네비게이션 (현재 없음 → **추가 필요**) | 전/다음 월 전환 | I | — |

### 2.6 상단 헤더

| # | 위젯 | 클릭 타겟 | 형식 | 모델 |
|---|---|---|---|---|
| F1 | 알림 아이콘 (벨) | 알림 drawer (우측 슬라이드) | M | 신규 `Notification` |
| F2 | 도움말 아이콘 (?) | 단축키·가이드 모달 | M | — |
| F3 | 사용자 아바타 "SP" | 프로필 drawer (설정·로그아웃) | M | User |

### 2.7 글로벌 FAB (우측 하단 + 버튼)

| # | 위젯 | 클릭 타겟 | 형식 | 모델 |
|---|---|---|---|---|
| G1 | FAB | 글로벌 "새로 만들기" 퀵 메뉴 | M | — |
| G1a | → 새 프로젝트 | `project-create` 모달 또는 페이지 | M/T | Project |
| G1b | → 새 후보자 (이력서 업로드) | `candidate-import` 모달 → AI 추출 → 저장 | M | Candidate + Resume |
| G1c | → 새 클라이언트 | Client form 모달 | M | Client |
| G1d | → 컨택 기록 추가 | Contact form 모달 (프로젝트 선택 → 후보자 선택) | M | Contact |

---

## 3. P13 기획에는 있으나 현재 목업에 없는 위젯 (필수 추가)

아래 네 블록이 P13 기획서가 대시보드의 **핵심**으로 지정한 영역이나 현재
목업에서는 빠져 있다. 다음 대시보드 업데이트 시 우선 추가 대상.

### 3.1 🚨 오늘의 액션 (Today's Actions) — 핵심 누락

컨설턴트의 하루는 이 리스트부터 시작된다. 긴급도는 자동 산정.

| 항목 | 조건 | 긴급도 | 클릭 시 |
|---|---|---|---|
| 재컨택 예정 오늘·과거 | `Contact.next_contact_date <= today` | 🔴 | 컨택 로그 작성 모달 |
| 면접 임박 | `Interview.scheduled_at` 오늘·내일 | 🟡 | 면접 상세 모달 |
| 서류 검토 대기 2일+ | `Submission.submitted_at <= today-2` AND 피드백 없음 | 🟡 | 피드백 입력 모달 |
| 컨택 잠금 만료 임박 | `Contact.locked_until <= today+1` | 🔴 | 재컨택 알림 |
| Offer 회신 대기 | `Offer.status=negotiating` AND 3일 경과 | 🟡 | Offer 상세 모달 |

**서비스 레이어**: `dashboard.services.get_urgent_actions(user)` → 위 5개 쿼리
유니온 + 긴급도 스코어링. 목업에서는 아이템 8~12개 노출.

### 3.2 내 파이프라인 (Funnel)

가로 퍼널 시각화: `NEW → SEARCHING → RECOMMENDING → INTERVIEWING → NEGOTIATING →
CLOSED_SUCCESS`. 각 단계의 Project 개수. 클릭 시 해당 단계 필터의
`projects.html` 로 이동. 현재 "Project Status" 카드가 이 역할을 부분적으로
수행하지만 4단계 세분화가 빠져있음.

### 3.3 승인 요청 큐 (Owner 전용)

`ProjectApproval` 중 미처리 건 리스트. 카드 내부 인라인 버튼으로 승인·반려
가능. consultant 권한일 때는 숨김.

### 3.4 팀 KPI (Owner 전용)

- 컨택 → 추천 전환율
- 추천 → 면접 전환율
- 평균 클로즈 기간 (일)
- 월 목표 대비 달성률

---

## 4. 서브 페이지·모달 카탈로그 (우선순위 부여)

대시보드 인터랙션을 완성하려면 아래 목업이 추가 제작되어야 한다.

### 🔴 P0 — 핵심 흐름 차단

| # | 파일 | 설명 |
|---|---|---|
| 1 | `project-detail.html` | 프로젝트 상세. 6탭: 개요·서칭·컨택·추천·면접·오퍼. 대시보드 클릭 대부분의 최종 목적지. |
| 2 | `contact-log-modal` (project-detail 내부) | 컨택 기록 작성. "오늘의 액션" 대부분의 끝점. |
| 3 | `project-create` | 프로젝트 생성: 클라이언트 선택 → JD 업로드/붙여넣기 → AI 분석 → 저장. |
| 4 | `candidate-import` | 이력서 업로드 → AI 추출 → 중복 체크 → Candidate 생성. |

### 🟡 P1 — 보조 흐름

| # | 파일 | 설명 |
|---|---|---|
| 5 | `interview-detail-modal` | 면접 등록·수정·결과 입력. |
| 6 | `submission-form` | 추천 서류 패키지 작성 (선택된 후보자들 + 코멘트). |
| 7 | `offer-form-modal` | Offer 제안/협상/수락·거절 기록. |
| 8 | `client-detail.html` | 거래 이력·노트·미팅 기록. clients-list 카드 클릭 타겟 (현재 누락). |
| 9 | `activity-log.html` | 전체 활동 로그 풀 히스토리. |

### 🟢 P2 — Owner / 관리용

| # | 파일 | 설명 |
|---|---|---|
| 10 | `approval-queue.html` | 승인 요청 처리. |
| 11 | `reports/performance.html` | 성사율·전환율·클로즈 기간 리포트. |
| 12 | `reports/revenue.html` | 수수료 집계. 신규 `ProjectFee` 필요. |
| 13 | `notification-drawer` | 알림 패널. 신규 `Notification` 필요. |
| 14 | `settings/` 계열 | 프로필·조직·뉴스 소스·팀 초대·수수료 목표 등. |

---

## 5. 모델 연결 매트릭스

| 기능 영역 | 기존 모델 그대로 | 모델 확장 필요 | 신규 모델 필요 |
|---|---|---|---|
| 오늘의 액션 집계 | Contact·Interview·Submission·Offer 공통 쿼리 | `Contact.next_contact_date`, `Contact.locked_until` 추가 | — |
| 파이프라인 Funnel | — | `ProjectPhase` 를 10단계로 확장 | — |
| Estimated Revenue | — | — | `ProjectFee` (contract_value, fee_rate, projected) |
| 월 목표 진행률 | — | — | `OrgTarget` (monthly_revenue, monthly_placements) |
| Recent Activity | — | — | `ActivityLog` (actor, verb, object_ct, object_id, meta, at) |
| 알림 drawer | — | — | `Notification` (user, kind, payload, read_at) |
| Monthly/Weekly Schedule | Interview.scheduled_at 일부 | — | `Meeting` (interview 가 아닌 일반 미팅) |
| 팀 KPI | — | — | 서비스 레이어에서 집계 (모델 추가 불필요) |
| 승인 큐 | `ProjectApproval` 존재 | — | — |

**모델 변경 요약**
- **확장** (기존 모델에 필드 추가): Contact, ProjectPhase
- **신규 모델**: ProjectFee, OrgTarget, ActivityLog, Notification, Meeting

각 신규 모델은 별도 마이그레이션 단위로 분리 가능하며, 대시보드 기능별로
점진 도입할 수 있다. 순서 제안:
1. ActivityLog (Recent Activity 위젯만으로도 가치)
2. Contact 필드 확장 (오늘의 액션의 대부분을 이 하나로 해결)
3. ProjectPhase 확장 (파이프라인 Funnel)
4. Notification
5. Meeting
6. ProjectFee / OrgTarget (리포트·수익)

---

## 6. 제작 순서 제안

대시보드 인터랙션을 **단절 없이 체감할 수 있는 최소 흐름**을 먼저 완성하는 것을
우선한다.

1. **`project-detail.html` 목업** — 대시보드 클릭의 절반 이상이 여기로 수렴.
   6개 탭 중 최소 `개요 · 컨택 · 추천` 3탭부터.
2. **`contact-log-modal` + `candidate-import`** — 하루 업무의 입력 양쪽 진입점.
3. **`client-detail.html`** — clients-list 카드 클릭 타겟 (현재 dead link).
4. **대시보드 목업 보강** — "오늘의 액션", "내 파이프라인 Funnel", (Owner)
   "승인 큐", "팀 KPI" 4개 블록 추가.
5. **`interview-detail-modal` / `submission-form` / `offer-form-modal`** —
   프로젝트 상세의 심층 모달들.
6. 나머지 (approval-queue, reports, settings, notification-drawer).

---

## 7. 체크리스트 (업데이트 추적용)

### 현 시점 완료

- [x] 대시보드 기본 레이아웃 (Monthly Success / Revenue / Project Status / Team
  Performance / Recent Activity / Weekly Schedule / Monthly Schedule)
- [x] 사이드바 8개 메뉴 네비게이션 연결
- [x] `candidate-list.html`, `candidate-detail.html`, `projects.html`,
  `clients-list.html`, `references.html`, `team.html`, `newsfeed.html` 목업

### P0 (차단 요소)

- [ ] `project-detail.html` (6탭)
- [ ] `contact-log-modal` 패턴
- [ ] `project-create` 플로우
- [ ] `candidate-import` 플로우
- [ ] 대시보드 "오늘의 액션" 블록 추가
- [ ] 대시보드 "내 파이프라인 Funnel" 블록 추가

### P1 (보조 흐름)

- [ ] `interview-detail-modal`
- [ ] `submission-form`
- [ ] `offer-form-modal`
- [ ] `client-detail.html`
- [ ] `activity-log.html`

### P2 (관리·리포트)

- [ ] `approval-queue.html`
- [ ] `reports/performance.html`
- [ ] `reports/revenue.html`
- [ ] `notification-drawer`
- [ ] `settings/` 계열

### 모델 확장/신규

- [ ] Contact 필드 확장 (next_contact_date, locked_until)
- [ ] ProjectPhase 10단계 확장
- [ ] `ActivityLog` 모델
- [ ] `Notification` 모델
- [ ] `Meeting` 모델
- [ ] `ProjectFee` 모델
- [ ] `OrgTarget` 모델
