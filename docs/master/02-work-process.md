# synco 업무 프로세스

> **마스터 문서 · 단일 진실 소스**
> 작성: 2026-04-16 · 범위: 사용자가 synco를 실제로 어떻게 쓰는가 · 데이터와 업무 파이프라인
> 자매 문서: [01-business-plan.md](01-business-plan.md) · [03-engineering-spec.md](03-engineering-spec.md)

이 문서는 "synco로 하루의 업무가 어떻게 흘러가는가"를 기술한다. 누가 어떤 역할로 들어와서, 어떤 데이터를 입력하고, 어떤 화면에서 어떤 버튼을 누르며, 그 결과가 어떤 데이터 파이프라인을 탄 뒤, 다시 어떤 알림으로 돌아오는지를 한 문서에서 본다.

---

## 1. 한눈에

synco는 **중소 서치펌 컨설턴트가 하루 종일 띄워놓고 쓰는 워크벤치**다. 이메일/드라이브에 쌓이는 이력서를 자동으로 파싱해 DB화하고, JD가 들어오면 자연어 검색으로 후보자를 찾고, 추천 서류를 AI로 생성해 고객사에 제출하고, 면접/오퍼/클로징까지의 모든 **할 일(Action)**을 한 곳에서 추적한다.

핵심 개념 세 가지만 먼저 잡고 간다.

1. **Project (프로젝트)** — 고객사가 의뢰한 한 건의 포지션. 마감(deadline)을 가진 작업 컨테이너.
2. **Application (지원)** — 특정 프로젝트에 특정 후보자를 "붙였다"는 매칭 사실. 상태값을 가지지 않고 **ActionItem의 진행으로 파생된다.**
3. **ActionItem (액션 아이템)** — 헤드헌터의 1급 업무 단위. "김철수에게 내일 오전 카카오톡 연락" 같은 할 일 하나. 예정·완료·결과를 가지며 완료 시 다음 액션을 제안한다.

> synco는 **상태 추적 도구가 아니라 할 일 관리 도구**다. 컨설턴트의 하루는 "지금 어느 단계냐?"가 아니라 "오늘 뭘 해야 하느냐?"로 굴러간다. 그래서 Project와 Application의 단계는 ActionItem에서 자동으로 파생되고, 사용자는 액션만 입력하면 된다.

---

## 2. 사용자 롤과 멀티테넌시

synco의 최상위 경계는 **Organization(서치펌)** 이다. 한 Organization 안의 데이터(프로젝트·후보자·고객사)는 같은 조직원끼리만 공유되며, 다른 서치펌은 접근할 수 없다. (DB 공유 네트워크는 별도 레이어로 Phase 2에서 구축.)

한 Organization에 속한 사용자는 `Membership`이라는 1:1 관계로 연결되며, 역할(role)과 상태(status)를 가진다.

| 역할 | 권한 |
|------|------|
| **Owner** | 조직 관리, 팀 멤버 초대/승인/해제, 승인 큐 처리, 참고 데이터(대학·기업·자격증) 관리, 수퍼 관리자 영역 접근 |
| **Consultant** | 프로젝트 CRUD, 후보자 DB 전체 이용, 추천·면접·오퍼 진행, 자기 프로젝트에 후보자 추가, 액션 기록 |
| **Viewer** | 읽기 전용. 리포트/대시보드 열람 (초기 회원이거나 외부 감사용) |

| 상태 | 의미 |
|------|------|
| `pending` | 초대코드 입력 후 Owner의 승인 대기 중 |
| `active` | 정상 활동 가능 |
| `rejected` | 승인 거절됨 (재신청 가능) |

---

## 3. 온보딩 여정 — 처음 가입부터 첫 프로젝트까지

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Kakao 로그인 │ →  │ 초대코드 입력 │ →  │ Owner 승인   │ →  │ 대시보드 진입│
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
       ↓                                        ↓
  최초 가입이면                            승인 대기 페이지
  /accounts/invite/                        /accounts/pending/
