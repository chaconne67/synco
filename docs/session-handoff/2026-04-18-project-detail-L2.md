# Session Handoff — Project Detail Level 2 (2026-04-18)

> **상태**: Phase A+B 완료, Phase C+D 미착수.
> **다음 세션**: 이 문서를 먼저 읽고, "다음 세션 재개 지침" 섹션의 단계를 따를 것.

---

## 1. 전체 맥락 — 왜 이 작업을 하고 있나

synco는 헤드헌팅 업무 관리 툴. 지금 **UI 전면 개편 스프린트** 중이고, 전 화면을 [`assets/ui-sample/*.html`](../../assets/ui-sample/) 목업 + [`docs/design-system.md`](../design-system.md) 기반으로 재작성 중. 순서는 **Projects 먼저 → 나머지 화면들**.

### Projects 스프린트 단계

- **Level 1 (칸반 리스트 `/projects/`)** — 완료. 경과 일수·입사자 이름·종료 컬럼 접힘·Stale auto-close·필터 바·정렬 토글. 
- **Level 2 (상세 페이지 `/projects/<pk>/`)** — C안 하이브리드 (Application-first 메인 + 부가 기능 드롭다운)
  - **L2.1**: 헤더/메인 구조 ✓
  - **L2.3-a**: 8단계 상수 + `current_stage` property + `stage_skipped` seed ✓
  - **L2.3-b**: 단계 건너뛰기 모달/뷰 ✓
  - **L2.3-c**: application_card 재작성 (진행바 + 현 단계 상자 + 2버튼) ✓
  - **L2.3-d**: `.stage-progress` CSS ✓
  - **Phase A**: 현 단계에 pending 없으면 **gate 액션 시작 버튼** 자동 노출 ✓ ← 이번 세션
  - **Phase B**: **이력서 수집 단계** 샘플 구현 — 3가지 방법(DB/이메일/업로드) ✓ ← 이번 세션
  - **Phase C (다음 세션)**: Phase B 패턴을 **나머지 7개 단계로 확장**
  - **Phase D (다음 세션)**: **산출물 자동 연동** (파일 업로드 → 액션 자동 완료 등)
- **L2.2** (더보기 드롭다운 확장) — 미착수
- **L2.4** (promote/drop UX 단순화) — 미착수

### 사장님 핵심 지시 (이 세션 직전 피드백)

"접촉 과정이 완료되었다면 다음 to-do는 이력서 접수. 이력서 접수를 어디서 하는지, 기존 이력서로 대체할 건지, 이메일로 받을 건지, 직접 받은 걸 업로드할 건지 — **각 단계별로 구체적인 대응 방안·액션 처리가 있어야 한다.**"

→ 시스템은 "할 일 기록 툴"이 아니라 **"다음에 뭘 할지 가이드하는 툴"** 이어야 함. 각 단계마다:
1. 다음 To-Do 자동 제시
2. 수행 방법 분기 (이력서: DB/이메일/직접)
3. 산출물 입력 UI

Phase A = 1번 해결. Phase B = 2번을 이력서 단계에서 샘플 구현. Phase C/D가 나머지.

---

## 2. 모델 상수 (모든 Phase 공통 기반)

**파일**: [projects/models.py](../../projects/models.py) 상단

```python
# 업무 프로세스 8단계 (엑셀 분석 §5 기반 + synco 사전미팅 추가)
STAGES_ORDER = [
    ("sourcing",        "서칭"),
    ("contact",         "접촉"),
    ("resume",          "이력서 수집"),
    ("pre_meeting",     "사전 미팅"),
    ("prep_submission", "제출 준비"),
    ("client_submit",   "고객사 제출"),
    ("interview",       "면접"),
    ("hired",           "입사"),
]

# ActionType.code → stage_id 매핑 (23 ActionTypes 중 20개, 범용 3종 제외)
STAGE_FROM_ACTION_TYPE = {...}

# 각 단계의 completion gate (이 ActionType 완료 = 단계 통과)
# 원칙: "단계 완료를 의미하는 가장 자연스러운 액션" — share_jd/await_reply 처럼 부산물성 액션 제외
STAGE_GATES = {
    "sourcing":        None,              # Application 존재 자체가 gate
    "contact":         "reach_out",       # "연락 한 번 성공 = 접촉 완료" (2026-04-18 share_jd→reach_out 변경)
    "resume":          "receive_resume",
    "pre_meeting":     "pre_meeting",
    "prep_submission": "submit_to_pm",
    "client_submit":   "submit_to_client",  # phase=screening 전환 트리거
    "interview":       "interview_round",
    "hired":           "confirm_hire",
}

STAGE_SKIPPED_ACTION_CODE = "stage_skipped"  # placeholder ActionType code
```

