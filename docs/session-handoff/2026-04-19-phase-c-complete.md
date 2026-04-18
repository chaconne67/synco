# Session Handoff — Phase C 완료, Candidate 재설계로 이관 (2026-04-19)

> **상태**: Phase C (프로젝트 상세 페이지 단계 모델 재설계) **완전 완료**.
> **다음 세션**: 이 문서를 먼저 읽고, §8 "재개 지침" 단계를 따를 것.
> **선행 핸드오프**: [2026-04-18-project-detail-L2.md](2026-04-18-project-detail-L2.md) (Phase A/B 배경)

---

## 1. 맥락 — 왜 Phase C였고, 지금 어디에 있나

synco는 헤드헌팅 업무 관리 툴. 스프린트 순서:
1. **Project 메인 페이지 (Phase A/B/C)** ← 완료
2. **Candidate 메인 페이지 (Phase D 후보)** ← **다음 세션 시작 지점**
3. **Project 서브 페이지 재설계 + 레거시 탭 제거** (Candidate 완료 후 동시 진행)
4. **Dashboard 재설계** (Project+Candidate 확정 후)
5. **Reference·Dashboard 등 보조 화면**

사장님 원칙: 핵심 2개는 **Project + Candidate**. Dashboard는 둘의 데이터를 보여주는 read-only 뷰. 따라서 Project+Candidate를 완성한 뒤에 Dashboard 재점검이 올바른 순서.

---

## 2. Phase C 실제 결과

### 커밋 범위
- **Base**: `db74b2c feat(ui): standardize Tailwind typography tokens + project detail Phase A/B`
- **HEAD**: `ba3b5f7 fix(projects): add @membership_required + N+1 fix on pre_meeting properties`
- **총 25 커밋** (UI 스프린트 베이스 제외 — 그건 Phase A/B 마무리 묶음)

### 검증 상태
- `uv run pytest` → **705 passed / 0 failed** (1분 40초)
- `uv run ruff check projects/ candidates/ tests/` → 클린
- `uv run python manage.py check` → 0 issues

### 구현 범위 요약

**모델/상수 ([projects/models.py](../../projects/models.py))**
- `STAGES_ORDER` 3개 라벨 변경: 이력서 수집 → **이력서 준비** / 제출 준비 → **이력서 작성(제출용)** / 고객사 제출 → **이력서 제출**
- `CARD_STAGES_ORDER` 신규 상수 (7단계, 서칭 제외) — 후보자 카드 진행바 전용
- `Submission.batch_id` UUID 필드 추가 — 배치 제출 시 동일 UUID 공유, 개별 제출 시 None
- `Application.has_pre_meeting_scheduled` / `pre_meeting_scheduled_at` properties (prefetch cache 인식)
- migration `0005_submission_batch_id`

**프로젝트 상세 페이지 구조 변경 ([projects/templates/projects/project_detail.html](../../projects/templates/projects/project_detail.html))**
- **영역 A** — 프로젝트 레벨 작업: 서칭 도구 + 이력서 배치 제출 관리
- **영역 B** — 후보자 카드 리스트 (7단계 진행바 + 단계별 전용 파티얼 dispatch)

**서칭 도구 ([partials/area_a_searching.html](../../projects/templates/projects/partials/area_a_searching.html) + [services/searching.py](../../projects/services/searching.py))**
- DB에서 찾기 → candidates 페이지에 `?project=<uuid>` 컨텍스트 전달
- 후보자 카드에 "프로젝트에 추가" 버튼 조건부 노출
- 페이지네이션·카테고리 전환 시에도 `?project=` 파라미터 유지
- 외부 채널 4개 (잡코리아/사람인/LinkedIn/이메일) — 플레이스홀더만 (Phase D에서 실제 구현)

**배치 제출 관리 ([partials/area_a_submission_batch.html](../../projects/templates/projects/partials/area_a_submission_batch.html))**
- `pending_for_submission` (current_stage == "client_submit") 대상 체크박스 리스트
- 선택한 N명을 단일 `Submission.batch_id` UUID로 묶어 일괄 제출
- Stage 검증: client_submit 외 단계 Application은 뷰에서 거절 (workflow bypass 방지)

