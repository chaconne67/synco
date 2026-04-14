# 07. 구현 계획 — 단계별 실행

재설계를 실제 synco 코드에 반영하는 단계별 계획. 데이터가 없으므로 마이그레이션 복잡도는 0이지만, 코드 리팩터 범위는 크다.

---

## 1. 영향 범위 실측

### 1-1. 파일 수
`ProjectStatus` 또는 `.status` 를 참조하는 파일: **27개**

주요 파일:
- `projects/views.py` (3,030줄) — 가장 큰 변경
- `projects/models.py` (849줄) — 모델 재정의
- `projects/signals.py` (116줄) — phase 파생 로직 추가
- `projects/services/lifecycle.py` — 상태 전환 로직 재작성
- `projects/services/collision.py` — 충돌 감지 (ProjectApproval 경로 유지)
- `projects/services/dashboard.py` — 대시보드 집계 재작성
- `projects/services/urgency.py` — days_elapsed 기반 긴급도 (유지 가능)
- `projects/services/auto_actions.py` — ProjectStatus 기반 트리거 재작성
- `projects/services/submission.py` — Submission 생성 로직 재정의

### 1-2. 템플릿
- `templates/projects/list.html` — 칸반 재작성
- `templates/projects/board.html` — 10-state 컬럼 → 5 phase + 종료
- `templates/projects/detail.html` — Application 리스트로 재작성
- `templates/projects/partials/view_filters.html` — phase 기반 필터
- 기타 status 참조 partial 다수

### 1-3. 마이그레이션
- 기존 `projects/migrations/*.py` 전부 삭제 후 재생성 (데이터 없으므로 안전)
- 로컬 DB는 볼륨 제거 후 재생성

---

## 2. 단계별 실행 계획

### Phase 1 — 모델 재정의 (반나절)
**목표**: 새 스키마를 코드로 정의하고 로컬에서 `migrate` 성공까지.

1. `projects/models.py` 수정:
   - `ProjectStatus` enum 제거
   - `ProjectPhase`, `CloseReason`, `ApplicationStage`, `DropReason`, `ProjectEventType` enum 추가
   - `Project.status` → `phase`, `closed_at`, `close_reason`로 교체
   - `Application` 모델 신규 추가
   - `ProjectEvent` 모델 신규 추가
   - `Offer` 모델 제거
   - `Contact`에 `application` FK 추가 (option B), result enum 제거
   - `Submission`의 `status` 필드 제거 또는 재정의 (결정 필요)
   - `Interview.submission` → `application` FK 변경
   - `MeetingRecord.project/candidate` → `application` FK 변경
2. 기존 `projects/migrations/` 파일 전부 삭제 (0001_initial부터)
3. `uv run python manage.py makemigrations projects` → 새 0001_initial 하나 생성
4. 로컬 DB 초기화 + `migrate` 성공 확인

**이 단계에서는 views/templates는 에러나도 OK.** 모델 먼저 확정.

### Phase 2 — 서비스 레이어 재작성 (반나절)

1. `projects/services/lifecycle.py`:
   - 기존 `maybe_advance_to_interviewing`, `maybe_advance_to_negotiating` 등 제거
   - 없음. 모든 phase 전진은 Application signal에서 자동 처리.
2. `projects/services/application_lifecycle.py` 신규 작성:
   - `promote(application, actor)`, `drop(application, reason, actor, note)`, `restore(application, actor)` 함수
3. `projects/signals.py`:
   - Application post_save/post_delete → `compute_project_phase` 호출 + `Project.phase` 업데이트
   - 기존 `on_project_created` 로직 재검토 (NEW status 제거됐으므로 트리거 재정의)
4. `projects/services/submission.py`:
   - Submission 생성 시 해당 Application의 stage 전이와 연동
5. `projects/services/auto_actions.py`:
   - `ProjectStatus.NEW` 기반 트리거 → `ProjectPhase.SEARCHING` 진입 시로 변경
6. `projects/services/dashboard.py`:
   - status별 집계 → phase별 집계로

### Phase 3 — 뷰 재작성 (1일)

