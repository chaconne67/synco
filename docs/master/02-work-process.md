# synco 업무 프로세스

> **마스터 문서 · 단일 진실 소스 · 자립 문서**
> 작성: 2026-04-16 · 범위: 사용자가 synco를 실제로 어떻게 쓰는가 · 데이터·업무 파이프라인·용어·충돌 방지·자동화
> 자매 문서: [01-business-plan.md](01-business-plan.md) · [03-engineering-spec.md](03-engineering-spec.md)

이 문서는 "synco로 하루의 업무가 어떻게 흘러가는가"를 자립적으로 기술한다. 외부 문서를 보지 않아도 신규 컨설턴트·PM·Owner·신규 개발자가 synco의 업무 전체를 이해할 수 있다.

---

## 1. 한눈에

synco는 **중소 서치펌 컨설턴트가 하루 종일 띄워놓고 쓰는 워크벤치**다. 이메일과 드라이브로 쌓이는 이력서를 자동으로 파싱해 DB화하고, JD(Job Description)가 들어오면 자연어 검색으로 후보자를 찾고, 추천 서류를 AI로 생성해 고객사에 제출하고, 면접·오퍼·클로징까지의 모든 **할 일(Action)** 을 한 곳에서 추적한다.

핵심 원칙 세 가지:

1. **synco는 상태 추적 도구가 아니라 할 일 관리 도구다.** 헤드헌터의 하루는 "지금 어느 단계냐"가 아니라 "오늘 뭘 해야 하느냐"로 굴러간다. 그래서 모든 상태는 ActionItem에서 자동으로 파생된다.
2. **컨설턴트는 사람을 만나는 일에 집중한다.** 이력서 파싱·정리·서류 작성·알림·재연락 리마인더는 AI와 자동화가 처리한다.
3. **모든 화면은 1~2 step 직행이다.** 대시보드 클릭 → 바로 해당 업무 화면. 깊이 있는 탐색은 정보 구조가 아니라 검색으로 푼다.

---

## 2. 용어집

이 문서 전반에서 쓰이는 synco의 고유 용어.

| 용어 | 정의 |
|---|---|
| **Organization(조직)** | 서치펌 단위. 멀티테넌시의 최상위 경계. 한 Organization 안의 데이터는 같은 조직원끼리만 공유된다 |
| **Membership(멤버십)** | User와 Organization의 1:1 연결. 역할(role)과 상태(status)를 가진다 |
| **Client(고객사)** | 의뢰 기업. 한 조직은 여러 Client를 둔다. Contract로 계약 이력을 가진다 |
| **Project(프로젝트)** | 고객사가 의뢰한 한 건의 포지션. 마감일(deadline)과 라이프사이클을 가진 작업 컨테이너 |
| **JD (Job Description)** | 고객사가 제공한 포지션 설명. 파일/드라이브/텍스트 3가지 방식으로 입력 |
| **Candidate(후보자)** | 이력서로 DB에 저장된 사람. 한 후보자는 여러 프로젝트에 재사용 가능 |
| **Application(지원/매칭)** | 특정 Project에 특정 Candidate를 붙인 매칭 사실. 상태값을 가지지 않고 ActionItem의 진행으로 파생된다 |
| **ActionItem(액션 아이템, 할 일)** | 헤드헌터 업무의 1급 단위. "김철수에게 내일 오전 카카오톡 연락" 같은 하나의 할 일. 예정·마감·완료·결과를 가진다 |
| **ActionType(액션 종류)** | 액션의 종류 마스터 테이블. 서칭 13종 + 심사 7종 + 범용 3종 = 23종이 기본 시드. 관리자 페이지에서 추가·비활성화 가능 |
| **Phase(단계)** | Project의 거시 상태. `searching`(서칭) / `screening`(심사) 두 가지. **활성 Application 중 하나라도 `submit_to_client` 액션이 완료되면 자동으로 `screening`으로 전환** |
| **Status(진행 상태)** | Project의 수명 상태. `open`(진행중) / `closed`(종료) |
| **Result(결과)** | Project 종료 시의 성패. `success` / `fail` |
| **Drop(드롭)** | Application이 부적격·거절 등으로 빠지는 것. `dropped_at` + `drop_reason`(unfit/candidate_declined/client_rejected/other) + `drop_note` |
| **Hire(입사 확정)** | Application이 성사되어 후보자가 입사 확정된 것. `hired_at` 세팅 → **자동으로 같은 프로젝트의 다른 Application 드롭 + Project 종료(`closed + success`)** |
| **Submission(추천 서류)** | 고객사에 제출한 서류 패키지. `submit_to_client` ActionItem과 1:1 연결 |
| **SubmissionDraft(AI 초안)** | 추천 서류를 AI가 6단계 파이프라인으로 만드는 작업 단위. Submission과 1:1 |
| **Interview(면접)** | 면접 기록. `interview_round` ActionItem과 1:1, 회차·방식·결과·피드백을 가진다 |
| **MeetingRecord(사전미팅 녹음)** | 컨설턴트와 후보자의 사전미팅 녹음·전사·분석 기록. `pre_meeting` ActionItem과 1:1 |
| **Reference Data(참고 마스터)** | 후보자 평가 기준이 되는 정규화 테이블. 대학 티어·기업 프로필·선호 자격증 |
| **Newsfeed(뉴스피드)** | 업계 뉴스를 수집·요약·관련성 매칭해 대시보드에 피드로 표시하는 레이어 |
| **컨택 잠금(Contact Lock)** | 후보자 재컨택 7일 독점권. 한 컨설턴트가 후보자와 컨택 예정을 잡으면 같은 후보자를 다른 컨설턴트가 동일 프로젝트에 동시 접근하지 못하도록 7일간 잠그는 구조 |
| **ProjectApproval(프로젝트 승인)** | 같은 고객사·같은/유사 포지션이 두 컨설턴트 사이에 중복 접수될 때 Owner가 승인/합류/반려를 결정하는 큐 |
| **DB 공유 네트워크** | 서치펌 간 후보자 DB를 공유해 매칭 시 수수료를 분배하는 구조 (로드맵, 현재 v1에 미포함) |

---

## 3. 사용자 롤과 멀티테넌시

synco의 최상위 경계는 **Organization(서치펌)** 이다. 한 Organization 안의 데이터(프로젝트·후보자·고객사)는 같은 조직원끼리만 공유되며, 다른 서치펌은 접근할 수 없다.

한 Organization에 속한 사용자는 `Membership` 1:1 관계로 연결되며 역할과 상태를 가진다.

| 역할 | 권한 |
|------|------|
| **Owner** | 조직 관리, 팀 멤버 초대/승인/해제, 프로젝트 승인 큐 처리, 참고 데이터(대학·기업·자격증) 관리, 수퍼 관리자 영역 접근 |
| **Consultant** | 프로젝트 CRUD, 후보자 DB 전체 이용, 추천·면접·오퍼 진행, 자기 프로젝트에 후보자 추가, 액션 기록, 음성 입력 사용 |
| **Viewer** | 읽기 전용 — 리포트/대시보드 열람 (초기 회원이거나 외부 감사용) |

| 상태 | 의미 |
|------|------|
| `pending` | 초대코드 입력 후 Owner의 승인 대기 중. 대시보드 진입 불가 |
| `active` | 정상 활동 가능 |
| `rejected` | 승인 거절됨. 재신청 가능 |

---

## 4. 온보딩 여정 — 처음 가입부터 첫 프로젝트까지

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Kakao 로그인 │ →  │ 초대코드 입력 │ →  │ Owner 승인   │ →  │ 대시보드 진입│
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
       ↓                                        ↓
  최초 가입이면                            승인 대기 페이지
  /accounts/invite/                        /accounts/pending/