**후보자 카드 7단계 파티얼**
- [stage_contact.html](../../projects/templates/projects/partials/stage_contact.html) — 응답 기록 라디오 (긍정/부정/보류) + 메모. 부정은 drop.
- [stage_resume.html](../../projects/templates/projects/partials/stage_resume.html) — Phase B의 3방법(DB 재사용/이메일 요청/파일 업로드) 그대로
- [stage_pre_meeting.html](../../projects/templates/projects/partials/stage_pre_meeting.html) — 일정 확정 → 결과 기록 2단계 토글. 오디오 파일 첨부(STT는 Phase D)
- [stage_prep_submission.html](../../projects/templates/projects/partials/stage_prep_submission.html) — 컨설턴트 컨펌 버튼 (자동 생성 템플릿은 Phase D)
- [stage_client_submit.html](../../projects/templates/projects/partials/stage_client_submit.html) — 단독 제출 버튼 (batch_id=None). 배치는 영역 A에서.
- [stage_interview.html](../../projects/templates/projects/partials/stage_interview.html) — 합격/탈락/보류 select + 선택 리뷰 textarea. 탈락은 drop.
- [stage_hired.html](../../projects/templates/projects/partials/stage_hired.html) — 기존 application_hire 뷰 재사용

**관리 커맨드**
- [update_stage_labels.py](../../projects/management/commands/update_stage_labels.py) — ActionType.label_ko 일괄 갱신 (1회성)

---

## 3. 전체 커밋 로그 (Phase C 범위)

```
ba3b5f7 fix(projects): add @membership_required + N+1 fix on pre_meeting properties
7ff2672 docs(phase-c): Task 17 SKIP — legacy tab cleanup deferred to Phase D
47d4d91 feat(projects): hired stage partial — reuses application_hire view
c2ffb27 feat(projects): interview stage — completion + optional after-interview review
5054ff3 feat(projects): client_submit stage — single-candidate submission path
38b27a1 feat(projects): prep_submission stage — consultant confirm (auto-gen deferred)
1f7ad17 feat(projects): pre_meeting stage — schedule + result record (audio optional)
3044017 test(projects): update stage-dispatch test to check stable URL instead of Task 10 stub
c337ada refactor(projects): remove stage_resume_methods.html, update resume stage labels
eb6394d feat(projects): contact stage partial — completion check + response record
9ba9b3c feat(projects): per-stage partial dispatch from application card
0f0f1f5 chore(projects): align stage-progress CSS to 7 columns + drop unused stages_order context
7bcd005 refactor(projects): card progress bar uses CARD_STAGES_ORDER (7 stages)
5767cf3 fix(projects): add stage validation to submission_batch_create (prevent bypass)
19f6a92 feat(projects): batch submission UI + view — creates Submissions sharing batch_id
fe64c14 feat(projects): add external channel placeholders (Jobkorea/Saramin/LinkedIn/Email)
fd1a851 fix(candidates): preserve ?project= across pagination and category filters
200c4da feat(projects): DB searching → candidate add flow in project detail area A
9593178 fix(projects): use real Tailwind tokens in area A partials
60a5108 refactor(projects): restructure project_detail into area A + area B
08d3c43 style(projects): apply ruff format to Task 3 new files
92b626f feat(projects): add Submission.batch_id for grouping batch-submitted resumes
53f23e3 feat(projects): add CARD_STAGES_ORDER for per-candidate 7-stage view
03b3227 chore(projects): drop unused pytest import + align plan with flat tests/ convention
d9cbbcc refactor(projects): rename resume/submission stage labels per Phase C spec
```

---

## 4. 설계·플랜 문서 (그대로 유지, 참조용)

- **설계 스펙**: [docs/superpowers/specs/2026-04-18-project-detail-stage-model-design.md](../superpowers/specs/2026-04-18-project-detail-stage-model-design.md)
- **Phase C 구현 플랜**: [docs/superpowers/plans/2026-04-18-project-detail-stage-model-phase-c.md](../superpowers/plans/2026-04-18-project-detail-stage-model-phase-c.md) — Task 17 SKIP 문서화 포함

Candidate 재설계 시에도 설계 철학(프로젝트 레벨/후보자 레벨 분리, 판정 기준 명시)은 동일하게 적용 권장.

---

## 5. 알려진 미해결 이슈 (Phase D 범위)

### 5.1 Task 17 — 레거시 탭 뷰 정리 (연기)

Phase C Task 17로 계획했으나 실측 결과 `project_tab_*` 뷰 4개는 dead code가 아님. 여전히 **현역으로** 아래에서 사용 중:

- `posting_section.html:23`, `posting_edit.html:31` — "개요로 돌아가기" 타겟
- `submission_draft.html:16` — "제출 리스트로" 링크
- `projects/views.py:1032` — `submission_create` 성공 후 `project_tab_submissions(request, pk)` 직접 함수 호출
- `projects/views.py:1622` — `tab_interviews_with_form.html` 직접 렌더
- `projects/services/voice/context_resolver.py:17-19` — 음성 라우팅 하드코딩 리스트
- 테스트 15+: test_p05_project_tabs.py, test_p07_submissions.py, test_p09_interviews_offers.py, test_p10_posting.py