```

### 3.1 시작점: Kakao 로그인
- 진입 URL: `/accounts/login/`
- 카카오 OAuth만 지원. 이메일/비밀번호 가입 없음.
- 카카오에서 돌아오면 `/accounts/kakao/callback/`에서 `User` 레코드를 만들거나 찾아 세션 로그인.

### 3.2 초대코드 입력
- 신규 유저는 `/accounts/invite/` 로 리다이렉트된다.
- 초대코드는 `InviteCode` 테이블에서 발급(Owner가 팀 관리 화면에서 생성). 코드에는 어느 Organization에 어떤 role로 합류할지, 만료일과 사용 횟수 상한이 설정돼 있다.
- 코드를 입력하면 Membership이 생성되며 상태는 `pending`. `used_count`가 1 증가.

### 3.3 Owner 승인
- Owner의 대시보드에는 "승인 대기" 카운트가 표시된다(사이드바 Approvals 메뉴에 배지).
- Owner가 `/org/members/` 에서 pending 멤버를 확인하고 활성화(승인) 또는 거절.
- 활성화되면 Membership.status → `active`. 다음 로그인부터 대시보드로 직행.

### 3.4 설정 초기화 (선택)
- `/accounts/settings/` 의 4개 탭
  - **프로필**: 이름, 회사, 업종, 지역 등
  - **이메일 모니터링**: Gmail 연결. 이력서 첨부 메일 자동 수집용
  - **텔레그램 연결**: 봇 챗 ID 바인딩. 긴급 알림 수신
  - **알림**: 카테고리별 Web/Telegram 채널 on/off

### 3.5 첫 프로젝트 등록
- 사이드바 "Projects" → "새 프로젝트" 버튼
- 클라이언트 선택 또는 신규 생성 → JD 입력(파일/드라이브/텍스트) → 저장
- 저장 즉시 JD 분석이 비동기로 시작되고, 완료되면 검색/매칭 탭에서 후보자 매칭 결과가 보인다.

---

## 4. 메인 네비게이션 지도

사이드바는 9개 메뉴로 구성된다. 모든 전환은 HTMX(`hx-get` + `hx-target="main"` + `hx-push-url="true"`) 기반이라 페이지 전체 리로드 없이 동작한다.

| 순서 | 메뉴 | 경로 | 역할 | 권한 |
|------|------|------|------|------|
| 1 | Dashboard | `/dashboard/` | 하루의 시작점. KPI, 오늘의 할 일, 팀 성과, 일정, 캘린더 | 전원 |
| 2 | Candidates | `/candidates/` | 후보자 검색/리스트, 상세, 검수 대기열 | 전원 |
| 3 | Projects | `/projects/` | 프로젝트 리스트(칸반/테이블), 상세, 생성/수정/종료 | 전원 |
| 4 | Clients | `/clients/` | 고객사 리스트/상세, 계약 이력 | 전원 |
| 5 | References | `/reference/` | 대학·기업·자격증 마스터 데이터 | Owner |
| 6 | Approvals | `/projects/approvals/` | 프로젝트 충돌 시 승인 큐 (배지로 건수 표시) | Owner |
| 7 | Newsfeed | `/news/` | 업계 뉴스, 채용·인사 동향 | 전원 |
| 8 | Team | `/org/` | 조직원 관리, 초대코드 발급, 역할 변경 | Owner |
| 9 | Settings | `/accounts/settings/` | 프로필, 이메일/텔레그램/알림 | 본인 |

사이드바 외에 글로벌 **FAB(우측 하단 + 버튼)** 으로 "새 프로젝트 / 새 후보자 / 새 고객사 / 컨택 기록"을 어디서나 바로 띄울 수 있다(대시보드 인터랙션 플랜의 G1 블록).

---

## 5. 헤드헌팅 전체 워크플로우

```
 ① 영업             ② JD 수신        ③ 서칭          ④ 추천          ⑤ 심사
┌──────────┐      ┌──────────┐     ┌──────────┐    ┌──────────┐   ┌──────────┐
│클라이언트│      │프로젝트  │     │후보자    │    │클라이언트│   │ 면접 →   │
│미팅/수주 │ ───→ │생성·JD  │ ──→ │검색·매칭 │──→ │서류 제출 │─→ │ 오퍼 →   │
│          │      │입력/분석 │     │컨택·조율 │    │          │   │ 클로즈   │
└──────────┘      └──────────┘     └──────────┘    └──────────┘   └──────────┘
 Client         Project(phase=searching)        Application       Project(phase=screening)
                                                                         ↓
                                                                  status=closed
                                                                  result=success|fail