### 중요: Gate 설계 원칙 (Phase C 구현 시 참고)

각 단계에서 gate를 정할 때는 **"그 액션이 완료되면 실제로 단계가 끝났다고 말할 수 있는가"** 로 판단. "이름이 gate다워 보이는 액션"이 아니라 **사용자가 자연스럽게 완료로 인식하는 액션** 이 gate여야 함. 부산물성/보조 액션(예: share_jd, await_reply, re_reach_out)은 gate 아님.

### Application property (L2.3-a에서 추가)

- `current_stage` → 현재 진행 중 stage id (hired면 'hired', dropped면 None)
- `stages_passed` → 통과한 stage id set
- `current_stage_label` → 표시 이름
- `current_stage_action_codes` → 현 단계에 속한 ActionType.code 리스트
- `current_stage_gate_action` → 현 단계의 gate ActionType 인스턴스 (Phase A에서 추가)
- `current_stage_pending_actions` → 현 단계 pending ActionItem 리스트 (Phase A에서 추가)

---

## 3. Phase A 구현 — 단계 gate 액션 자동 추천

### 파일 변경

| 파일 | 변경 |
|---|---|
| [projects/models.py](../../projects/models.py) | `current_stage_gate_action` + `current_stage_pending_actions` property 추가 |
| [projects/views.py](../../projects/views.py) `action_create` | `?preset=<ActionType.code>` 쿼리 파라미터로 사전 선택 지원. `preset_action_type` context 전달 |
| [projects/templates/projects/partials/application_card.html](../../projects/templates/projects/partials/application_card.html) | 현 단계 할 일 리스트 밑에 "pending 없으면 gate 액션 시작 버튼" 블록 추가. resume 단계는 별도 파일 include |

### 동작 요약

현 단계의 pending ActionItem이 없으면:
- `resume` 단계 → `stage_resume_methods.html` 파티얼 렌더 (Phase B UI)
- 다른 단계 → gate ActionType 있으면 "이 단계를 완료하려면 **{label}** 액션이 필요합니다 [**{label} 시작하기 →**]" 버튼
- gate 없으면 (sourcing만 해당) → 기존 "할 일을 추가하거나 건너뛰세요" 안내

버튼 클릭 → `GET /projects/applications/<pk>/actions/new/?preset={gate.code}` → 액션 생성 모달 with 사전 선택

### 주의

- `action_create_modal.html` 템플릿은 `preset_action_type` context를 아직 시각적으로 활용하지 않음. Phase C에서 모달이 preset을 강조 표시하도록 개선할 여지 있음 (지금은 form.initial만 세팅).
- preset code가 DB에 없으면 silently 무시 (preset_at=None).

---

## 4. Phase B 구현 — 이력서 수집 단계 3가지 방법

### 파일 변경

| 파일 | 내용 |
|---|---|
| [projects/urls.py](../../projects/urls.py) | URL 3개 추가: `application_resume_use_db` / `application_resume_request_email` / `application_resume_upload` |
| [projects/views.py](../../projects/views.py) | `_create_receive_resume_action` 헬퍼 + 뷰 3개 |
| [projects/templates/projects/partials/stage_resume_methods.html](../../projects/templates/projects/partials/stage_resume_methods.html) | 3 버튼 UI (DB/이메일/업로드) |
| [projects/templates/projects/partials/resume_email_request_modal.html](../../projects/templates/projects/partials/resume_email_request_modal.html) | 이메일 요청 폼 모달 |
| [projects/templates/projects/partials/resume_upload_modal.html](../../projects/templates/projects/partials/resume_upload_modal.html) | 파일 업로드 모달 |

### 각 방법별 동작

**① DB 기존 이력서 사용** (`application_resume_use_db`)
- 조건: `application.candidate.current_resume` 존재
- 동작: 확인 없이 `receive_resume` ActionItem DONE 즉시 생성. note = "DB 기존 이력서 재사용 (파일: filename)"
- 없으면 버튼 비활성화, tooltip "등록된 이력서 없음"

**② 이메일로 요청** (`application_resume_request_email`)
- GET: 폼 모달 (to = candidate.email readonly, body textarea)
- POST: `receive_resume` ActionItem **PENDING** 생성 + due_at = now+3일. note = 이메일 본문
- **실제 이메일 송신은 하지 않음** — 로그만 기록 (Phase D에서 실제 발송 연동 예정)

**③ 파일 직접 업로드** (`application_resume_upload`)
- GET: 파일 input 모달 (PDF/Word/HWP)
- POST: `candidates.Resume` 레코드 생성 + 후보자 `current_resume` 비어있으면 자동 세팅 + `receive_resume` DONE 생성
- **파일 텍스트 추출·AI 처리는 하지 않음** — 단순 업로드만 (Phase D에서 `data_extraction` 파이프라인 연동 예정)