상세 마이그레이션 체크리스트: [Phase C 플랜 Task 17 섹션](../superpowers/plans/2026-04-18-project-detail-stage-model-phase-c.md#task-17-레거시-탭-뷰템플릿-정리--skip-phase-d로-이관).

### 5.2 최종 리뷰가 짚은 Minor 이슈 (Phase D 정리 권장)

최종 리뷰 (opus 수준) 결과 C1(membership_required)과 I1(N+1)은 커밋 ba3b5f7에서 수정 완료. 나머지 이슈는 Phase D 착수 시점에 정리하는 게 효율적:

- **I2**: `stage_contact_complete` / `stage_interview_complete`에서 빈 문자열 note → `None` 변환 필요 (현재 `""`로 저장됨)
- **I3**: cross-org / unauthenticated 테스트 누락 — 6개 스테이지 뷰 전체
- **I4**: `stage_resume.html`의 `candidate.current_resume` 접근 → `project_detail` view에서 `select_related("candidate__current_resume")` 추가 필요
- **M1**: 7개 stage 테스트가 `assert resp.status_code in (200, 302)` — 302만 허용으로 엄격화
- **M2**: 스테이지 뷰 안에서 `DropReason`, `ActionItem`, `ActionItemStatus`, `ActionType` 함수 지역 import 중복 (모듈 레벨에도 있음)
- **M3**: `stage_contact_complete`의 `f"응답: {response}. {note}".strip()`은 동작하지만 의도가 모호. `f"응답: {response}." + (f" {note}" if note else "")` 로 리팩토링 권장.
- **M4**: `stage_hired.html`만 HTMX 속성 동시 사용 (`method="post"` + `hx-post`). 다른 6개 파티얼과 통일 권장.

### 5.3 아키텍처 관찰 (설계 단계에서 결정 필요)

- **Workflow 강제 일원화**: `submission_batch_create`만 `current_stage == "client_submit"` 검증. 나머지 5개 stage 뷰는 검증 없음. 공유 가드 `_assert_current_stage(app, expected)` 도입 고려.
- **`pending_for_submission` HTMX 갱신 누락**: area A 배치 패널은 페이지 로드 시만 계산. `applicationChanged` HTMX 이벤트가 카드 리스트를 새로 그릴 때 area A는 업데이트 안 됨. 사용자가 작업 중 새 후보가 client_submit 도달해도 배치 패널에 안 보임 → 전체 페이지 새로고침 필요.
- **사전 미팅 sub-state 패턴**: Application 모델에 property로 sub-state를 두는 패턴 시작됨. 다른 단계(예: 면접 라운드)에 확산되면 설계 재검토 필요.

---

## 6. 현재 앱 상태 하이레벨

### 정상 작동 플로우 (수동 확인 필요)

1. 프로젝트 생성 → `/projects/<pk>/`
2. 영역 A "DB에서 찾기" → candidates 페이지 → "프로젝트에 추가" → 후보자 카드 생성
3. 후보자 카드 — 접촉 단계: 긍정/부정/보류 기록
4. 이력서 준비: DB 재사용 / 이메일 요청 / 업로드 3경로
5. 사전 미팅: 일정 → 결과 기록 (텍스트 + 오디오 첨부 선택)
6. 이력서 작성 컨펌
7. 이력서 제출 — 단독 버튼 또는 영역 A 배치 체크박스
8. 면접: 합격/탈락/보류 + 리뷰
9. 입사: `application_hire` view 재사용

### 테스트·품질 상태

- **Phase C 신규 테스트 27개** 모두 통과 (기존 678 + Phase C 27 = 705 passed)
- ruff/django check 클린
- Migrations 최신까지 적용됨 (0005)

### 운영 DB 주의

Phase C는 **운영 DB에 마이그레이션 미적용**. 배포 시 `python manage.py migrate projects` 및 `update_stage_labels` 커맨드 수동 실행 필요:

```bash
# 운영 미적용 migration 확인
ssh chaconne@49.247.46.171 \
  "docker exec \$(docker ps -qf name=synco_web) python manage.py showmigrations | grep '\[ \]'"

# 배포 후 적용 (./deploy.sh 내부에서 자동이면 불필요)
ssh chaconne@49.247.46.171 \
  "docker exec \$(docker ps -qf name=synco_web) python manage.py migrate projects"
ssh chaconne@49.247.46.171 \
  "docker exec \$(docker ps -qf name=synco_web) python manage.py update_stage_labels"
```

---

## 7. 다음 세션 — Candidate 메인 페이지 재설계 (Phase D)

### 7.1 왜 Candidate가 다음인가

Project 메인 완성됨 → 자연스럽게 **후보자 쪽**이 다음 중심. 특히:
- 프로젝트 페이지에서 "DB에서 찾기"로 candidates 페이지에 진입하는 경로가 이미 열림. 거기서 후보자 관련 UX가 여전히 구버전이면 새 Project UX와 부조화.
- Candidate 모델 풍부함 (이력서, 댓글, 추천 뱃지, 리뷰, fraud detection 등) → Project와 동등한 수준의 정리 필요.

### 7.2 Candidate 페이지에서 아직 안 된 것들 (임시 목록)

사장님과 본격 브레인스토밍 필요하지만, 현재 관찰되는 출발점들:

1. **Candidate 상세 페이지 구조** — 프로젝트 스타일의 영역 A/B 분리가 적용 가능한지?
2. **후보자 검증 플로우** — 이력서 기반 정보와 컨설턴트가 직접 기록한 사전미팅 메모 등의 통합 뷰
3. **후보자 활동 타임라인** — 어떤 프로젝트에 Application으로 올라갔는지, 각 단계 어디까지 갔는지
4. **여러 프로젝트에 걸친 후보자 관리** — 한 명의 후보자가 동시에 여러 프로젝트 대상이 될 수 있음
5. **후보자 메뉴의 검색·필터링** — 현재는 기본 필터만. JD 매칭 스코어링은 이미 구현됨 — 이걸 어떻게 UX로 노출할지

### 7.3 주요 데이터 주체

- [candidates/models.py](../../candidates/models.py) — Candidate, Resume, ResumeEducation, ResumeCareer, ResumeCertificate, CandidateComment, RecommendationBadge 등
- Identity matching 정책은 email/phone only (name 매칭 금지) — 메모리에 기록됨
- Candidate.name 이 파일명으로 들어간 레코드 일부 존재 (예: "00 다국적 기업 홍보 담당자 리스트.docx") — data_extraction 파이프라인이 실패한 케이스. cleanup 별도 과제.

### 7.4 재사용 가능한 Phase C 자산

- 설계 프레임워크 (프로젝트 레벨/후보자 레벨, 방법 분기, 판정 기준)
- 영역 A/B 레이아웃 패턴
- subagent-driven-development 실행 방법 (본 세션에서 18 Task 완료 증명됨)
- ruff format + CSS class 검증 체크리스트 (첫 번째 플랜에서 놓친 것들)

---

## 8. 다음 세션 재개 지침

### 8-1) 이 문서 먼저 확인

```bash
cat docs/session-handoff/2026-04-19-phase-c-complete.md
```

### 8-2) 현재 상태 확인

```bash
# 브랜치·변경
git status
git log --oneline -30

# 테스트
uv run pytest -q

# 린트
uv run ruff check .

# Django 체크
uv run python manage.py check

# 서버 띄우기
./dev.sh
```

### 8-3) 스모크 테스트 (Phase C 동작 확인)

브라우저에서 `/projects/` → 프로젝트 클릭 → 상세 페이지:
- 영역 A 서칭 도구 (DB 버튼 + 4개 플레이스홀더) 노출
- 영역 A 이력서 배치 제출 (후보자 없으면 빈 상태 메시지)
- 영역 B 후보자 카드에 7단계 진행바 (서칭 제외, 접촉부터)
- 각 단계 카드에서 단계별 전용 파티얼 (폼/버튼) 렌더

### 8-4) Candidate 재설계 착수

첫 메시지 제안:

```
Phase D 착수 — Candidate 메인 페이지 재설계.
docs/session-handoff/2026-04-19-phase-c-complete.md §7 먼저 읽고 컨텍스트 잡은 뒤,
Project 재설계 때 썼던 설계 프레임워크(프로젝트 레벨/후보자 레벨, 판정 기준,
방법 분기)를 Candidate에 어떻게 적용할지 brainstorming 부터.
```

이렇게 지시하면 자동으로 brainstorming 스킬이 발동하고 Project Phase C처럼 진행됨:
1. 사장님과 요구사항 문답 → 설계 문서
2. writing-plans 로 구현 계획 → 플랜 문서
3. subagent-driven-development 로 실행 → 각 Task 구현+리뷰

---

## 9. 마지막 주의사항

- **배포 미수행**: 26 커밋이 origin/main보다 앞서있지만 아직 push/deploy 안 함. 사장님이 `./deploy.sh` 지시해야 운영에 반영됨.
- **커밋 정책**: "git commit은 전체가 기본" — Phase C 내부에서는 task별 커밋이 자연스러운 단위라서 분리했음. Phase D도 동일 전략.
- **영향 범위**: Phase C는 프로젝트 상세 페이지 + 일부 candidates 페이지(검색 컨텍스트 모드). 대시보드, Reference, 포스팅 편집 등 다른 화면은 무관.
- **이 세션의 에이전트 호출**: 18 Task × 3-agent 리뷰 + 수정자 다수 = 수십 회. 모두 foreground 순차 실행. 재현 필요 시 subagent-driven-development 스킬의 같은 패턴 사용.