1. `projects/views.py`:
   - `project_list` — 칸반 뷰로 재작성 (5 phase + 종료 컬럼)
   - `project_detail` — Application 리스트 렌더링
   - 새 뷰: `application_promote`, `application_drop`, `application_restore`, `project_add_candidate`, `project_timeline`, `project_close`
   - 기존 `status_update` 뷰 제거 (phase 수동 조작 금지)
   - `ProjectStatus` 참조 전부 제거
2. `projects/forms.py`:
   - `ProjectForm`에서 `status` 필드 제거
   - 새 폼: `AddCandidateToProjectForm`, `DropApplicationForm`, `CloseProjectForm`
3. `projects/urls.py`:
   - Application 관련 라우트 추가

### Phase 4 — 템플릿·UI 재작성 (1-2일)

1. 칸반 (`list.html`):
   - 5 phase 컬럼 + 종료 컬럼 접힘/펼침
   - 카드 디자인 (pending 수, 경과일, phase별 컨텍스트)
2. 프로젝트 상세 (`detail.html`):
   - 상단 요약 블록
   - Application 리스트 (프로그레스 바 + promote/drop 버튼)
   - + 후보자 추가 모달
3. 프로그레스 바 partial — 5단계 원형 마커 + 연결선 (Tailwind 기반)
4. 드롭 모달 partial — DropReason 선택 + 노트
5. 필터 바 — phase, 컨설턴트, 고객사, 기간
6. Timeline 뷰 (보너스, 시간 남으면)

### Phase 5 — 테스트 + seed 데이터 (반나절)

1. 단위 테스트:
   - `compute_project_phase` 규칙의 10개 시나리오 (04-phase-derivation-rule.md 참조)
   - `promote`, `drop`, `restore` 서비스 함수
   - signal이 phase를 재계산하는지
2. 뷰 테스트:
   - 칸반 렌더링
   - Application 추가/promote/drop 플로우
   - 권한·조직 필터링
3. Seed 데이터 management command (옵션):
   - `seed_from_excel` — 엑셀 파일에서 김현정 탭 일부를 파싱해서 Project/Application/Candidate 생성
   - QA 용도로만 사용, 운영 배포 전 제거

### Phase 6 — 레거시 제거 + 린트 통과 (반나절)

1. `Offer` 모델 관련 코드 전부 제거 (OfferForm, 오퍼 관련 뷰/템플릿)
2. `PENDING_APPROVAL` 하드코딩 제거 (ProjectApproval 경로 유지)
3. `ruff check .` 통과
4. `ruff format .` 적용
5. `pytest -v` 전체 통과 확인
6. 개발 서버에서 E2E 수동 확인 (`/browse` 스킬로 스크린샷까지)

---

## 3. 단계별 예상 시간 합계

| Phase | 예상 시간 | 리스크 |
|---|---|---|
| 1. 모델 재정의 | 0.5일 | 낮음 |
| 2. 서비스 레이어 | 0.5일 | 중 (기존 signal 로직 재검토 필요) |
| 3. 뷰 재작성 | 1.0일 | 중 (3,030줄 views.py 수정) |
| 4. 템플릿/UI | 1-2일 | 중-높음 (디자인 완성도) |
| 5. 테스트/seed | 0.5일 | 낮음 |
| 6. 레거시 제거 | 0.5일 | 낮음 |
| **합계** | **4-5일** | |

`impl-forge-batch` 스킬로 각 Phase를 격리된 worktree에서 순차 실행하는 것을 권장.

---

## 4. 다음 세션 시작 체크리스트

다음 세션에서 이 작업을 이어받을 때 확인해야 할 것들:

- [ ] `docs/designs/20260414-project-application-redesign/README.md` 전체 읽기
- [ ] 사장님과 설계 내용이 여전히 유효한지 5분 확인 대화
- [ ] 결정사항 변경 있는지 확인 (특히 `Submission.status` 필드 처리 여부)
- [ ] `plan-forge` 또는 `impl-forge-batch` 실행 여부 결정
- [ ] Phase 1(모델 재정의)부터 시작. 로컬 DB 클린 재생성 전에 백업 여부 확인 (어차피 테스트 데이터뿐이라 삭제해도 무방)