```

### 4.1 시작점: Kakao 로그인
- 진입 URL: `/accounts/login/`
- 카카오 OAuth만 지원. 이메일/비밀번호 가입 없음.
- 카카오에서 돌아오면 `/accounts/kakao/callback/` 에서 `User` 레코드를 만들거나 찾아 세션 로그인.

### 4.2 초대코드 입력
- 신규 유저는 `/accounts/invite/` 로 리다이렉트된다.
- 초대코드는 `InviteCode` 테이블에서 Owner가 발급(만료일·사용 횟수 상한·role 사전 지정).
- 코드를 입력하면 Membership이 생성되며 상태는 `pending`. 코드 `used_count`가 1 증가.

### 4.3 Owner 승인
- Owner의 대시보드에는 "승인 대기" 카운트가 사이드바 배지로 표시된다.
- Owner가 `/org/members/` 에서 pending 멤버를 확인하고 활성화 또는 거절.
- 활성화되면 Membership.status → `active`. 다음 로그인부터 대시보드로 직행.

### 4.4 설정 초기화 (선택)
`/accounts/settings/` 의 4개 탭:
- **프로필**: 이름·회사·업종·지역
- **이메일 모니터링**: Gmail OAuth 연결 → 이력서 첨부 메일 자동 수집용
- **텔레그램 연결**: 웹에서 6자리 코드 발급(5분 유효) → 봇에게 `/start <코드>` → 바인딩 완료
- **알림**: 4종(컨택 결과·추천 피드백·프로젝트 승인·뉴스피드) × 2채널(web/telegram) on/off

### 4.5 첫 프로젝트 등록
- 사이드바 "Projects" → "새 프로젝트" 버튼
- 클라이언트 선택 또는 신규 생성 → JD 입력(파일/드라이브/텍스트) → 저장
- 저장 즉시 JD 분석이 비동기로 시작되고, 완료되면 검색/매칭 탭에서 후보자 매칭 결과가 나타난다.

---

## 5. 메인 네비게이션 지도

사이드바는 9개 메뉴로 구성된다. 모든 전환은 HTMX 기반 (`hx-get` + `hx-target="main"` + `hx-push-url="true"`)이라 페이지 전체 리로드 없이 동작한다.

| 순서 | 메뉴 | 경로 | 역할 | 권한 |
|------|------|------|------|------|
| 1 | Dashboard | `/dashboard/` | 하루의 시작점. KPI, 오늘의 할 일, 팀 성과, 일정, 캘린더 | 전원 |
| 2 | Candidates | `/candidates/` | 후보자 검색/리스트, 상세, 검수 대기열 | 전원 |
| 3 | Projects | `/projects/` | 프로젝트 리스트(칸반/보드/테이블), 상세, 생성/수정/종료 | 전원 |
| 4 | Clients | `/clients/` | 고객사 리스트/상세, 계약 이력 | 전원 |
| 5 | References | `/reference/` | 대학·기업·자격증 마스터 데이터 | Owner |
| 6 | Approvals | `/projects/approvals/` | 프로젝트 충돌 승인 큐 (배지로 건수 표시) | Owner |
| 7 | Newsfeed | `/news/` | 업계 뉴스, 채용·인사 동향 (새 글 있으면 도트) | 전원 |
| 8 | Team | `/org/` | 조직원 관리, 초대코드 발급, 역할 변경 | Owner |
| 9 | Settings | `/accounts/settings/` | 프로필·이메일·텔레그램·알림 | 본인 |

사이드바 외에 글로벌 **FAB(우측 하단 + 버튼)** 으로 "새 프로젝트 / 새 후보자 / 새 고객사 / 컨택 기록"을 어디서나 바로 띄울 수 있다.

---

## 6. 헤드헌팅 전체 워크플로우

```
 ① 영업           ② JD 수신       ③ 서칭         ④ 추천         ⑤ 심사            ⑥ 종료
┌──────────┐    ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐       ┌──────────┐
│클라이언트│    │프로젝트  │   │후보자    │   │클라이언트│   │ 면접 →   │       │ closed + │
│미팅/수주 │───→│생성·JD  │──→│검색·매칭 │──→│서류 제출 │──→│ 오퍼 →   │──────→│ success/ │
│          │    │입력/분석 │   │컨택·조율 │   │          │   │ 입사확정 │       │ fail     │
└──────────┘    └──────────┘   └──────────┘   └──────────┘   └──────────┘       └──────────┘
  Client        phase=searching                                phase=screening
                                                                     ↓
                                                              confirm_hire 액션 완료 →
                                                              Hire signal 자동 발동 →
                                                              Project 종료