```

### 5.1 영업 — 클라이언트 수주
- **Clients** 메뉴에서 고객사 등록(회사명, 업종, 규모, 지역, 담당자 연락처, 메모).
- 계약 조건은 `Contract` 모델에 시작/종료일·약관·상태(협의중/체결/만료/해지)로 기록.
- 실제 영업 미팅 자체를 synco 안에 기록하는 전용 flow는 초기 버전에는 없다 — 필요 시 Client.notes에 메모.

### 5.2 JD 수신 — 프로젝트 생성
- **Projects → 새 프로젝트** 로 진입. 선택 가능한 JD 소스는 세 가지: `upload`(파일), `drive`(Google Drive 파일 ID), `text`(직접 붙여넣기).
- 저장 시 프로젝트는 `phase=searching` / `status=open` / `result=""` / `deadline=<선택>` 으로 생성.
- JD 분석은 별도 액션(`/projects/<pk>/analyze-jd/`)으로 LLM을 호출해 `requirements`(필수 스킬·경력·학력·자격증·키워드)를 JSON으로 채운다.
- 분석 결과는 "JD Results" 탭에서 검토 후 수정 가능.

### 5.3 서칭 — 후보자 매칭
- **프로젝트 상세 → Search/Matching 탭**
- JD 분석 결과를 기반으로 `CandidateEmbedding`(pgvector)과의 유사도 + 구조 필터를 조합한 ORM 쿼리로 매칭 후보자 목록을 보여준다.
- Consultant는 "프로젝트에 후보자 추가"(`project_add_candidate`) 버튼으로 매칭 리스트에서 `Application` 레코드를 생성한다.
- Application이 만들어지면 바로 `Application.current_state = "matched"` (ActionItem 하나도 없는 상태).

### 5.4 컨택 — ActionItem 생성·완료
매칭된 후보자에게는 "할 일"이 줄줄이 달린다. Consultant는 각 액션을 생성·완료하며 업무를 이어간다.

- 사용 가능한 액션 종류는 `ActionType` 테이블(DB 관리). 서칭 국면 13개 + 심사 국면 7개 + 범용 3개 = 23종 정도. Owner가 관리자 페이지에서 추가·비활성화 가능.
- 대표적 서칭 액션: `search_db`(DB 검색) · `reach_out`(연락) · `share_jd`(JD 공유) · `receive_resume`(이력서 수령) · `pre_meeting`(사전미팅) · `submit_to_client`(클라이언트 제출).
- 완료(`status=done`)할 때 `result` 텍스트와 `completed_at`이 기록되고, `ActionType.suggests_next`에 따라 "다음 액션 제안"이 뜬다. 버튼 한 번으로 다음 ActionItem을 생성할 수 있다(자동 체인).

### 5.5 추천 서류 (`submit_to_client`)
- 서류 제출은 `Submission` 모델이 담당한다. `ActionType.code = "submit_to_client"` 인 ActionItem을 완료하면 1:1로 Submission 레코드가 묶인다.
- Submission은 AI 초안 파이프라인 `SubmissionDraft`와 1:1. 6단계 파이프라인:
  1. **Generate** — AI가 이력서와 JD를 읽고 초안 JSON을 만든다
  2. **Consultation** — 컨설턴트가 음성/텍스트로 코멘트 추가
  3. **Finalize** — AI가 최종 버전을 정제
  4. **Masking** — 개인정보(연락처·연봉 등)를 선택적으로 가림
  5. **Convert** — Word/PDF/HWP 등 원하는 포맷으로 변환
  6. **Download** — 파일 다운로드 + `submit_to_client` 완료 처리
- 이 제출 액션이 완료되면 Project의 `phase`가 **자동으로 `screening`으로 전환**된다(OR 규칙: 활성 Application이 하나라도 submit_to_client를 완료하면 screening).

### 5.6 면접·오퍼 (`interview_round`, `confirm_hire`)
- 고객사 피드백이 오면 → `receive_doc_feedback` 액션을 완료하며 내용 기록
- 면접 잡히면 → `schedule_interview` 액션 → `interview_round` 액션에 묶인 `Interview` 레코드 생성 (일정, 방식, 라운드, 결과)
- 합격이면 → `confirm_hire` 액션을 완료. **모든 활성 Application이 자동 드롭되고**, 해당 Application은 `hired_at`이 세팅되며, Project는 `status=closed / result=success`로 전환.

### 5.7 종료 처리
- 성공(`success`): 위 `confirm_hire` 자동 종료 또는 수동 종료.
- 실패(`fail`): 고객사가 철회하거나 기한 내 적임자를 못 찾을 때. 프로젝트 상세에서 "종료" 버튼 → 사유/메모 입력.
- 종료 시점에는 `closed_at` 타임스탬프와 `result`가 기록되며, 이후 대시보드/리포트의 집계에 쓰인다.

---

## 6. Phase × Application state × ActionItem — 3층 모델

synco의 상태 모델은 **3개의 층**이 서로 영향을 주고받는다. 이해해두면 대시보드가 왜 그런 식으로 동작하는지 쉽게 읽힌다.

```
 ┌────────────────────────── Project ──────────────────────────┐
 │  phase:  searching / screening     (자동 파생)              │
 │  status: open / closed             (수동 또는 confirm_hire) │
 │  result: success / fail / ""       (종료 시 세팅)            │
 │  deadline: Date                    (클라이언트 마감)         │
 │  ├── Application(A) ──────────────────────────────────┐    │
 │  │    hired_at / dropped_at + drop_reason              │    │
 │  │    current_state = 최신 완료 ActionItem에서 파생   │    │
 │  │    ├── ActionItem #1 [search_db · done]             │    │
 │  │    ├── ActionItem #2 [reach_out · done]             │    │
 │  │    ├── ActionItem #3 [receive_resume · done]        │    │
 │  │    ├── ActionItem #4 [submit_to_client · done] ◀── phase 전환 트리거
 │  │    └── ActionItem #5 [interview_round · pending]    │    │
 │  └──────────────────────────────────────────────────────┘    │
 │  ├── Application(B) … dropped                                │
 │  └── Application(C) … matched                                │
 └──────────────────────────────────────────────────────────────┘