---

## 5. 열린 결정사항 (구현 전 확정 필요)

### 5-1. `Submission.status` 필드 처리
현재: `작성중 | 제출 | 통과 | 탈락` (4-state)

선택지:
- (A) Submission.status 완전 제거. Application.stage로 통합.
- (B) Submission.status는 "서류 작성 파이프라인 내부 상태"로 의미 축소 (작성중/제출만). 통과/탈락은 Application.stage로 이동.
- (C) 그대로 두고 Application.stage와 이중 관리.

**권장: B**. AI 서류 작성 파이프라인(SubmissionDraft)이 있어서 "작성중/제출" 상태는 내부 워크플로로 필요함. 통과/탈락은 Application stage가 대체.

### 5-2. `Contact` 스키마 변경 범위
- 최소 변경: 의미만 재정의, 스키마 그대로
- 권장: `Contact.application` FK 추가, `result` enum 제거

**권장: 권장 옵션**. Application에 명시적으로 매달림.

### 5-3. Auto-close 규칙
- 시간 기반 자동 종료 규칙을 도입할지 여부
- 만약 도입한다면 임계값 (30일? 60일? 90일?)

**권장: v1에서는 수동 종료만**. v2에 auto-close 추가 검토.

### 5-4. Candidate가 HIRED된 프로젝트의 나머지 Application 처리
- (A) 자동으로 전원 DROPPED (drop_reason: "클라이언트_포지션마감")
- (B) 그대로 유지 (UI에서 "비활성" 표시)

**권장: A**. 깔끔하고 데이터 정합성 유지.

### 5-5. 한 후보자가 여러 프로젝트에서 HIRED 되는 경우
- 이론적으로 가능하지만 현실에서는 한 후보자가 하나의 포지션에만 입사
- Candidate에 "current_employer" 같은 단일 상태를 둘지, Application의 HIRED 여부로 판단할지

**권장: Application.stage=HIRED가 여러 개 있으면 warning 로그만. 비즈니스 결정은 향후로**.

---

## 6. 기타 고려사항

### 6-1. v2 UI 재설계와의 맞물림
synco v2는 voice-first UI로 이미 상당 부분 구현됨. 칸반/프로젝트 상세는 v2 디자인 언어(dark navy, Stellate style)와 일관성을 맞춰야 함. 기존 `feat(chrome+dashboard): Stellate-style dark navy chrome + Teal HQ grid` 커밋(48dbea3)의 스타일 가이드 참조.

### 6-2. RBAC 연동
현재 `feat/rbac-onboarding` 브랜치에 RBAC 작업 중. Project 접근 제한은 `assigned_consultants` 기반. Application도 같은 권한 모델 따라야 함.

### 6-3. AI 서비스 연동
- `jd_analysis`: 그대로 유지
- `candidate_matching`: `ProjectStatus.SEARCHING`에서 트리거 → `ProjectPhase.SEARCHING`으로 교체
- `submission.draft`: 기존대로 유지 (Application.stage=RECOMMENDED 진입 시)

### 6-4. 알림/Notification
- 현재 `ProjectStatus` 변화를 notification으로 쏘는 로직이 있는지 확인 필요
- 있다면 `phase_changed` 이벤트로 교체

---

## 7. 작업 진행 시 유의사항

1. **Phase 1부터 6까지 순서대로 진행**. 중간 단계에서 중단돼도 이전 단계의 산출물이 유의미하도록.
2. **각 Phase 끝에서 커밋**. 큰 커밋 하나보다 단계별 6개 커밋이 리뷰·롤백에 용이.
3. **브랜치**: `feat/project-application-redesign` 신규 생성. 현재 `feat/rbac-onboarding`과 분리.
4. **병합 전 사장님 검토**: UI 스크린샷 + 주요 동작 녹화 (5분)로 확인.
5. **운영 배포는 RBAC 작업 완료 후**. 두 큰 변화를 동시에 배포하지 않는다.