```

### 6.1 영업 — 클라이언트 수주
- **Clients** 메뉴에서 고객사 등록 (이름·업종·규모·지역·담당자 JSON·메모).
- 계약 조건은 `Contract` 모델에 시작/종료일·약관·상태(협의중/체결/만료/해지)로 기록.
- 실제 영업 미팅 자체를 synco 안에 기록하는 전용 플로우는 v1에는 없다. 필요 시 Client.notes에 메모.

### 6.2 JD 수신 — 프로젝트 생성
- **Projects → 새 프로젝트** 로 진입. JD 소스 3가지: `upload`(파일), `drive`(Google Drive 파일 ID), `text`(붙여넣기).
- 저장 시 프로젝트는 `phase=searching / status=open / result="" / deadline=<선택>` 로 생성.
- 저장 직후 **JD 분석이 비동기 시작**된다:
  1. 파일 텍스트 추출 (PDF/Word/HWP → UTF-8)
  2. Claude/Gemini가 구조화 JSON 생성: `{position, level, birth_year_from/to, gender, min/max_experience, education, certifications, keywords, industry, role_summary, responsibilities}`
  3. 결과는 `Project.jd_analysis`(AI 추적용)와 `Project.requirements`(검색 필터용) 두 필드에 저장

- **충돌 감지**: 프로젝트 저장 시 같은 Organization 내에 **같은 Client + 유사한 포지션명**이 이미 있으면 `ProjectApproval` 큐로 올라가고 Owner의 판단을 기다린다 (자세한 규칙은 10장).

### 6.3 서칭 — 후보자 매칭
- **프로젝트 상세 → Search/Matching 탭**
- JD 분석 결과의 `requirements` 가 자동으로 검색 필터에 세팅된다 (`birth_year_from/to`, `min/max_experience_years`, `education.fields`, `certifications.preferred`, `keywords`).
- 서버는 `CandidateEmbedding`(pgvector)과의 코사인 유사도 + 구조 필터를 조합해 상위 N명(기본 30)을 반환한다.
- Consultant는 "프로젝트에 후보자 추가" 버튼으로 매칭 리스트에서 `Application` 레코드를 생성한다.
- Application이 만들어지면 `current_state = "matched"` (ActionItem 0개 상태).

### 6.4 컨택 — ActionItem 생성·완료
매칭된 후보자에게는 "할 일"이 줄줄이 달린다. Consultant는 각 액션을 생성·완료하며 업무를 이어간다.

- 액션 종류는 `ActionType` 테이블 (23종 seed, 7장에서 전체 열거).
- 대표적 서칭 액션: `search_db`(DB 검색) · `reach_out`(연락) · `share_jd`(JD 공유) · `receive_resume`(이력서 수령) · `pre_meeting`(사전미팅) · `submit_to_client`(클라이언트 제출).
- 완료(`status=done`)할 때 `result` 텍스트와 `completed_at`이 기록되고, `ActionType.suggests_next`에 따라 **다음 액션 제안 팝업**이 뜬다. 버튼 한 번으로 다음 ActionItem을 생성할 수 있다(자동 체인).

### 6.5 추천 서류 (`submit_to_client`)
- 서류 제출은 `Submission` 모델이 담당한다. `submit_to_client` ActionItem을 완료하면 1:1로 Submission 레코드가 묶인다.
- Submission은 AI 초안 파이프라인 `SubmissionDraft`와 1:1. **6단계 파이프라인** (자세한 내용은 13장):
  1. **Generate** — AI가 이력서+JD를 읽고 초안 JSON 생성
  2. **Consultation** — 컨설턴트가 음성/텍스트로 코멘트 추가
  3. **Finalize** — AI가 최종 버전을 정제
  4. **Masking** — 개인정보(연락처·연봉·회사명 등) 선택적 가림
  5. **Convert** — Word/PDF/HWP + 국문/국영문/영문 언어 선택
  6. **Download** — 파일 다운로드 → `submit_to_client` 완료 처리
- 이 제출 액션이 완료되면 Project의 `phase`가 **자동으로 `screening`** 으로 전환된다 (OR 규칙: 활성 Application이 하나라도 `submit_to_client` 완료했으면 screening).

### 6.6 심사 — 면접·오퍼
- 고객사 피드백 수신 → `receive_doc_feedback` 액션 완료 → 피드백 내용을 `result`에 기록
- 면접 잡힘 → `schedule_interview` → `interview_round` 액션. 완료 시 `Interview` 레코드 1:1 생성 (round·type·result·scheduled_at·feedback)
- 합격 → `confirm_hire` 액션을 완료하면 **Hire signal이 자동 발동**해 (자세한 내용은 9장):
  1. `Application.hired_at = now()`
  2. 같은 프로젝트의 나머지 활성 Application 모두 자동 드롭 (drop_reason=`other`, note: "입사자 확정으로 포지션 마감")
  3. `Project.status = closed / result = success / closed_at = now()`

### 6.7 종료 처리
- **자동 종료**: 위 `confirm_hire` Hire signal.
- **수동 종료**: 고객사가 철회하거나 기한 내 적임자를 못 찾을 때. 프로젝트 상세에서 "종료" 버튼 → `result=fail` + 사유/메모 입력.
- 종료 시점에 `closed_at` 타임스탬프와 `result`가 기록되며, 이후 대시보드/리포트의 집계에 쓰인다.

---

## 7. Phase × Application × ActionItem — 3층 모델

synco의 상태 모델은 **3개의 층**이 서로 영향을 주고받는다. 이해해두면 대시보드가 왜 그런 식으로 동작하는지 쉽게 읽힌다.

```
 ┌────────────────────────── Project ──────────────────────────┐
 │  phase:  searching / screening     (자동 파생)              │
 │  status: open / closed             (수동 또는 confirm_hire) │
 │  result: success / fail / ""       (종료 시 세팅)            │
 │  deadline: Date                    (클라이언트 마감)         │
 │                                                              │
 │  ├── Application(A) ──────────────────────────────────┐     │
 │  │    hired_at / dropped_at + drop_reason              │    │
 │  │    current_state = 최신 완료 ActionItem에서 파생   │     │
 │  │    ├── ActionItem #1 [search_db · done]             │    │
 │  │    ├── ActionItem #2 [reach_out · done]             │    │
 │  │    ├── ActionItem #3 [receive_resume · done]        │    │
 │  │    ├── ActionItem #4 [submit_to_client · done] ◀── phase 전환 트리거
 │  │    └── ActionItem #5 [interview_round · pending]    │    │
 │  └──────────────────────────────────────────────────────┘    │
 │  ├── Application(B) … dropped                                │
 │  └── Application(C) … matched (ActionItem 0개)                │
 └──────────────────────────────────────────────────────────────┘
```

### 7.1 Project.phase — "서칭 / 심사" 자동 파생

**규칙 (OR)**:
- 활성 Application (dropped_at=NULL AND hired_at=NULL) 중 하나라도 `submit_to_client` 코드의 ActionItem이 `done`이면 → `screening`
- 아니면 → `searching`
- `closed` 프로젝트는 마지막 phase를 유지 (변경 안 함)

**재계산 트리거**:
- ActionItem post_save/post_delete signal
- Application post_save/post_delete signal

### 7.2 Application.current_state — 파생 속성

DB에 저장되지 않고, 렌더링할 때 계산된다.

```
if dropped_at is not None:  return "dropped"
if hired_at is not None:    return "hired"

latest_done = 이 Application의 최신 완료 ActionItem (completed_at desc)
if latest_done is None:     return "matched"