```

### 6.1 Project.phase — "서칭 / 심사" 자동 파생
- 초기값: `searching`
- **전환 규칙(OR)**: 활성 Application 중 하나라도 `submit_to_client` ActionItem을 완료했으면 `screening`
- 전환 시점: ActionItem 저장 signal에서 `compute_project_phase(project)` 호출로 재계산

### 6.2 Application.current_state — 파생 속성
DB에 저장하지 않고, 렌더링할 때 계산한다.

```
if dropped_at:  return "dropped"
if hired_at:    return "hired"
latest_done = 최신 완료 ActionItem
if latest_done is None: return "matched"
return STATE_FROM_ACTION_TYPE[latest_done.action_type.code] or "in_progress"
```

`STATE_FROM_ACTION_TYPE`은 코드 상수 매핑: `pre_meeting → pre_met`, `submit_to_client → submitted`, `interview_round → interviewing`, `confirm_hire → hired`.

### 6.3 ActionItem — 1급 업무 단위
- `application` 에 FK로 여러 개 달림
- `action_type` 에 FK (PROTECT; 보호된 4개 타입은 삭제 불가)
- `status`: `pending` / `done` / `skipped` / `cancelled`
- `scheduled_at`, `due_at`, `completed_at`, `channel`, `result`, `note`, `assigned_to`, `parent_action`
- 완료 시 다음 액션 후보를 `ActionType.suggests_next` 배열에서 뽑아 사용자에게 제안

### 6.4 드롭(Drop)과 종료(Hire)
- Application 드롭: `dropped_at`과 `drop_reason`(unfit / candidate_declined / client_rejected / other), `drop_note`를 세팅. 해당 Application의 pending 액션은 모두 cancelled.
- Application hire: `hired_at` 세팅. **같은 프로젝트 내 다른 활성 Application은 자동 드롭**, Project는 `closed + success`.

---

## 7. 화면별 업무 흐름

### 7.1 Dashboard — 하루의 시작

**레이아웃 기준**: `assets/ui-sample/dashboard.html` (디자인 시스템의 단일 진실 소스)

**구성 블록** (인터랙션은 `docs/designs/dashboard-interaction-plan.md` 참조):

```
┌─────────────────────────────────────────────────────────────┐
│ Top header: 데스크·헤드헌팅 · 날짜/시간 · 알림·프로필       │
├──────────┬──────────────────────────────────────────────────┤
│          │ KPI ROW                                          │
│          │  ┌─────────┬─────────┬─────────┐                 │
│          │  │Monthly  │Estimated│Project  │                 │
│          │  │Success  │Revenue  │Status   │                 │
│ Sidebar  │  │   24    │₩842,500 │진/심/완 │                 │
│ (260px)  │  └─────────┴─────────┴─────────┘                 │
│          │                                                  │
│          │ ┌─────────────────────┬──────────────────┐       │
│          │ │ Team Performance    │ Recent Activity  │       │
│          │ │  멤버별 진행률 막대 │  최근 4개 피드   │       │
│          │ └─────────────────────┴──────────────────┘       │
│          │                                                  │
│          │ ┌─────────────┬────────────────────────────┐     │
│          │ │ Weekly      │ Monthly Schedule           │     │
│          │ │ Schedule    │ (캘린더 그리드, today 강조)│     │
│          │ └─────────────┴────────────────────────────┘     │
└──────────┴──────────────────────────────────────────────────┘
```

**인터랙션 원칙**: 모든 카드 요소는 "클릭 → 해당 업무 화면 1~2 step 직행"
- KPI 숫자 클릭 → 필터링된 Projects 리스트
- Team 멤버 행 → 해당 멤버 상세 drawer 또는 `projects?owner=<id>`
- Activity 항목 → 관련 프로젝트/후보자/클라이언트 상세
- 캘린더 셀 → 당일 이벤트 리스트 drawer

**핵심 누락 블록(P13 기획 기준)** — 다음 업데이트에서 추가 예정:
- 🚨 **오늘의 액션** — 재컨택 예정·면접 임박·서류 검토 대기·컨택잠금 만료 등 5종 쿼리 유니온 → 긴급도 스코어링
- **내 파이프라인 Funnel** — `NEW → SEARCHING → RECOMMENDING → INTERVIEWING → NEGOTIATING → CLOSED_SUCCESS` 단계별 개수
- **승인 요청 큐** (Owner only)
- **팀 KPI** (전환율·평균 클로즈 기간) (Owner only)

### 7.2 Projects — 의뢰 수주부터 클로징까지

**리스트 뷰**: 칸반(phase별 컬럼) / 보드 / 테이블 전환 가능.

**상세 탭 구조**:
| 탭 | 역할 |
|---|---|
| Overview | KPI, 프로젝트 요약, 최근 액션 타임라인 |
| Search | JD 분석 결과 기반 매칭 후보자 리스트 + 추가 버튼 |
| Applications | 매칭된 후보자들의 카드 뷰. 각 카드에 pending 액션 표시 |
| Submissions | 추천 서류 패키지 목록. 새 초안 생성 진입점 |
| Interviews | 면접 일정·결과 |
| Posting | JD 게시용 텍스트 생성, 채용 공고 사이트 등록/해제 |
| Context | 프로젝트 메모, 수동 컨텍스트 노트 |
| Auto Actions | AI가 제안하는 후속 액션 리스트 (컨설턴트 승인 후 ActionItem으로 전환) |

**주요 동작**:
- 새 프로젝트 → 클라이언트 선택 → JD 입력 → 저장 → (자동) JD 분석 → 매칭
- 후보자 추가 → Application 생성 → 초기 ActionItem 자동 생성
- 액션 완료(HTMX modal) → 다음 액션 제안
- 프로젝트 종료 → `closed_at`/`result`/`note` 기록
- **충돌 감지**: 이미 다른 컨설턴트가 진행 중인 클라이언트/포지션과 겹치면 Owner 승인 큐로 이동(`ProjectApproval`)

### 7.3 Candidates — 후보자 DB

**리스트 뷰**: 카테고리 탭 + 필터 + 자연어 검색.

**검색 방식**:
- **텍스트 검색**: 이름·회사·학교 등 ORM 필터
- **자연어 검색**: "인서울 출신 AICPA 보유 남성, 경력 10년 이상" → LLM이 구조화 필터로 변환 → ORM 쿼리
- **벡터 검색**: `CandidateEmbedding`(pgvector) 유사도. JD 매칭에 주로 쓰임

**상세 화면**:
- 프로필 헤더(이름·현 회사·포지션·경력 연수·상태)
- 학력(`Education`) · 경력(`Career`) · 자격증(`Certification`) · 어학(`LanguageSkill`)
- 이력서 원본(`Resume` 테이블, 여러 버전 가능)
- 추출 로그(`ExtractionLog`) · Discrepancy 리포트(`DiscrepancyReport`) · 검증 진단(`ValidationDiagnosis`)
- 댓글(`CandidateComment`)
- 이 후보자가 진행 중/과거의 Application 타임라인

**검수 플로우** (`/candidates/review/`):
- AI가 이력서에서 뽑아낸 초안의 신뢰도가 낮은 항목만 모아서 보여준다
- Consultant가 항목별로 **Confirm** / **Reject** / **Edit**
- 신뢰도 태그: 원본(`source`) / AI 추론(`inferred`) / AI 생성(`generated`)

### 7.4 Clients — 고객사 관리

- 리스트: 이름·업종·규모·지역·최근 프로젝트 수
- 상세: 기본 정보 + 계약 이력(`Contract`) + 담당자 JSON + 메모
- 마스터 데이터 탭: 해당 고객사가 요구한 포지션 이력, 성공/실패율

### 7.5 References — 참고 마스터 데이터 (Owner)

후보자 평가 기준이 되는 정규화 테이블:

| 모델 | 내용 |
|---|---|
| `UniversityTier` | 대학 랭킹. SKY / SSG / JKOS / KDH / INSEOUL / SCIENCE_ELITE / REGIONAL / 해외 최상위·상위·우수 |
| `CompanyProfile` | 기업 분류. 대기업/중견/중소/외국계/스타트업, 상장 구분, 매출·인원 범위 |
| `PreferredCert` | 선호 자격증. 카테고리별(회계·법률·IT 등) + 가중치(상/중/하) + 별칭 배열 |

Owner만 편집 가능. Consultant는 읽기만. 초기 데이터는 `clients/management/commands/load_reference_data.py` 로 시드.

### 7.6 Newsfeed — 업계 동향

- Owner가 `NewsSource` 등록(URL + 타입 + 카테고리)
- `projects/management/commands/fetch_news.py` 가 주기적으로 기사 수집 → `NewsArticle`
- Gemini 요약/관련성 점수 → `NewsArticleRelevance` (사용자-기사 페어)
- 사이드바에는 "안 읽은 기사 있음" 도트로 표시

### 7.7 Team — 조직원 관리 (Owner)

- 멤버 리스트 (role · status · 활동량)
- 초대코드 발급/폐기 (`InviteCode`)
- pending 멤버 승인/거절
- Organization 정보 수정 (이름·플랜·로고·DB 공유 여부)

### 7.8 Settings — 개인 설정

4개 탭:
- **프로필**: 이름·회사·업종·지역
- **이메일**: Gmail OAuth 연결/해제 (이력서 자동 수집)
- **텔레그램**: 바인딩 코드 발급 → 봇에게 전송 → 인증 → 알림 수신 가능
- **알림**: 4종(`contact_result`, `recommendation_feedback`, `project_approval`, `newsfeed_update`) × 2채널(web/telegram) on/off

---

## 8. 데이터 파이프라인

### 8.1 이력서 인입 경로

```
 ┌───────────┐      ┌───────────┐     ┌──────────┐    ┌───────────┐
 │ Gmail     │      │ Drive     │     │ 수동     │    │ Chrome    │
 │ (첨부)    │      │ (공유 폴더)│     │ 업로드   │    │ Extension │
 └─────┬─────┘      └─────┬─────┘     └────┬─────┘    └─────┬─────┘
       │                  │                │                │
       ▼                  ▼                ▼                ▼
 check_email_resumes  data_extraction  resume_upload   chrome_ext hook
 (cron)               extract (batch)  (view 직접)     (POST 엔드포인트)
       │                  │                │                │
       └────────────┬─────┴────────────────┴────────────────┘
                    ▼
            ┌──────────────────┐
            │ Resume 레코드    │
            │ status=pending   │
            │ file stored      │
            └────────┬─────────┘
                     ▼
            ┌──────────────────┐
            │ 텍스트 추출      │
            │ (doc/docx/pdf/   │
            │  hwp → UTF-8)    │
            └────────┬─────────┘
                     ▼
            ┌──────────────────┐
            │ Gemini Batch     │
            │ (GeminiBatchJob/ │
            │  GeminiBatchItem)│
            │ JD→JSON 구조화   │
            └────────┬─────────┘
                     ▼
            ┌──────────────────┐
            │ Candidate +      │
            │ Education/Career │
            │ /Cert/Language   │
            │ + Resume 바인딩  │
            └────────┬─────────┘
                     ▼
            ┌──────────────────┐
            │ CandidateEmbed-  │
            │ ding 생성        │
            │ (pgvector)       │
            └──────────────────┘