### 알려진 제약

- 3 뷰 모두 모달 닫기를 `setTimeout(() => ... = '', 200)` 으로 처리. HTMX 204 응답으로 모달 자동 닫힘이 안 되는 환경에서 작동. 깔끔하지 않음 → Phase D에서 `HX-Trigger` 로 모달 close event 발행하도록 개선 가능
- `request_email` 본문에 기본 템플릿 자동 주입되지만 조직별 커스터마이즈 불가 → Phase C에서 `Organization` 별 이메일 템플릿 필드 추가 검토

---

## 5. 다음 세션 계획 — Phase C + D

### Phase C — Phase B 패턴을 나머지 7개 단계로 확장

각 단계별로 `stage_{stage_id}_methods.html` 파티얼 + 뷰 세트 구축. 권장 작업 순서:

1. **사전 미팅** (`pre_meeting`) — 가장 간단. 방법: 대면/화상/전화. 완료 시 미팅 메모 입력.
2. **제출 준비** (`prep_submission`) — 방법: AI 초안 생성(`SubmissionDraft` 파이프라인 연동)/수동 작성. 이미 `projects/services/draft_*.py` 존재
3. **고객사 제출** (`client_submit`) — 방법: 이메일/포털 업로드. `Submission` 레코드 생성 필수 (phase=screening 트리거)
4. **면접** (`interview`) — 방법: 1차/2차/3차/최종. `Interview` 모델 활용
5. **입사** (`hired`) — 방법: 입사일 세팅. `hire_application()` 서비스 재사용 (이미 있음)
6. **접촉** (`contact`) — Phase B 수준 미만. 방법: 전화/이메일/카카오/LinkedIn (기록만)
7. **서칭** (`sourcing`) — 생략 가능 (Application 생성 자체가 gate)

각 단계 구현 전 **stage별 필수 산출물과 방법 분기**를 문서 마지막 부록 A 표 참고.

### Phase D — 산출물 자동 연동 (트리거 자동화)

1. **Resume 업로드 → receive_resume 자동 완료** (Phase B에서 수동 호출 중. 시그널로 자동화)
2. **Submission 레코드 생성 → submit_to_client 자동 완료**
3. **Interview 레코드 생성 → interview_round 자동 완료**
4. **이메일 발송 실제 연동** — `accounts.EmailConnection` + Gmail API 활용
5. **Application.hired_at 세팅 → confirm_hire 자동 완료** (이미 있음)
6. **MeetingRecord 생성 → pre_meeting 자동 완료**

구현 위치: `projects/signals.py` (현재 phase signal만 있음).

---

## 6. 다음 세션 재개 지침

### 1) 이 문서 먼저 읽기

```
cat docs/session-handoff/2026-04-18-project-detail-L2.md
```

### 2) 현재 상태 확인 (컨텍스트 hot start)

```bash
# 브랜치/변경 확인
git status
git log --oneline -20

# 개발 서버 띄우기
./dev.sh

# 프로젝트 상세 페이지 동작 확인
# http://localhost:8000/projects/ → 카드 클릭 → 활성 Application 있는 프로젝트
```

### 3) Phase A/B 동작 스모크 테스트

- Application의 current_stage가 contact이면서 share_jd pending/done 없음 → "JD 공유하기 시작하기" 버튼 표시돼야 함
- Application의 current_stage가 resume → 3 버튼 카드 (DB/이메일/업로드)
- 한 application을 임의로 resume stage로 만들려면 shell에서 share_jd DONE ActionItem 생성

### 4) Phase C 착수 시 추천 순서

```
1. 본 문서 §5 부록 A 표 읽기 (stage별 방법·산출물 정의)
2. 사장님께 단계별 "방법 목록" 최종 확인 (8개 단계 × 방법 N개 = 많음)
3. 구현은 stage 하나씩 — 각 stage = partial 1개 + view 3~4개 + modal 2~3개 분량
4. 먼저 pre_meeting 단계부터 시작 (가장 단순)
```

### 5) 투두 복원

다음 세션 시작 시 첫 번째 message에서:

```
/projects/ 상세 페이지 Phase C + D 이어서 진행.
docs/session-handoff/2026-04-18-project-detail-L2.md 를 먼저 읽고 컨텍스트 잡은 뒤
프로젝트 상세 Level 2 구현 계속. 
첫 작업은 Phase C의 pre_meeting 단계 샘플 구현.
```

라고 지시하면 됩니다.

---

## 7. 알려진 이슈 (다음 세션에서 같이 정리)