return STATE_FROM_ACTION_TYPE.get(latest_done.code, "in_progress")
```

**STATE_FROM_ACTION_TYPE 매핑 (UI 표시용)**:
- `pre_meeting → pre_met`
- `submit_to_client → submitted`
- `interview_round → interviewing`
- `confirm_hire → hired`
- 그 외 → `in_progress`

### 7.3 ActionItem — 1급 업무 단위

- `application`에 FK로 여러 개 달림
- `action_type`에 FK (PROTECT; 보호된 4개 타입은 삭제 불가: `pre_meeting`, `submit_to_client`, `interview_round`, `confirm_hire`)
- `status`: `pending` / `done` / `skipped` / `cancelled`
- `scheduled_at`, `due_at`, `completed_at`, `channel`, `result`, `note`, `assigned_to`
- `parent_action` (self FK) — 자동 체인 추적: "이 액션은 어떤 액션의 후속인가"
- 완료 시 다음 액션 후보를 `ActionType.suggests_next` 배열에서 뽑아 사용자에게 제안

### 7.4 드롭과 Hire

**Application Drop (`dropped_at` 세팅)**:
- `drop_reason`: `unfit`(부적합) / `candidate_declined`(후보자 거절/포기) / `client_rejected`(클라이언트 탈락) / `other`(기타)
- `drop_note` 자유 메모
- 해당 Application의 pending 액션은 모두 `cancelled` 처리
- 복구 가능 (`dropped_at=NULL` 로 되돌림)

**Application Hire (`hired_at` 세팅)** — 9.3장의 signal이 자동 발동:
1. `Application.hired_at = now()`
2. 같은 프로젝트의 **나머지 활성 Application 모두 자동 드롭** (`drop_reason=other`, note: "입사자({candidate}) 확정으로 포지션 마감")
3. `Project.closed_at = now(), status=closed, result=success, note += "입사 확정"`
4. `compute_project_phase`는 closed라 변경되지 않음

**엣지 케이스**: 이론상 한 후보자가 여러 프로젝트에서 `hired_at`이 찍힐 수 있다(현실에선 드물다). v1에서는 차단하지 않고 `duplicate hire detected` 로그만 남긴다. Application 유니크 제약은 `(project, candidate)` 와 `(project WHERE hired_at IS NOT NULL)` 두 개이므로, **프로젝트당 성사 1명**이 DB 수준에서 보장된다.

---

## 8. ActionType — 23종 시드

초기 시드 데이터(data migration으로 주입됨). Owner는 관리자 페이지에서 추가·비활성화 가능. 보호된(`is_protected=True`) 4종은 삭제 불가.

### 8.1 서칭 국면 (13종)

| code | 한국어 라벨 | output | 보호 |
|---|---|---|---|
| `search_db` | DB 후보자 검색 | — | — |
| `search_external` | 외부 소스 탐색 | — | — |
| `reach_out` | 후보자 연락 | — | — |
| `re_reach_out` | 재연락 | — | — |
| `await_reply` | 답장 대기 | — | — |
| `share_jd` | JD 공유 | — | — |
| `receive_resume` | 이력서 수령 | — | — |
| `convert_resume` | 내부 양식 변환 | — | — |
| `schedule_pre_meet` | 사전미팅 일정 조율 | — | — |
| **`pre_meeting`** | **사전미팅 실시** | **MeetingRecord** | **✓** |
| `prepare_submission` | 제출 이력서 작성 | — | — |
| `submit_to_pm` | 내부 PM 1차 검토 | — | — |
| **`submit_to_client`** | **클라이언트 제출** | **Submission** | **✓** |

### 8.2 심사 국면 (7종)

| code | 한국어 라벨 | output | 보호 |
|---|---|---|---|
| `await_doc_review` | 서류 심사 대기 | — | — |
| `receive_doc_feedback` | 서류 피드백 수령 | — | — |
| `schedule_interview` | 면접 일정 조율 | — | — |
| **`interview_round`** | **면접 실시** | **Interview** | **✓** |
| `await_interview_result` | 면접 결과 대기 | — | — |
| **`confirm_hire`** | **입사 확정** | — | **✓** |
| `await_onboarding` | 입사일 대기 | — | — |

### 8.3 범용 (3종)

| code | 한국어 라벨 | 용도 |
|---|---|---|
| `follow_up` | 팔로업 | 모든 국면에서 추가 후속 |
| `escalate_to_boss` | 사장님 에스컬레이션 | 판단 어려움을 Owner에게 넘김 |
| `note` | 단순 메모 | 결과·맥락 기록 |

### 8.4 자동 체인 제안 (suggests_next)

액션 완료 시 UI가 컨설턴트에게 띄우는 "다음 액션 후보". 버튼 한 번으로 새 ActionItem 생성 가능.

| 완료된 액션 | 제안되는 다음 액션 |
|---|---|
| `reach_out` | `await_reply`, `schedule_pre_meet` |
| `await_reply` | `re_reach_out`, `schedule_pre_meet` |
| `schedule_pre_meet` | `pre_meeting` |
| `pre_meeting` | `prepare_submission`, `follow_up` |
| `prepare_submission` | `submit_to_client` |
| `submit_to_client` | `await_doc_review` |
| `await_doc_review` | `receive_doc_feedback` |
| `receive_doc_feedback` | `schedule_interview`, `follow_up` |
| `schedule_interview` | `interview_round` |
| `interview_round` | `await_interview_result`, `interview_round` (2차) |
| `await_interview_result` | `confirm_hire`, `follow_up` |
| `confirm_hire` | `await_onboarding` |

---

## 9. 자동 파생과 시스템 규칙

### 9.1 Next Action 자동 제안 (8.4와 중첩, 다른 맥락)

대시보드의 "오늘의 액션" 섹션과 프로젝트 개요 탭은 컨설턴트에게 **현재 상태에 근거한 다음 해야 할 일**을 제안한다. 단순 ActionItem 리스트 외에 시스템이 추론하는 후속도 포함:

- 컨택 완료(관심) → "제출 서류 AI 초안 생성 필요"
- 서류 제출 후 5일 경과 → "고객사 팔로업 필요"
- 면접 2차 합격 후 → "오퍼 준비"
- 프로젝트 등록 후 공지 미작성 → "공지 초안 생성"

이는 모두 `AutoAction` 모델로 저장되며, 컨설턴트가 "승인" 버튼을 누르면 실제 ActionItem으로 전환된다 (자동 생성은 하지 않음 — 사용자 확인 필수).

### 9.2 Overdue / Due Soon

ActionItem은 DB 상태가 아닌 파생 속성으로 긴급도를 계산:

- **Overdue**: `status=pending AND due_at < now()`
- **Due soon(3일 내)**: `status=pending AND now() <= due_at <= now()+3d`

대시보드의 "🚨 오늘의 액션" 블록은 위 쿼리들을 유니온해 긴급도 스코어링 후 정렬한다.

### 9.3 Hire Signal — 자동 종료 플로우

```python
# Application.hired_at 이 세팅될 때 post_save signal 발동
if instance.hired_at and not project.closed_at:
    # 1. 프로젝트 종료
    project.closed_at = now()
    project.status = "closed"
    project.result = "success"
    project.note += "\n[자동] {candidate} 입사 확정으로 종료"
    project.save()

    # 2. 나머지 활성 Application 전원 드롭
    for other in project.applications.active().exclude(id=instance.id):
        other.dropped_at = now()
        other.drop_reason = "other"
        other.drop_note = "입사자({candidate}) 확정으로 포지션 마감"
        other.save()
```

### 9.4 Project 종료 시 상태 동기화

```
closed_at 세팅 ↔ status=closed
closed_at NULL ↔ status=open (+ result="" 초기화)
```

CheckConstraints가 DB 레벨에서 이 관계를 강제한다:
- `open → closed_at IS NULL`
- `open → result = ""`
- `result != "" → status = closed`

### 9.5 자동 알림 트리거

다음 이벤트가 발생하면 `Notification` 레코드가 생성되고, `NotificationPreference`에 따라 web/telegram 채널로 발송된다.

- 컨택 결과 입력 → 추천 초안 생성 제안
- 서류 제출 3일 경과 → 팔로업 리마인더
- 면접 전날 → 면접 리마인더
- 컨택 잠금 만료 1일 전 → 재컨택 알림
- 프로젝트 충돌 감지 → Owner 승인 요청 알림
- 새 뉴스 기사 관련성 ≥ 0.7 → 대시보드 피드 + 텔레그램

주기 잡은 `check_due_actions`, `send_reminders`, `check_email_resumes`, `fetch_news` 등의 management command로 실행된다.

---

## 10. 충돌 방지 시스템 (2층 구조)

synco의 가장 중요한 비즈니스 규칙 중 하나. "같은 후보자에게 두 컨설턴트가 동시 접근"과 "같은 고객사 포지션을 두 컨설턴트가 중복 수주"를 **다른 층에서** 막는다.

### 10.1 프로젝트 등록 충돌 — ProjectApproval

프리랜서 컨설턴트들은 서로의 의뢰를 모르는 채 같은 고객사에 접근할 수 있다. synco는 프로젝트 저장 시 충돌을 감지해 Owner에게 판단을 넘긴다.

**감지 규칙**:
- **High conflict (유사도 ≥ 0.7)**: 같은 Client + 포지션 키워드(직급/부서/직무) 매칭 → "같은 프로젝트일 가능성 높음"
- **Medium conflict (유사도 < 0.7)**: 같은 Client + 다른 포지션 → "참고 정보"
- **No conflict**: 다른 Client 또는 아예 유사 없음

**ProjectApproval 상태**: `pending`(대기) / `approved`(신규 프로젝트로 승인) / `joined`(기존 프로젝트에 합류) / `rejected`(반려)

**Owner 판단**:
- **승인(approved)**: 두 프로젝트를 별개로 취급
- **합류(joined)**: 기존 프로젝트에 해당 컨설턴트를 `assigned_consultants`로 추가
- **반려(rejected)**: 신규 프로젝트 저장 취소

**가시성 정책**: 평소엔 자기 프로젝트만 보이지만, 충돌이 감지된 순간 상대방 프로젝트의 제한된 정보(담당자, 상태)가 노출된다.

### 10.2 후보자 컨택 잠금 — Contact Lock

한 컨설턴트가 후보자에게 컨택 예정을 잡으면 **7일간 그 후보자에 대한 독점권**을 가진다. 다른 컨설턴트가 같은 프로젝트에서 같은 후보자에 접근하지 못하게 한다.

**적용 범위**:
- 같은 프로젝트 + 같은 후보자 → **차단** (중복 컨택 금지)
- 다른 프로젝트 + 같은 후보자 → **허용** (다른 포지션이므로), 이전 컨택 이력 UI에 표시
- 컨택 예정 등록 시 7일 타이머 시작 → 실제 컨택 결과 입력까지 독점

**자동 해제 조건**:
- 7일 경과 → 자동 해제
- 컨택 결과 입력(성공/실패) → 즉시 해제
- Owner 수동 해제 (예: 휴가·장기 부재)

**현재 구현 상태**: v1의 ActionItem 모델은 `scheduled_at`으로 예정 시점을 가지지만 잠금 독립 필드(`locked_until`)는 아직 없다. 잠금 로직은 P16/P18 확장에서 도입 예정.

---

## 11. 화면별 업무 흐름

### 11.1 Dashboard — 하루의 시작

**레이아웃 기준**: `assets/ui-sample/dashboard.html` (디자인 단일 진실 소스)

**구성 블록**:

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

**위젯별 인터랙션 지도** — 모든 카드 요소는 "클릭 → 해당 업무 화면 1~2 step 직행":

| 위젯 | 클릭 타겟 | 형식 |
|---|---|---|
| **Monthly Success (24)** | `/projects/?status=closed&result=success&period=month` | 페이지 |
| Monthly Success · In Progress 12 | `/projects/?filter=active` | 페이지 |
| Monthly Success · Rate 82% | `/reports/performance/` | 페이지 |
| **Estimated Revenue** | `/reports/revenue/` | 페이지 |
| Revenue · Target 76% | 수익 목표 설정 모달 | 모달 |
| **Project Status · 진행 42** | `/projects/?phase=searching,screening&status=open` | 페이지 |
| Project Status · 심사 18 | `/projects/?phase=screening` | 페이지 |
| Project Status · 완료 114 | `/projects/?status=closed` | 페이지 |
| **Team — 카드 전체** | `/org/` | 페이지 (Owner) |
| Team 멤버 행 | 멤버 상세 drawer 또는 `/projects/?owner={user_id}` | 모달/페이지 |
| Team — "VIEW ALL →" | `/org/` | 페이지 |
| **Recent Activity** 카드 헤더 | 전체 활동 로그 페이지 | 페이지 |
| Activity — "Candidate placed" | `/projects/{id}#offer` | 페이지 |
| Activity — "New candidate" | `/candidates/{id}` | 페이지 |
| Activity — "Meeting note" | `/clients/{id}#notes` | 페이지 |
| Activity — "Deadline near" | `/projects/{id}` + 경고 배너 | 페이지 |
| **Weekly Schedule 카드** | 일정 상세 모달 | 모달 |
| Weekly — 카드 `···` | 편집·취소·일정 변경 메뉴 | 모달 |
| **Monthly Schedule 날짜 셀** | 당일 이벤트 drawer | 모달 |
| 빈 날짜 셀 | 이벤트 추가 모달 | 모달 |
| 이벤트 pill | 이벤트 상세 모달 | 모달 |
| **알림 벨** | 알림 drawer | 모달 |
| **프로필 SP** | 프로필/설정 drawer | 모달 |
| **FAB +** | 글로벌 "새로 만들기" 메뉴 | 모달 |
| FAB → 새 프로젝트 | `/projects/new/` 모달 | 모달 |
| FAB → 새 후보자 | 이력서 업로드 + AI 추출 | 모달 |
| FAB → 새 고객사 | 고객사 폼 | 모달 |
| FAB → 컨택 기록 | 프로젝트→후보자 선택 → 액션 기록 | 모달 |