```

**특이점**:
- Gemini Batch API를 쓴다 → 한 번에 수백~수천 건을 비동기로 처리하며, 결과는 `response_json`에 저장
- 파일명 자동 생성 규칙: `{이름}.{YY}.{현회사}.{전회사}.{대학교}`
- 신뢰도 표시 3단계: 원본 확인(source) / AI 추론(inferred) / AI 생성(generated)
- 중복 검출: email/phone 기준으로만 자동 병합. 이름 기반 병합은 금지(동명이인 리스크)

### 8.2 프로젝트 매칭 엔진

```
Project.jd_analysis (LLM 산출물)
 ↓
 requirements JSON (필수 스킬·경력·학력·자격증·키워드)
 ↓
 후보자 쿼리 빌더:
   1. 구조 필터 (경력연수, 학력 tier, 현재 회사 크기, 자격증)
   2. 벡터 유사도 (JD 임베딩 ↔ CandidateEmbedding)
   3. 제외: 이미 이 프로젝트에 Application 있거나, 다른 프로젝트에서 잠금된 후보자
 ↓
 매칭 점수 순 상위 N명 (default 30)
 ↓
 Search 탭에 카드로 표시 → "추가" 버튼으로 Application 생성
```

### 8.3 AI 문서 생성 (Submission Draft)

`SubmissionDraft` 모델의 6단계 파이프라인. 각 단계는 HTMX 뷰로 분리되어 있으며 중간에 중단·재개가 가능하다.

```
 ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
 │generate  │→ │consultat-│→ │finalize  │→ │masking   │→ │convert   │→ │download  │
 │          │  │ion       │  │          │  │          │  │          │  │          │
 │LLM 초안  │  │컨설턴트  │  │LLM 최종  │  │개인정보  │  │포맷 변환 │  │고객사 제출│
 │JSON 생성 │  │코멘트    │  │정제      │  │마스킹    │  │(Word/PDF)│  │          │
 │          │  │(음성 OK) │  │          │  │(연봉 등) │  │          │  │          │
 └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