- `_build_overview_context` (projects/views.py 611) 에 `project.submissions` 오용 (이미 부분 수정됐지만 다른 호출자 있을 수 있음)
- `project_detail_tabs` 관련 레거시 view/template 몇 개가 아직 존재 (tab_overview/tab_search/tab_submissions/tab_interviews). **C안 채택으로 사용 안 함** — 이후 정리 대상
- `project-detail.html` UI 샘플 목업(assets/ui-sample/)은 8탭 버전으로 만들어둠 — C안에 맞춰 업데이트 필요
- `docs/design-system.md` 에 stage-progress 컴포넌트 문서화 아직 안 됨 → §4 Components 에 추가 필요
- **Candidate.name이 파일명으로 들어간 레코드 존재** (예: "00 다국적 기업 홍보 담당자 리스트.docx"). `data_extraction` 파이프라인이 이력서 import 시 실제 이름 추출 실패한 케이스로 추정. 별도 cleanup/재추출 작업 필요
- **contact gate 변경 기록**: 2026-04-18 `STAGE_GATES["contact"]` 를 `share_jd` → `reach_out` 로 변경. 실제 헤드헌터 워크플로우에 맞추기 위해. Phase C에서 다른 단계 gate 검토 시 같은 원칙 적용
- **seed_dummy_data `random.sample` 적용** (2026-04-18) — 이전에는 `random.choice`로 같은 application에 중복 ActionType 생성됐음. 과거 시딩된 환경이라면 재시딩 권장 (`seed_dummy_data --wipe`)

---

## 부록 A — 각 단계별 방법·산출물 매트릭스 (Phase C 구현 참고)

| 단계 | gate ActionType | 방법 분기 (Phase C에서 구현) | 필수 산출물 |
|---|---|---|---|
| sourcing | — | DB 검색 · 외부 탐색 (LinkedIn/Saramin/Incruit) | Application 레코드 |
| contact | share_jd | 전화 · 이메일 · 카카오 · LinkedIn 메시지 | 후보자 JD 수신 확인 |
| **resume** (Phase B 완료) | receive_resume | **DB 재사용 · 이메일 요청 · 직접 업로드** | Resume 파일 |
| pre_meeting | pre_meeting | 대면 · 화상 · 전화 | MeetingRecord (노트·녹음) |
| prep_submission | submit_to_pm | AI 초안 (SubmissionDraft) · 수동 작성 | SubmissionDraft 완료 |
| client_submit | submit_to_client | 이메일 발송 · 포털 업로드 · 파일 공유 | Submission 레코드 |
| interview | interview_round | 1차/2차/3차/최종 | Interview 레코드 + 피드백 |
| hired | confirm_hire | 입사일 확정 | Application.hired_at |

---

## 부록 B — 이번 세션 수정 파일 전체 목록

**모델/서비스**:
- `projects/models.py` — STAGES_ORDER / STAGE_FROM_ACTION_TYPE / STAGE_GATES / STAGE_SKIPPED_ACTION_CODE 상수 + Application property 5종 추가
- `projects/services/dashboard.py` — sort direction 파라미터 추가 (Level 1), Stale auto-close sweep
- `projects/views.py` — project_list sort/filter context, application_skip_stage, application_resume_* 3종, action_create preset, _build_tab_context 버그 수정, project_detail 새 template에 맞춤

**URL**:
- `projects/urls.py` — application_skip_stage, application_resume_* 3종

**템플릿** (신규):
- `projects/templates/projects/partials/stage_skip_modal.html`
- `projects/templates/projects/partials/stage_resume_methods.html`
- `projects/templates/projects/partials/resume_email_request_modal.html`
- `projects/templates/projects/partials/resume_upload_modal.html`

**템플릿** (재작성/수정):
- `projects/templates/projects/project_detail.html` (목업 토큰 적용, 헤더 + 더보기 드롭다운)
- `projects/templates/projects/partials/application_card.html` (8단계 진행 바 + 현 단계 상자 + gate 버튼 + resume 방법 분기)
- `projects/templates/projects/partials/project_applications_list.html` (HTMX 리프레시 시 카드 래퍼 유지)

**관리 커맨드**:
- `projects/management/commands/update_action_labels.py` — ActionType 라벨 일괄 업데이트 + stage_skipped seed
- `projects/management/commands/close_overdue_projects.py` — deadline 경과 OPEN 프로젝트 자동 실패 종료

**CSS**:
- `static/css/input.css` — stage-progress / col-container / col-pill / card-* / av-N / meta-pill 추가

**설계 문서**:
- `docs/design-system.md` — §6 Don't에 좌측 스트라이프 금지, arbitrary text-size 지양, UX 용어 사람 중심 규칙 추가