**핵심 블록 — 🚨 오늘의 액션** (P13 기획의 대시보드 핵심):

컨설턴트의 하루는 이 리스트로 시작된다. 5종 쿼리의 유니온 + 긴급도 자동 스코어링으로 상위 8~12개 노출.

| 항목 | 조건 | 긴급도 |
|---|---|---|
| 재컨택 예정 오늘·과거 | `ActionItem.scheduled_at ≤ today (re_reach_out/reach_out)` | 🔴 |
| 면접 임박 | `Interview.scheduled_at` 오늘·내일 | 🟡 |
| 서류 검토 대기 2일+ | `Submission.submitted_at ≤ today-2 AND 피드백 없음` | 🟡 |
| 컨택 잠금 만료 임박 | `Contact Lock locked_until ≤ today+1` | 🔴 |
| Offer 회신 대기 | `confirm_hire pending AND 3일 경과` | 🟡 |

**내 파이프라인 Funnel**: `NEW → SEARCHING → RECOMMENDING → INTERVIEWING → NEGOTIATING → CLOSED_SUCCESS` 단계별 Project 카운트. 클릭 시 해당 단계 필터의 `/projects/` 로 이동.

**Owner 전용 추가 블록**:
- **승인 요청 큐**: `ProjectApproval.status=pending` 카드. 인라인 승인/반려 버튼
- **팀 KPI**: 컨택 → 추천 전환율, 추천 → 면접 전환율, 평균 클로즈 기간(일), 월 목표 대비 달성률

### 11.2 Projects — 의뢰 수주부터 클로징까지

**멀티뷰 리스트**: 같은 데이터를 4가지로 전환 가능 (P04 기획):

| 뷰 | 구성 | 용도 |
|---|---|---|
| **Kanban** | phase별 컬럼(검색중/심사중/종료) | 전체 흐름 한눈에 |
| **Action-centric list** | 긴급도 자동 분류 🔴/🟡/🟢 | 오늘 뭘 해야 하는지 |
| **Spreadsheet** | 정렬 + 카운트 | 엑셀 사용자 적응 |
| **Calendar** | 면접일·재컨택일 시각화 | 일정 중심 관리 |

드래그 앤 드롭은 **비활성화** — phase는 액션에서 자동 파생되므로 사용자가 직접 바꿀 수 없다.

**상세 탭 구조**:

| 탭 | 역할 |
|---|---|
| Overview | KPI, 프로젝트 요약, 퍼널 시각화(컨택→추천→면접→오퍼), 담당자, 최근 액션 타임라인, 자동 공지 초안 |
| Search | JD 분석 기반 매칭 후보자 리스트 + "프로젝트에 추가" 버튼, 컨택 상태 표시(⚠ 컨택됨/🔒 예정) |
| Applications | 매칭된 후보자들의 카드 뷰. 각 카드에 pending/done 액션 표시 |
| Submissions | 추천 서류 목록. SubmissionDraft 6단계 진입점 |
| Interviews | 면접 일정·결과 |
| Posting | JD 게시용 공지 AI 생성/편집/다운로드, 채용 사이트별 등록 추적(잡코리아·사람인·인크루트·LinkedIn·원티드·캐치) |
| Context | 프로젝트 메모·업무 연속성 스냅샷 |
| Auto Actions | AI 제안 후속 액션 리스트 (승인 후 ActionItem으로 전환) |

**주요 동작**:
- 새 프로젝트 → 클라이언트 선택 → JD 입력 → 저장 → (자동) JD 분석 → 매칭 + 공지 초안 자동 생성 + 충돌 체크
- 후보자 추가 → Application 생성 + 시스템이 `reach_out` ActionItem 제안
- 액션 완료(HTMX 모달) → 결과/메모 입력 → 다음 액션 제안 팝업 → 체인
- 프로젝트 종료 → `closed_at`/`result`/`note` 기록
- **충돌 감지**: 저장 시 10.1장의 ProjectApproval 큐로 올라감

### 11.3 Candidates — 후보자 DB

**리스트 뷰**: 카테고리 탭 + 필터 + 자연어 검색

**검색 방식**:
- **텍스트 검색**: 이름·회사·학교 등 ORM 필터
- **자연어 검색**: "인서울 출신 AICPA 보유 남성, 경력 10년 이상" → LLM이 구조화 필터로 변환 → ORM 쿼리
- **벡터 검색**: `CandidateEmbedding`(pgvector) 코사인 유사도. JD 매칭에 주로 사용
- **SearchSession/SearchTurn**: 대화 컨텍스트 유지, 팔로업 질문 가능