완료 시 `Submission.submitted_at`과 연결된 ActionItem의 `status=done`이 세팅되어 Project.phase가 `screening`으로 전환된다.

### 8.4 검색 파이프라인 (후보자 검색)

`SearchSession` / `SearchTurn` 이 대화 컨텍스트를 유지한다.

```
 사용자 입력 (텍스트/음성)
   ↓
 voice_transcribe() ← Whisper API (음성일 때만)
   ↓
 SearchSession 찾기 or 생성
   ↓
 LLM 의도 파싱 → 구조화 필터 + 자연어 잔여 쿼리
   ↓
 ORM 쿼리 실행 (+ 벡터 유사도)
   ↓
 결과 카드 + "다음은?" 팔로업 제안
   ↓
 SearchTurn 레코드 저장
```

### 8.5 알림 파이프라인

```
 이벤트 발생 (액션 완료, 피드백, 승인 요청, 뉴스 업데이트)
   ↓
 NotificationPreference 조회
   ↓
 채널별 분기
  ├─ web:      Notification 모델 저장 → 대시보드/헤더 벨 아이콘
  └─ telegram: TelegramBinding 통해 봇 메시지 전송
```

---

## 9. 자동화와 스케줄 잡

백그라운드 루틴은 Django management command로 구현되어 있으며, cron 또는 Docker Swarm 서비스로 실행된다.