**상세 화면**:
- 프로필 헤더 (이름·현 회사·포지션·경력 연수·상태)
- 학력(`Education`), 경력(`Career`), 자격증(`Certification`), 어학(`LanguageSkill`)
- 이력서 원본(`Resume`, 여러 버전 가능) + 추출 로그(`ExtractionLog`) + 신뢰도 태그
- **Discrepancy 리포트** (`DiscrepancyReport`): 이력서 위조/변조 탐지 결과 (RED/YELLOW/BLUE)
- **Validation 진단** (`ValidationDiagnosis`): 검수 항목별 AI 판정
- 댓글(`CandidateComment`)
- **이 후보자의 모든 Application 타임라인** (Level 3 네비게이션)

**검수 플로우** (`/candidates/review/`):
- AI가 이력서에서 뽑아낸 초안의 신뢰도가 낮은 항목만 모아서 보여준다
- Consultant가 항목별로 **Confirm** / **Reject** / **Edit**
- 신뢰도 태그: 원본 확인(`source`) / AI 추론(`inferred`) / AI 생성(`generated`)

### 11.4 Clients — 고객사 관리

- 리스트: 이름·업종·규모·지역·최근 프로젝트 수
- 상세: 기본 정보 + 계약 이력(`Contract`) + 담당자 JSON + 메모
- 해당 고객사의 모든 프로젝트 이력, 성공/실패율

### 11.5 References — 참고 마스터 데이터 (Owner)

후보자 평가 기준이 되는 3개 정규화 테이블:

| 모델 | 내용 | 초기 규모 |
|---|---|---|
| `UniversityTier` | SKY / SSG(서성한) / JKOS(중경외시) / KDH(건동홍) / INSEOUL / SCIENCE_ELITE / REGIONAL / 해외(최상위/상위/우수) | ~200+ 대학 |
| `CompanyProfile` | 대기업/중견/중소/외국계/스타트업, KOSPI/KOSDAQ/비상장, 매출·인원 범위, 별칭 | 초기 KOSPI/KOSDAQ ~2,500사 + 점진 확장 |
| `PreferredCert` | 카테고리 11종(회계·법률·IT 등), 레벨(상/중/하), 별칭 | ~800종 |

Owner만 편집 가능. Consultant는 읽기만. 초기 데이터는 `load_reference_data` management command로 시드. CSV 가져오기/내보내기 지원.

### 11.6 Newsfeed — 업계 동향

- Owner가 `NewsSource` 등록 (RSS/블로그 URL + 타입 + 카테고리)
- `fetch_news` management command가 매일 수집 → `NewsArticle` 저장 → Gemini 요약 (2~3 문장 + 태그)
- **관련성 매칭**: 내 프로젝트의 고객사명/업종/requirements와 비교해 `NewsArticleRelevance` 점수 생성
  - 회사명 직접 매칭: 0.9
  - 업종 일치: 0.6
  - 키워드 교집합: 0.5~0.8
- 관련도 ≥ 0.5 기사는 대시보드 상단 고정, 매일 아침 텔레그램 요약 발송
- 사이드바에 "안 읽은 기사 있음" 도트

### 11.7 Team — 조직원 관리 (Owner)

- 멤버 리스트 (role · status · 활동량)
- 초대코드 발급/폐기 (`InviteCode`)
- pending 멤버 승인/거절
- Organization 정보 수정 (이름·플랜·로고·DB 공유 여부)

### 11.8 Settings — 개인 설정

4개 탭: 프로필 / 이메일(Gmail OAuth) / 텔레그램(바인딩) / 알림(4종×2채널 on/off).

---

## 12. 후보자 입력 경로 (5가지)

Candidate를 DB에 생성하는 5가지 경로. 모두 결국 같은 `Candidate` 레코드로 수렴한다.

| 경로 | 설명 | 비중 |
|---|---|---|
| **① 기존 DB 검색·선택** ⭐ | Candidates 메뉴에서 조건 검색 후 선택 → Application 생성 | 가장 빈번 |
| ② 파일 업로드 | 프로젝트 Search 탭에서 이력서 드래그앤드롭 → 파서가 Candidate 생성 → Application | 수동 추가 |
| ③ Drive 폴더 스캔 | 공유 폴더에 드롭 → `data_extraction` 앱의 Gemini Batch가 일괄 스캔 | 대량 인입 |
| ④ 이메일 수신 | Gmail 첨부 자동 감지 → 자동 파싱 → 프로젝트 자동 매칭 (REF 키워드) | 수동 개입 최소 |
| ⑤ 음성 입력 | "홍길동을 삼성전자 프로젝트에 추가해줘" → 보이스 에이전트가 DB 검색, 없으면 대화형 수집 | 모바일 친화 |
| ⑥ Chrome Extension | LinkedIn/잡코리아/사람인 프로필 페이지에서 원클릭 저장 (로드맵) | 소싱 자동화 |

입력 경로가 달라도 **Application 생성은 항상 동일한 행위**: 기존 Candidate를 특정 Project에 "붙이는" 한 번의 동작. 1번은 기존 후보자 재사용, 2~6번은 새 Candidate를 만들면서 같은 흐름으로 이어진다.

---

## 13. 데이터 파이프라인

### 13.1 이력서 파싱 파이프라인

```
 ┌───────────┐      ┌───────────┐     ┌──────────┐    ┌───────────┐
 │ Gmail     │      │ Drive     │     │ 수동     │    │ Chrome    │
 │ (첨부)    │      │ (공유 폴더)│     │ 업로드   │    │ Extension │
 └─────┬─────┘      └─────┬─────┘     └────┬─────┘    └─────┬─────┘
       │                  │                │                │
       ▼                  ▼                ▼                ▼
 check_email_resumes  data_extraction  resume_upload   chrome_ext hook
 (cron)               extract (batch)  (view 직접)     (POST API)
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
- **Gemini Batch API** 사용 → 한 번에 수백~수천 건 비동기 처리. 결과는 `response_json`에 저장
- **파일명 자동 생성 규칙**: `{이름}.{YY}.{현회사}.{전회사}.{대학교}` (`posting_file_name` 규칙)
- **신뢰도 3단계 표시**: 원본 확인(`source`) / AI 추론(`inferred`) / AI 생성(`generated`)
- **중복 검출**: email/phone 기준으로만 자동 병합. 이름 기반 병합은 금지(동명이인 리스크)

### 13.2 JD 분석 + 매칭 엔진

```
JD 입력 (파일/drive/text)
  ↓
텍스트 추출 (Python)
  ↓
Gemini structured output → JSON
  {position, level, birth_year_from/to, gender,
   min/max_experience_years, education.fields,
   certifications.preferred, keywords, industry,
   role_summary, responsibilities}
  ↓
Project.jd_analysis (추적용) + Project.requirements (필터용)
  ↓
매칭 시:
  1. 구조 필터 (경력연수, 학력 tier, 현재 회사 크기, 자격증)
  2. 벡터 유사도 (JD 임베딩 ↔ CandidateEmbedding 코사인)
  3. 제외: 이미 Application 있는 후보자, 컨택 잠금 중인 후보자
  ↓
적합도 3단계 스코어링 (높음/보통/낮음)
  ↓
상위 N명 (기본 30)
  ↓
Search 탭에 카드로 표시 → "추가" → Application 생성
```

**Gap 분석**: 각 후보자별로 JD 충족/미충족 근거를 리포트로 제시. 컨설턴트가 "왜 이 사람을 추천하는가"를 클라이언트에 설명할 때 사용.

### 13.3 AI 추천 서류 생성 (SubmissionDraft 6단계)

```
 ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
 │generate  │→ │consultat-│→ │finalize  │→ │masking   │→ │convert   │→ │download  │
 │          │  │ion       │  │          │  │          │  │          │  │          │
 │AI 초안   │  │컨설턴트  │  │AI 최종   │  │개인정보  │  │포맷 변환 │  │고객사 제출│
 │JSON 생성 │  │코멘트    │  │정제      │  │마스킹    │  │(Word/PDF)│  │          │
 │          │  │(음성 OK) │  │          │  │(연봉 등) │  │          │  │          │
 └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

**단계별 상세**:

1. **Generate**: Candidate의 이력서 구조 데이터 + Project의 JD → 엑스다임 양식(국문/국영문/영문/고객사 커스텀)에 맞게 초안 JSON 자동 매핑. 서식 통일·오탈자 교정·경력 기간 자동 계산·회사 소개 자동 생성(`CompanyProfile` 활용).
2. **Consultation**: 컨설턴트가 직접 입력 또는 녹음 파일 업로드 → Whisper STT → AI가 초안에 녹임.
3. **Finalize**: 초안 + 상담 내용을 병합해 완성본 미리보기. `final_content_json` 저장.
4. **Masking**: `masking_config`에 따라 연봉·생년월일·연락처·회사명 등 선택적 가림. 고객사 제출용 버전.
5. **Convert**: 포맷(Word/PDF/HWP) + 언어(ko/en) 선택 → 파일 생성.
6. **Download**: 파일 다운로드 + `submit_to_client` ActionItem `status=done` 자동 세팅 → Phase 자동 전환.

상태 필드: `generated` → `consultation_added` → `finalized` → `masked` → `converted` → `downloaded`

### 13.4 검색 파이프라인

`SearchSession` / `SearchTurn`이 대화 컨텍스트를 유지한다.

```
 사용자 입력 (텍스트/음성)
   ↓
 voice_transcribe() ← Whisper API (음성일 때만)
   ↓
 SearchSession 찾기 or 생성
   ↓
 Claude 의도 파싱 → 구조화 필터 + 자연어 잔여 쿼리
   ↓
 ORM 쿼리 + 벡터 유사도
   ↓
 결과 카드 + "다음은?" 팔로업 제안
   ↓
 SearchTurn 레코드 저장
```

### 13.5 알림 파이프라인

```
 이벤트 발생 (액션 완료, 피드백, 승인 요청, 뉴스 업데이트, due 임박)
   ↓
 NotificationPreference 조회
   ↓
 채널별 분기
  ├─ web:      Notification 모델 저장 → 대시보드/헤더 벨 아이콘
  └─ telegram: TelegramBinding 통해 봇 메시지 전송 (Inline Keyboard 포함 가능)
```

---

## 14. 크로스커팅 채널 — 음성·텔레그램·업무 연속성

### 14.1 음성 에이전트 (P14 기획, v1 부분 구현)

모든 화면 우하단의 플로팅 마이크 버튼 → Whisper 딕테이션 → Gemini 의도 파싱 → 의도별 액션 실행.

**의도 11종**:
1. `project_create` — 프로젝트 생성
2. `contact_record` — 컨택 기록
3. `contact_reserve` — 컨택 예정 등록(잠금 발동)
4. `submission_create` — 추천 서류 생성 시작
5. `interview_schedule` — 면접 일정 등록
6. `offer_create` — 오퍼 내용 기록
7. `status_query` — "삼성 건 어디까지 갔어?"
8. `todo_query` — "오늘 할 일"
9. `search_candidate` — 자연어 검색
10. `navigate` — 화면 이동
11. `meeting_upload` — 사전미팅 녹음 업로드

**컨텍스트 인식**: 현재 화면에서 `data-voice-context` 속성을 읽는다. 프로젝트 상세에서 "전화했어"라고 말하면 해당 프로젝트의 현재 선택된 후보자에 대한 컨택 기록으로 해석.

**멀티턴**: 부족 정보 자동 질문 → 사용자 답변 → 재파싱 → 반복.

**사전미팅 녹음 인사이트**: 녹음 파일 업로드 → Whisper STT → Gemini 구조화 → 8개 항목 인사이트 리포트(핵심 요약·이직 동기·희망 조건·강점·커뮤니케이션·관심 포지션·레드플래그·후속 조치) → 컨설턴트 확인 후 `MeetingRecord`에 반영.

### 14.2 텔레그램 Bot (P15 기획)

`TelegramBinding`으로 유저와 chat_id가 1:1 연결된다. 웹앱에서 6자리 코드 발급 → `/start <코드>` → 바인딩.

**Inline Keyboard 업무 처리**:
- **프로젝트 승인**: 큐 알림과 함께 [승인][합류][메시지][반려] 4개 버튼. 다단계 선택 진행
- **컨택 기록**: 리마인더에서 [전화][카톡][이메일] → 결과 [관심][거절][무응답] → 메모 텍스트

**AI 텍스트 요청**: 의도 파싱은 P14 재사용 → "오늘 할 일" → 할 일 목록, "레이언스 건 현황" → 프로젝트 요약.

**자동 리마인더** (management command + cron):
- 오늘 재컨택 예정
- 내일 잠금 만료
- 서류 검토 2일 초과
- 면접 전날

### 14.3 업무 연속성 (P16 기획)

장시간 작업·대화·폼 입력이 중단되어도 시스템이 상태를 자동 보존한다.

**보존 시점**:
- 폼 입력 중 이탈 → JS `beforeunload` → HTMX POST → `ProjectContext.draft_data` 저장
- 보이스 대화 중단 → 자동 저장
- 탭 종료 → 브라우저 unload 훅

**draft_data JSON 구조**: `{form_name, field_values, completed_fields, missing_fields}`

**재개**: 프로젝트 진입 시 "이어서 하기" 배너 → 버튼 클릭으로 폼 복원. 보이스: "아까 하던 거 이어서 하자" → 컨텍스트 복원.

**이벤트 트리거 자동 제안 (`AutoAction` 모델)**:
- 프로젝트 등록 후 → 공지 초안 + 후보자 서치 자동 생성
- 컨택 관심 → 추천 서류 초안 생성
- 면접 합격 → 오퍼 템플릿
- 잠금 만료 1일 전 → 재컨택 리마인더

모두 `pending` 상태로 제안만 하고, 컨설턴트가 승인해야 실제 ActionItem으로 전환된다.

---

## 15. 전체 시나리오 — 삼성전자 AI Engineer 4/1~4/20

**4/1 수주**
- 사장님이 삼성전자에서 AI Engineer 의뢰 수신
- Project 생성: `deadline=4/30, phase=searching, status=open, closed_at=NULL, result=""`
- 박정일 컨설턴트에게 할당

**4/2 초기 서칭 (DB 검색 경로)**
- 박정일이 Candidates 메뉴에서 "경력 5~10년 AI/ML" 조건으로 검색
- 김철수, 이영희 선택 → "프로젝트에 추가" → 각각 Application 생성
- 시스템이 각 Application에 `reach_out` ActionItem 자동 제안, 박정일 확인 → `due_at=4/4` 자동 세팅

**4/3 추가 이력서 업로드**
- 박정일이 지인 소개로 박민수 이력서 파일 수신
- 파일 업로드 → 파서가 Candidate 생성 → 매칭 → Application + `reach_out` ActionItem 생성

**4/3 아침 박정일 대시보드**
```
오늘 할 일 3건
  • 김철수 reach_out (kakao) due 4/4
  • 이영희 reach_out (email) due 4/4
  • 박민수 reach_out (phone) due 4/4
```

**4/3 실제 연락**
- **김철수 (카톡)**: 답장 즉시 옴, 관심 있음 → `reach_out` 완료 (`result="관심, 이력서 요청"`) → 후속 팝업에서 `schedule_pre_meet` 선택 → 새 ActionItem 생성
- **이영희 (이메일)**: 답장 없음 → `reach_out` 완료 (`result="답장 대기"`) → `await_reply` 선택
- **박민수 (전화)**: 이직 의사 없음 → `reach_out` 완료 (`result="거절"`) → **Application 드롭** (`drop_reason=candidate_declined, drop_note="이직 의사 없음"`)