| 커맨드 | 역할 | 주기 |
|---|---|---|
| `projects.check_email_resumes` | Gmail 새 이력서 첨부 폴링 | 5~15분 |
| `projects.fetch_news` | Newsfeed 기사 수집·요약 | 1시간 |
| `projects.check_due_actions` | 마감 임박 ActionItem 알림 발송 | 1시간 |
| `projects.send_reminders` | pending 액션 리마인더(오늘/내일 예정) | 1일 |
| `projects.cleanup_failed_uploads` | 실패한 업로드/임시 파일 정리 | 1일 |
| `projects.process_meetings` | 사전미팅 녹음 파일 STT + 인사이트 추출 | 수동/이벤트 |
| `candidates.generate_embeddings` | 신규/갱신 후보자 벡터 재생성 | 수동/이벤트 |
| `candidates.scan_discrepancies` | 이력서 불일치 스캔 | 수동/주간 |
| `data_extraction.extract` | Drive 이력서 일괄 추출 | 수동/이벤트 |
| `projects.seed_dummy_data` | 더미 시드 (개발 전용) | 수동 |

---

## 10. 일일·주간 업무 시나리오

### 10.1 컨설턴트의 하루

1. **09:00 대시보드 접속**
   - 상단 알림 벨 점 → 어젯밤 도착한 고객사 피드백 2건
   - "Recent Activity" 첫 항목 → 해당 프로젝트 상세로 점프