**4/5 김철수 사전미팅 일정 확정**
- `schedule_pre_meet` 완료 (`result="4/8 14:00 강남역"`) → 후속 `pre_meeting` 생성 (`scheduled_at=4/8 14:00, channel=in_person`)

**4/6 이영희 답장 마감 지남**
- 박정일 대시보드에 "마감 지남 1건" 표시 (is_overdue=True)
- 박정일이 `re_reach_out` 선택 → 새 ActionItem, 카톡으로 재연락

**4/8 김철수 사전미팅**
- 박정일이 김철수와 강남역 대면 미팅, 녹음
- `pre_meeting` 완료 버튼 → 모달에서 "녹음 파일 업로드" → `MeetingRecord` 생성(1:1)
- AI 전사/분석 → `transcript`, `analysis_json` 채워짐 → 8개 항목 인사이트 리포트
- `pre_meeting.result = "전체적으로 괜찮음, 제출 추천"`, `status=done`
- 후속 `prepare_submission` 자동 제안 → 박정일 확정

**4/10 김철수 제출**
- `prepare_submission` 완료 → 후속 `submit_to_client` 생성
- **SubmissionDraft 파이프라인 실행**: Generate → Consultation → Finalize → Masking → Convert(Word) → Download
- 박정일 검토·수정 후 클라이언트에 이메일 전송
- `submit_to_client` 완료 → `Submission` 생성(1:1), 파일 첨부
- **Signal 발동** → Project.phase = `screening` (제출 완료 활성 액션 생김)
- 후속 `await_doc_review` 자동 생성 (due_at = 4/15)

**4/14 클라이언트 피드백**
- 이메일: "김철수 좋은데 다른 옵션도 볼게요"
- 박정일이 `await_doc_review` 완료 (`result="추가 후보자 요청"`) → 후속으로 `follow_up: 추가 서치` 선택
- 신규 2명 매칭 → Application 추가
- **Phase 그대로 screening** — 김철수 제출 완료가 여전히 활성, OR 규칙으로 screening 유지

**4/16 이영희 2차 재연락도 무응답 → 드롭**
- `drop_reason=candidate_declined, drop_note="2차 재연락도 무응답"`

**4/18 김철수 1차 면접**
- `schedule_interview` → `interview_round` 생성 → 완료 → `Interview` 레코드(round=1, type=대면, scheduled_at=4/18, location=삼성 강남)
- 면접 후 `Interview.result=합격, feedback="기술 탄탄, 2차 추천"`
- 후속 제안: `interview_round` 2차 또는 `confirm_hire`

**4/20 2차 면접 합격 + 입사 확정**
- `interview_round` 2차 완료 → 후속 `confirm_hire` 생성
- 박정일이 `confirm_hire` 완료 → "이 후보자를 HIRED 처리하시겠습니까?" 확인 모달
- 확정 → `Application.hired_at = now()`, `status=done`

**Signal 자동 발동**:
1. Project: `closed_at=4/20 15:00, status=closed, result=success, note += "김철수 입사 확정"`
2. 신규1, 신규2 자동 드롭 (`drop_reason=other, drop_note="입사자(김철수) 확정으로 포지션 마감"`)
3. `compute_project_phase` 유지 (closed)

**최종 상태**:
```
Project:      status=closed, result=success, closed_at=4/20, note="김철수 입사 확정"
Applications:
  김철수: hired_at=4/20             — 성공
  이영희: dropped_at=4/16, candidate_declined
  박민수: dropped_at=4/3, candidate_declined
  신규1:  dropped_at=4/20, other (자동)
  신규2:  dropped_at=4/20, other (자동)
ActionItems: 모두 done/skipped/cancelled
```

---

## 16. 일일·주간 업무 시나리오

### 16.1 컨설턴트의 하루

1. **09:00 대시보드 접속**
   - 상단 알림 벨 도트 → 어젯밤 고객사 피드백 2건
   - "Recent Activity" 첫 항목 → 해당 프로젝트 상세로 점프

2. **09:10 어제의 액션 마무리**
   - `receive_doc_feedback` 완료 모달 → 피드백 내용 입력
   - 제안된 `schedule_interview` 수락 → 새 ActionItem

3. **09:30 새 이력서 검수**
   - Gmail로 들어온 2건이 이미 파싱되어 "검수 대기" 리스트에 있음
   - 상세 진입 → AI가 잘못 뽑은 연봉 수정 → Confirm
   - Candidate 생성 완료

4. **10:00 새 JD 도착**
   - Clients → 기존 고객사 → "새 프로젝트"
   - JD 텍스트 붙여넣기 → 저장 → 자동 분석 1분 대기
   - Search 탭 → 상위 20명 매칭 → 8명 "프로젝트에 추가"

5. **10:30 후보자 컨택**
   - Application 8건 각각 `reach_out` 생성
   - 카카오톡 일괄 메시지 → 답장 오면 완료 처리
   - 답장 없는 3건은 내일로 스케줄

6. **13:00 추천 서류 작성**
   - 어제 사전미팅 완료된 3명 → `prepare_submission` → `submit_to_client`
   - SubmissionDraft 파이프라인 6단계 실행
   - "Submit" 버튼 → Project phase 자동 screening 전환

7. **16:00 면접**
   - Zoom 후 바로 `interview_round` 완료 → 결과 "2차 통과" → `await_interview_result` 생성

8. **18:00 내일 계획**
   - 대시보드로 복귀 → 내일의 pending 액션 미리보기 → 퇴근

### 16.2 Owner의 주간 체크

1. **월요일 아침**
   - Approvals 배지 → 주말 사이 등록된 프로젝트 충돌 3건 승인/합류/반려
   - Team 탭 → 멤버별 Current Projects 건수 + 완료율 → 편중 조정

2. **수요일**
   - References 탭에서 신규 자격증/기업 시드 추가
   - Newsfeed에서 주요 인사 뉴스 1개 공유

3. **금요일**
   - 팀 KPI (전환율·성사율·평균 클로즈 기간) 리뷰
   - 유지보수 이슈 대응 확인

---

## 17. 권한 매트릭스

| 기능 | Owner | Consultant | Viewer | Pending |
|---|---|---|---|---|
| 로그인 | ✓ | ✓ | ✓ | ✓ |
| 대시보드 | ✓ | ✓ | ✓ | — |
| 후보자 검색/열람 | ✓ | ✓ | ✓ | — |
| 후보자 등록/수정 | ✓ | ✓ | — | — |
| 프로젝트 CRUD | ✓ | ✓ | — | — |
| 프로젝트 승인 큐 처리 | ✓ | — | — | — |
| ActionItem 생성·완료 | ✓ | ✓ | — | — |
| Submission Draft 파이프라인 | ✓ | ✓ | — | — |
| 고객사 CRUD | ✓ | ✓ | — | — |
| References 편집 | ✓ | — | — | — |
| Team 관리 (초대/승인) | ✓ | — | — | — |
| 조직 설정 변경 | ✓ | — | — | — |
| 음성 에이전트 | ✓ | ✓ | — | — |
| 텔레그램 바인딩 | ✓ | ✓ | — | — |
| 자동 알림 수신 | ✓ | ✓ | ✓ | — |

---

## 18. 이 문서의 위치

- **사업·전략**: [01-business-plan.md](01-business-plan.md)
- **업무 프로세스(이 문서)**: 02-work-process.md
- **코드·모델·배포**: [03-engineering-spec.md](03-engineering-spec.md)

이 세 문서는 **자립적**이다. `docs/archive/` 폴더는 과거 기록을 보존할 뿐이며, 언제든 삭제해도 마스터 3종과 현재 코드만으로 synco의 사업·업무·구현을 완전히 파악할 수 있다.

UI의 디자인 단일 진실 소스는 `assets/ui-sample/*.html` 과 `docs/design-system.md` 두 개다.