2. **09:10 어제의 액션 마무리**
   - `receive_doc_feedback` 액션 완료 모달 → 피드백 내용 붙여넣기
   - 제안된 다음 액션 `schedule_interview` 수락 → 일정 조율 ActionItem 생성

3. **09:30 새 이력서 검수**
   - Gmail로 들어온 2건이 이미 파싱되어 "검수 대기" 리스트에 들어와 있음
   - 상세 진입 → AI가 잘못 뽑은 연봉 수정 → Confirm
   - Candidate 생성 완료

4. **10:00 새 JD 도착**
   - Clients → 기존 고객사 → "새 프로젝트"
   - JD 텍스트 붙여넣기 → 저장 → JD 분석 1분 대기
   - Search 탭 → 상위 20명 매칭 → 그중 8명 "프로젝트에 추가"

5. **10:30 후보자 컨택**
   - 추가된 Application 8건 각각 `reach_out` 액션 생성
   - 카카오톡으로 일괄 메시지 → 답장 오면 ActionItem 완료 처리
   - 답장 없는 3건은 내일로 스케줄

6. **13:00 추천 서류 작성**
   - 어제 사전미팅 완료된 후보자 3명 → `prepare_submission` → `submit_to_client`
   - SubmissionDraft 파이프라인 실행: generate → consultation(음성 메모) → finalize → masking → convert → download
   - "Submit" 버튼 → Project phase 자동 screening 전환

7. **16:00 면접**
   - Zoom 후 바로 `interview_round` 액션 완료 → 결과 "2차 통과" → 다음 액션 `await_interview_result`

8. **18:00 내일 계획**
   - 대시보드로 복귀 → 내일의 pending 액션 미리보기 → 퇴근

### 10.2 Owner의 주간 체크

1. **월요일 아침**
   - Approvals 배지 → 주말 사이 등록된 프로젝트 중 충돌 건 3건 승인/거절
   - Team 탭 → 멤버별 Current Projects 건수 + 완료율 확인 → 편중 조정

2. **수요일**
   - References 탭에서 신규 자격증/기업 시드 추가
   - Newsfeed에서 주요 인사 뉴스 1개 공유

3. **금요일**
   - Reports/Performance (Phase 2) → 이번 주 성사/전환율 리뷰
   - 유지보수 대응 요청 있는지 체크

---

## 11. 권한 매트릭스 (요약)

| 기능 | Owner | Consultant | Viewer | Pending |
|---|---|---|---|---|
| 로그인 | ✓ | ✓ | ✓ | ✓ |
| 대시보드 | ✓ | ✓ | ✓ | — |
| 후보자 검색/열람 | ✓ | ✓ | ✓ | — |
| 후보자 등록/수정 | ✓ | ✓ | — | — |
| 프로젝트 CRUD | ✓ | ✓ | — | — |
| 프로젝트 승인 큐 처리 | ✓ | — | — | — |
| 고객사 CRUD | ✓ | ✓ | — | — |
| References 편집 | ✓ | — | — | — |
| Team 관리 (초대/승인) | ✓ | — | — | — |
| 조직 설정 변경 | ✓ | — | — | — |

---

## 12. 이 문서의 위치

- **사업·전략**: [01-business-plan.md](01-business-plan.md)
- **업무 프로세스(이 문서)**: 02-work-process.md
- **코드·모델·배포**: [03-engineering-spec.md](03-engineering-spec.md)

추가 참조:
- UI 디자인 시스템: `docs/design-system.md`
- 목업 화면: `assets/ui-sample/*.html`
- 대시보드 인터랙션 맵: `docs/designs/dashboard-interaction-plan.md`
- Phase × Application 재설계 스펙: `docs/designs/20260414-project-application-redesign/FINAL-SPEC.md`

이전 버전의 Phase 문서들(`docs/plans/headhunting-workflow/P01~P19.md`)과 forge 기록은 `docs/archive/` 로 이동되었으며, 이 마스터 3종이 현재의 단일 진실 소스이다.
