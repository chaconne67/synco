---
date: 2026-04-13
status: draft-v3
topic: taste-to-ship (tts)
type: workflow design spec
---

# taste-to-ship (tts) — End-to-End AI Build Workflow

> **v3 변경사항 (2026-04-13):**
> - Stage 1b **User Workflow Mapping** 추가 (사용자 관점 실제 업무 프로세스 설계)
> - Stage 1e **existing/new 분기 제거** → idempotent ensure로 통일
> - **synco 특정 17단계 skeleton 제거** → tech-stack-driven generic baseline
> - **Stage 4.5 제거** → 모든 preflight를 Stage 1f로 흡수
> - **Stage 6 Deploy + Gate Pre-Deploy 제거** → tts는 Stage 5에서 종료, 배포는 사용자 수동
> - Human touchpoint **2개 → 1개** (Stage 1 단일 sitting만)
> - Zombie check에 plan-forge-batch의 판단 기준 "다음 세션 실행/테스트가 실패하는가?" 흡수 + git stash 전략

> *Choose your taste, I'll do the rest.*

SaaS 웹 애플리케이션을 **아이디어에서 구현 완료까지** 하나의 워크플로우로 연결하는 메타-오케스트레이터. 빈 디렉토리든 기존 레포든 동일한 idempotent 워크플로우로 처리한다. 사용자의 인간 개입을 **Stage 1 통합 인터뷰 단 한 번**으로 한정하고, 그 이후 전 과정을 **세션 체이닝 기반 자동 실행**으로 처리한다. 배포는 tts 범위 밖 — 사용자가 완성된 코드를 리뷰한 뒤 수동 실행한다 (`deploy.sh`는 미리 잘 준비됨).

## Motivation

### 해결하려는 4가지 문제

1. **설계 공백으로 인한 경로 의존성**
   현재 워크플로우(office-hours → brainstorming → 구현 계획서 초안 → 태스크 분할 → plan-forge-batch)의 "구현 계획서 초안" 단계에서 UI/UX 품질, 데이터 모델, 인증·권한, 기능 간 연계 등이 충분히 검토되지 않는다. 이 공백은 구현 이후에 드러나 수정 비용이 폭발한다. 특히 **디자인 결정**은 모든 화면에 퍼지고 나면 리팩토링이 거의 불가능하므로, 결정 시점이 "사후 리뷰"에서 **"구현 이전 승인"**으로 앞당겨져야 한다.

2. **사용자 관점 업무 프로세스 설계의 부재**
   기존 워크플로우는 "유스케이스 3~5개" 수준에서 멈춘다. 실제 사용자가 링크를 타고 들어와서 첫 화면에서 무엇을 할 수 있고, 각 액션의 반응과 알림은 어떻게 되고, 업무가 어떤 단계로 진행되며, 무엇을 할 수 없는지 같은 **구체적인 업무 프로세스**가 인테이크에서 잡히지 않는다. 이것이 **프로덕트를 만드는 근본 목적**인데도. 결과적으로 구현 이후에 "이 화면에서는 이게 되어야 하는데 안 되네"가 반복된다.

3. **장시간 작업에서의 컨텍스트 오염**
   아이디어에서 구현 완료까지 전 과정을 한 세션에서 돌리면 컨텍스트가 포화되어 hallucination, 무한 루프, 엉뚱한 방향 탐색 같은 증상이 누적된다. `plan-forge-batch`가 구현 단계에서 해결한 "세션 경계로 컨텍스트 격리" 원리를 **워크플로우 전체 레벨에서 재적용**해야 한다.

4. **사용자 개입의 산발성**
   현재는 중간중간 사용자에게 질문이 튀어나와 맥락 전환 비용이 크다. 사용자는 "중간에 한참 알아서 진행해놓고 어떻게 하냐고 물어보면 뭘 물어보는지 몰라서 또 물어보고 왔다 갔다" 하는 상황을 겪는다. **모든 인간 개입을 앞단 한 자리에 모아야** 한다.

### 핵심 통찰

**사용자의 taste가 확정되면 — 제품 개념, 디자인 방향, 아키텍처 초안, 승인된 목업 — 나머지는 확산(diffusion) 과정으로 자동화 가능하다.** 노이즈에서 형상이 드러나는 diffusion 모델처럼, taste가 seed/prompt가 되어 점진적으로 구체화된 최종 제품으로 수렴한다.

---

## Goals

- **G1.** 아이디어 → 구현 완료를 단일 워크플로우 스킬로 연결
- **G2.** 사용자 인간 개입을 **Stage 1 통합 인터뷰 단 한 번**으로 한정
- **G3.** 경로 의존성이 있는 결정(디자인 룩앤필, 브랜드 톤, 모듈 경계, 사용자 업무 프로세스)을 **사용자 승인 후에만** 진행
- **G4.** **사용자 관점 업무 프로세스**를 인테이크 단계에서 구체적으로 캡처하여 모든 하위 단계의 source of truth로 삼음
- **G5.** 전 과정을 세션 체이닝으로 분할하여 컨텍스트 오염 방지
- **G6.** `plan-forge-batch`의 엔진 로직을 재사용 가능한 라이브러리로 추출
- **G7.** 동적 세션 분할 계획으로 프로젝트 규모에 적응
- **G8.** 기존 `plan-forge-batch`는 유지하고 새 스킬을 병존시켜 점진적 전환
- **G9.** **빈 디렉토리든 기존 레포든 동일한 idempotent 워크플로우**로 처리 (분기 없음)
- **G10.** 구현 시작 전에 **환경 준비 상태를 완전 검증**하여, 자동 실행 단계에서 환경 문제로 중단되지 않도록 보장

## Non-Goals

- **NG1.** 완전 무인 실행 (사용자 개입 0건). Stage 1 인터뷰는 사람이 반드시 한다.
- **NG2.** 예술적 디자인 자동 생성. 디자인은 **기능적 UX 품질**을 목표로 하며, 사용자 승인 없이 브랜드 정체성을 결정하지 않는다.
- **NG3.** 기존 `plan-forge-batch` 스킬의 즉시 폐기. 새 스킬과 병존하며 검증 후 삭제 여부를 결정한다.
- **NG4.** 다른 언어/프레임워크 지원. 현재 타겟은 Django + HTMX + Postgres 스택의 SaaS 웹 앱이다. 다른 스택은 추후 확장.
- **NG5.** 분산 실행. 로컬 단일 머신 기반으로 작동한다.
- **NG6.** 좀비 프로세스의 **무조건 자동 kill**. 파괴적 동작 전에 사용자 확인을 요구한다 (`/careful` 정신).
- **NG7.** **배포 자동화.** tts는 구현 완료까지만 책임지고, 배포는 사용자가 최종 리뷰 후 수동 실행한다. `deploy.sh`를 잘 준비하는 것이 tts의 몫, 실행하는 것은 사용자의 몫.
- **NG8.** 기존 파일 덮어쓰기. idempotent ensure는 **없는 파일만 생성**하고 있는 파일은 건드리지 않는다.

---

## Core Principles

| 원칙 | 적용 |
|---|---|
| **User workflow is the source of truth** | 모든 설계 결정은 "사용자가 실제로 이 프로덕트로 무엇을 하는가"에서 출발. Stage 1b가 이 원천을 만듦 |
| **Path-dependency prevention** | 경로 의존성 있는 결정은 Stage 1에서 사용자 승인 후 확정 |
| **Context isolation via session chaining** | 모든 자동 실행 단위는 별도 세션. 상태는 파일시스템으로 전달 |
| **Human front-loading** | 인간 개입은 워크플로우 앞단 한 자리에 완전히 몰아서 끝. 중간 재호출 없음 |
| **Dynamic session planning** | Intake 이후 session-plan을 자동 생성하고 단계 사이에 재평가 |
| **Fault isolation via module boundaries** | 태스크는 architecture 문서의 모듈 경계를 절대 넘지 않음 |
| **Forge everything** | 설계 문서, 태스크 문서, 구현 계획 모두 adversarial review(담금질) 통과 |
| **Engine/content separation** | batch 엔진(세션 체이닝, 진행 추적)과 콘텐츠(담금질·구현·점검)를 분리 |
| **Environment verified before autonomy** | Stage 1 종료 전에 환경이 완전히 준비되어 있어야 함. "다음 세션 실행/테스트가 실패할 자원"이 있으면 진행 금지 |
| **Idempotent ensure, never overwrite** | 파일 생성은 없으면 만들고 있으면 건드리지 않음. 프로젝트 상태 분기 없음 |
| **Destructive ops require consent** | 좀비 kill, lock 파일 제거, 컨테이너 삭제 등 파괴적 동작은 사용자 확인 후 실행 |
| **Preserve in-progress work** | 환경 정리 시 uncommitted 변경은 `git stash`로 보존, 절대 버리지 않음 |
| **Deploy is user's final act** | tts는 구현·점검까지만 책임. 배포는 사용자가 최종 리뷰 후 수동 실행 |

---

## User Involvement Boundary

### 인간 접촉 포인트 (1개)

| 포인트 | 성격 | 소요 시간 | 이유 |
|---|---|---|---|
| **Stage 1: Intake** (필수) | 인터랙티브 인터뷰, 1 sitting | 1~2시간 (6개 sub-stage) | 제품 개념·사용자 업무 프로세스·디자인 룩앤필·아키텍처 제약은 머릿속에만 있음. 질문으로만 꺼낼 수 있음 |

**배포는 tts 범위 밖**이다. tts는 Stage 5(Implementation) 종료 시점에서 끝난다. 사용자는 완성된 코드를 원하는 시점에 리뷰하고, 준비된 `deploy.sh`를 수동으로 실행한다.

### 자동화 대상 (중간 개입 없음)

- 설계 문서 초안 작성
- 설계 담금질
- 태스크 분할
- 태스크 담금질
- 구현 + 구현 점검

**원칙:** Stage 1 종료 시점에 commit된 `intake/` 번들(+ 필요 시 idempotent ensure된 skeleton 파일)이 사용자 taste의 최종본이다. 이후 단계는 이 번들을 seed로 받아 실행한다. 중간에 사용자에게 추가 질문을 하지 않는다.

### Stage 1 내부 인터랙션 포인트 (한 sitting 안)

Stage 1 sitting 동안 사용자는 다음 지점에서 응답한다. 모두 "한 자리"에서 연속으로 진행된다:

| 시점 | 종류 | 내용 |
|---|---|---|
| 1a | 인터뷰 | office-hours 질문 시퀀스 (제품 개념) |
| 1b ⭐ | **상세 설계** | 사용자 업무 프로세스 매핑 (entry/actions/reactions/notifications/restrictions) |
| 1c | 선택 | 브랜드 톤, 색 방향, 참고 사이트 |
| 1d | **승인** | 목업 variant 선택 (workflow 기반 주요 화면) |
| 1e | 확인 | 모듈 목록·의존성·기술 스택 |
| 1f-1 | 대화 | 외부 서비스·DB 구성·운영 인프라 |
| 1f-3 | **승인** | 좀비·stale 자원 발견 시 kill 승인 (git stash 확인 포함) |

---

## Pipeline Overview

```
[HUMAN, 1 sitting — 1~2 hours]
Stage 1: Intake ─────────────────────────────────────────┐
  1a. Product Brief          (/office-hours)             │
  1b. User Workflow Mapping  ⭐ (interactive)            │
      사용자 업무 프로세스: entry → actions → reactions  │
      → notifications → next → restrictions              │
  1c. Design Direction       (design-consultation)       │ Session chain
  1d. Visual Approval        (ui-mockup upgraded) ⭐     │ (each sub-stage
      workflow 기반 주요 화면 mockup + 승인             │  = 1 session)
  1e. Architecture Sketch    (brainstorming)             │
  1f. Environment Readiness  ⭐ (unified, idempotent)    │
      - 1f-1 Infrastructure intake (interactive)         │
      - 1f-2 Static env check (auto, full preflight)     │
      - 1f-3 Zombie & lock check                         │
             (auto + user consent + git stash)           │
      - 1f-4 Idempotent skeleton ensure                  │
             (tech-stack baseline, 있으면 skip)           │
                                                          │
  → intake/ bundle + (ensure된 skeleton) committed ──────┘
  ═════════════════ 이후 100% 자동 ═════════════════

[AUTO]
Stage 1.5: Session Planning
  - Read intake bundle
  - Light drift check (포트/docker/git HEAD)
  → session-plan.json

Stage 2: Design Package (9 docs)
  2a. Draft generation (00~07, 99)
  2b. design-forge-batch (개별 + 쌍 담금질)
  2c. Re-plan (session-plan 갱신)

Stage 3: Task Split
  99-agreed.md + 01-architecture.md → t01..tN + plan.md

Stage 4: Task Forging
  task-forge-batch (태스크별 담금질)

Stage 5: Implementation
  impl-forge-batch (구현 + 점검)

═══════════════════════════════════════════════════
tts 종료. 사용자 수동 리뷰 후 ./deploy.sh 직접 실행.
═══════════════════════════════════════════════════
```

---

## Stage 1: Intake (Human, 1 Sitting)

통합 인터뷰를 통해 **사용자 taste의 최종본**을 생성한다. 내부적으로는 sub-stage마다 별도 세션으로 체이닝되지만, 사용자 경험상 연속된 인터뷰다.

### 1a. Product Brief

- **실행 스킬:** `/office-hours`
- **입력:** 사용자 아이디어 (구두)
- **출력:** `docs/intake/{project}/product-brief.md`
- **내용:**
  - 제품 개요, 문제 정의, 타겟 사용자
  - 가치 제안 (왜 이 제품인가)
  - 핵심 유스케이스 3~5개 (고수준)
  - 성공 지표
  - 경쟁/차별화 포인트

### 1b. User Workflow Mapping ⭐

**가장 근본적인 sub-stage.** 제품을 만드는 목적 자체인 "사용자가 실제로 이걸로 무엇을 하는가"를 구체적으로 잡는다. 이후 모든 설계 결정(1c 디자인, 1d 목업, 1e 아키텍처)의 **source of truth**가 된다.

- **실행 스킬:** 신규 인터랙티브 로직 (tts orchestrator 내부)
- **입력:** product-brief.md
- **출력:** `docs/intake/{project}/user-workflows.md`

- **캡처하는 것:** 각 주요 사용자 여정(3~7개)에 대해 아래 7가지 차원을 구체적으로 기록:

  1. **Entry & Context** — 사용자가 어떻게 이 여정에 진입하는가 (링크 클릭, 대시보드 이동, 알림 등), 당시 상황·목표·멘탈 모델
  2. **First Screen & State** — 진입 직후 보이는 화면, 초기 상태(zero state/loading/populated)
  3. **Available Actions** — 이 화면에서 사용자가 **할 수 있는** 행동 목록 (버튼, 링크, 입력)
  4. **Required Actions** — 사용자가 **반드시 해야 하는** 행동 (필수 입력, 승인 등)
  5. **Reactions & Side Effects** — 각 행동에 대한:
     - UI 피드백 (상태 변화, 로딩, 에러)
     - 시스템 응답 (DB 변경, 파일 생성)
     - 알림 (이메일, 인앱, 웹훅, 브라우저 푸시)
     - 타 사용자/시스템에 미치는 영향
  6. **Next Steps & Paths** — 행동 이후 사용자가 이동하는 곳. happy path + 주요 alternate paths
  7. **Restrictions & Blockers** — 사용자가 **할 수 없는 것**:
     - 권한 미달로 차단되는 경우
     - 선행 조건 미충족으로 차단되는 경우 (예: 결제 미완료)
     - 비즈니스 룰로 차단되는 경우
     - 시스템 상태로 차단되는 경우 (예: rate limit)

- **기록 형식:** 각 여정을 다음 구조로:

  ```markdown
  ## Journey: {이름}

  ### Context
  누가, 언제, 왜 이 여정을 시작하는가.

  ### Preconditions
  이 여정을 시작할 수 있는 조건.

  ### Steps
  1. [Entry] 사용자가 X 링크를 클릭
     - First screen: Y 화면
     - Initial state: Z
  2. [Action] 사용자가 A 버튼을 누름
     - UI: 로딩 → 성공 메시지
     - System: B 레코드 생성, C 이벤트 발행
     - Notification: 관리자에게 이메일
     - Next: D 화면으로 이동
  3. ...

  ### Alternate Paths
  - If X fails: ...
  - If user has no permission: ...

  ### Restrictions
  - User CANNOT ...
  - Blocked when ...

  ### Success Criteria
  이 여정이 성공적으로 완료되었다고 판단하는 기준.
  ```

- **프로세스:**
  1. product-brief에서 유스케이스를 끄집어낸 뒤, 각 유스케이스를 **완전한 여정**으로 확장하도록 사용자에게 질의
  2. 한 여정씩 7차원을 채워나감
  3. 여정 간 연결(한 여정의 완료가 다른 여정의 시작을 트리거하는 경우)도 기록
  4. 사용자가 최종 승인

**이 단계 없이 Stage 2로 진행 금지.** workflow 미승인 상태에서 디자인이나 아키텍처를 만들면 결과가 사용자 실제 업무와 어긋난다.

### 1c. Design Direction

- **실행 스킬:** `design-consultation` (gstack)
- **입력:** product-brief.md + user-workflows.md + 사용자 선호 질의
- **출력:** `docs/intake/{project}/design-direction.md`
- **내용:**
  - 브랜드 톤 (professional, playful, minimal, technical 등)
  - 색감 방향 (primary, accent, 중립 팔레트)
  - 타이포그래피 (Pretendard 기본, 대안 제안)
  - 참고 사이트 3~5개
  - 피하고 싶은 시각적 요소

### 1d. Visual Approval ⭐

**경로 의존성을 앞단에서 끊는 단계.** 사용자 workflow의 핵심 화면을 mockup으로 구체화하고 사용자가 직접 승인한다.

- **실행 스킬:** `ui-mockup` (업그레이드판, Gemini Nano Banana Pro 기반)
- **입력:** product-brief.md + **user-workflows.md** + design-direction.md
- **출력:**
  - `docs/intake/{project}/approved-mockups/*.png` (workflow의 주요 화면 3~7개)
  - `docs/intake/{project}/approved-mockups/component-library.png` (버튼·카드·네비)
  - `docs/intake/{project}/design-approved.md` (승인 근거, 피드백 정리)
- **프로세스:**
  1. user-workflows의 각 여정에서 **주요 화면 식별** (First Screen 및 중요 상태 전이 화면)
  2. 각 화면 variant 3~5개 병렬 생성 (Gemini Nano Banana Pro)
  3. 비교 보드 표시
  4. **사용자가 직접 선택** (일괄, 변형 승인 가능)
  5. 컴포넌트 라이브러리 샘플 생성
  6. 사용자가 최종 승인

### 1e. Architecture Sketch

- **실행 스킬:** `superpowers:brainstorming` (인터랙티브)
- **입력:** product-brief.md + **user-workflows.md** + 기존 코드베이스 스캔 결과
- **출력:** `docs/intake/{project}/architecture-sketch.md`
- **내용:**
  - 모듈 목록 초안 (이름, 책임 범위) — user-workflows를 지원할 수 있도록 설계
  - 모듈 간 의존성 방향 (DAG)
  - 기술 스택 확인 (기본: Django 5.2 + HTMX + Postgres)
  - 외부 통합 목록 (결제, 메일, 인증 등)
  - 기존 코드베이스와의 관계 (있다면: 어떤 기존 모듈이 재사용되는지, 어떤 게 대체되는지)

**빈 디렉토리여도, 기존 레포여도 같은 방식으로 작성된다.** 차이는 "기존 코드베이스 섹션이 비어있는가"뿐이다.

### 1f. Environment Readiness ⭐

**마지막 sub-stage. 사용자가 자리에 있는 마지막 기회.** 이 지점을 지나면 자동 실행이 시작되어 개입할 수 없다.

**핵심 원칙: unified + idempotent.** 프로젝트 상태(빈 디렉토리 / 기존 레포 / 혼합)를 구분하여 분기하지 **않는다**. 대신 모든 작업을 **idempotent ensure**로 수행한다: 필요한 자원이 없으면 생성, 있으면 건드리지 않는다. 이렇게 하면 한 가지 로직이 모든 경우를 자연스럽게 처리한다.

#### 1f-1. Infrastructure Intake (인터랙티브)

- **실행 스킬:** 신규 대화형 로직 (tts orchestrator 내부)
- **입력:** product-brief.md + user-workflows.md + architecture-sketch.md
- **출력:** `docs/intake/{project}/infrastructure-plan.md`
- **대화 내용:**
  - 외부 서비스 목록 확정 (결제·메일·OAuth·AI API 등)
  - 각 서비스의 credential 취득 계획 (이미 있음 / 지금 발급 / 나중에)
  - DB 구성: 로컬 Postgres 컨테이너 / 운영 DB 연결 / 둘 다
  - 운영 인프라 계획 (도메인, SSL, 배포 타겟 — 배포는 tts 범위 밖이지만 `deploy.sh` 준비에 필요)
  - 운영 모니터링·로깅 전략

#### 1f-2. Static Environment Check (자동)

모든 체크는 **read-only** — 파괴적 동작 없음. 파일·프로세스·네트워크 상태만 관찰한다.

| 검사 항목 | 방식 | 통과 조건 |
|---|---|---|
| Python 버전 | `python --version` | ≥ 3.13 |
| uv | `uv --version` | 존재 |
| Git | `git --version` | 존재 |
| Docker 데몬 | `docker info` | 동작 중 |
| Docker Compose | `docker compose version` | v2 이상 |
| Red-team CLI | `which codex`, `which gemini` | 최소 1개 존재 (없으면 Agent 폴백 경고) |
| API 키 | `$OPENAI_API_KEY`, `$GEMINI_API_KEY` | 최소 1개 존재 |
| Disk space | `df -h .` | 프로젝트 경로에 1GB+ 여유 |
| Django 설치 (`manage.py` 있는 경우만) | `uv run python -c "import django; print(django.VERSION)"` | ≥ 5.2 |
| Migration 상태 (`manage.py` 있는 경우만) | `uv run python manage.py makemigrations --check --dry-run` | 미생성 migration 없음 |
| DB 접속 (DB 설정이 있는 경우만) | `docker compose ps` + `pg_isready` | 접속 가능 |
| `.env` 키 대조 (`.env.example` 있는 경우만) | `.env.example` ∩ `.env` | 필수 키 모두 존재 |

**조건부 검사:** "있는 경우만" 표시된 항목은 현재 프로젝트 상태에 따라 skip 가능. 빈 디렉토리면 Django 관련 체크는 skip되고, 대신 1f-4에서 설치·생성된다.

#### 1f-3. Zombie & Lock Check ⭐ (자동 + 사용자 확인)

**판단 기준 (from plan-forge-batch):**

> **"이 자원이 남아있으면 다음 세션의 실행(`uv run pytest`, `manage.py runserver`, `docker compose up` 등)이 실패하는가?"**
> **Yes → 정리. No → 무시.**

이 기준을 적용하지 않으면 false positive가 쌓여서 사용자에게 불필요한 확인을 자주 요청하게 된다. 예를 들어 포트 9999가 점유되어 있어도 우리가 9999를 쓸 일이 없으면 무시한다.

| 검사 대상 | 확인 방법 | 판단 기준 |
|---|---|---|
| **필요한 포트 점유** (8000, 5432, 8080 등 infrastructure-plan에서 쓸 포트만) | `lsof -i:$PORT` 또는 `ss -tlnp` | 점유 중이면 실행 실패 확실 → 사용자 확인 후 kill. **다른 포트로 회피 금지** (CLAUDE.md 포트 정책) |
| **Orphan Django runserver** | `pgrep -af "manage.py runserver"` + ppid 체크 | 포트 8000을 쥐고 있으면 정리 대상. 아니면 무시 |
| **Orphan claude CLI 세션** (이전 tts 잔재) | `pgrep -af "claude -p"` + ppid 체크 | 파일/git 경합 위험 있으면 정리. 아니면 무시 |
| **Stale lock 파일** | `.claude/*.lock`, `*.pid`, `/tmp/*.pid` | 파일 내 PID 검증 → 소유자 죽었으면 **자동 제거** (안전), 살아있으면 경고 |
| **DB 커넥션 풀 고갈** | `psql -c "SELECT count(*) FROM pg_stat_activity"` | max_connections 근접 시 idle-in-tx/오래된 idle 정리 |
| **Orphan Docker 컨테이너** | `docker ps -a` + 이름/레이블 | 우리가 쓸 컨테이너 이름과 충돌하는 것만 → 사용자 확인 후 `docker rm` |
| **`/tmp/forge-*` 임시 파일** | `ls /tmp/forge-*` | 이전 배치의 temp 파일 → 자동 제거 (안전) |
| **`.git/index.lock`** | `ls .git/index.lock` | 살아있는 git 프로세스 확인, 없으면 자동 제거 |

**Uncommitted changes 처리 (from plan-forge-batch):**

```bash
if [ -n "$(git status --porcelain)" ]; then
  git stash push -m "tts: in-progress work preserved before auto stages $(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi
```

**사용자에게 반드시 알림**: "당신의 작업 중 변경을 stash로 보존했습니다. Stage 종료 후 `git stash pop`으로 복원 가능합니다."

**조치 원칙:**

| 상황 | 동작 |
|---|---|
| 소유자 PID가 이미 죽은 stale lock 파일 | **자동 제거** (안전) |
| `/tmp/forge-*` 임시 파일 | **자동 제거** (안전) |
| Uncommitted 변경 사항 | **자동 git stash** (보존, 절대 버리지 않음) + 사용자 알림 |
| 필요한 리소스를 쥐고 있는 살아있는 프로세스 | **식별 + 리포트**, 사용자 확인 후 kill |
| 정체 불명 프로세스 (사용자도 모르겠다 답) | **유지**, "수동 점검 필요" 경고 후 진행 거부 |

**게이트 동작:** 1f-3을 통과해야만 1f-4로 진행 가능.

#### 1f-4. Idempotent Skeleton Ensure

프로젝트가 Stage 2 이후 자동 실행을 돌릴 수 있도록 필요한 파일들이 **존재함을 보장**한다. 이미 있는 파일은 건드리지 않는다.

**판단 원칙:** intake에서 결정된 **tech stack**이 skeleton의 shape을 정한다. 기본 타겟(Django + HTMX + Postgres)의 경우 아래 파일들을 ensure한다. 다른 스택은 추후 확장.

**Ensure 대상:** 각 파일에 대해 `[ -f $FILE ] || 생성` 로직 적용. 순서는 의존성 따라.

| # | 파일/디렉토리 | Ensure 조건 | 생성 내용 |
|---|---|---|---|
| 1 | `.git/` | 없으면 | `git init` |
| 2 | `.gitignore` | 없으면 | Python + Django + IDE + Docker 표준 |
| 3 | `pyproject.toml` | 없으면 | `uv init`로 생성 후 infrastructure-plan 기반 deps 추가 |
| 4 | `uv.lock` | 없으면 | `uv sync`로 생성 |
| 5 | `manage.py` + `config/` | 없으면 | `django-admin startproject config .` |
| 6 | `config/settings.py` 수정 | settings이 방금 생성됐을 때만 | DATABASES (Postgres), INSTALLED_APPS, TIME_ZONE, LANGUAGE_CODE 등 tech-stack 기본값 적용 |
| 7 | `docker-compose.yml` | 없으면 | Postgres 16 service + tech-stack에 맞는 서비스들 |
| 8 | `.env.example` | 없으면 | infrastructure-plan의 env vars 목록 기반 생성 |
| 9 | `.env` | 없으면 | `.env.example` 복사 (값은 비어있음, 사용자가 채움) |
| 10 | `dev.sh` | 없으면 | 개발 서버 실행 스크립트 |
| 11 | `deploy.sh` | 없으면 | 배포 스크립트 템플릿 (infrastructure-plan의 배포 타겟 반영) |
| 12 | `CLAUDE.md` | 없으면 | 프로젝트 메모리 템플릿 (product-brief 요약 포함) |
| 13 | `README.md` | 없으면 | 제품명 + 한 줄 설명 + 개발 시작 가이드 |
| 14 | Tailwind 설정 (`package.json`, `tailwind.config.js`) | 없으면 + infrastructure-plan이 Tailwind 포함 | 기본 설정 + Pretendard font |
| 15 | 초기 migration | DB 접속 가능 + migrations 테이블 없음 | `uv run python manage.py migrate` |
| 16 | 첫 commit | 1~15 중 하나라도 새로 생성됐으면 | `git add -A && git commit -m "chore: tts skeleton ensure"` |

**핵심 특성:**
- 빈 디렉토리: 1~16 모두 실행됨 → 완전한 skeleton
- 기존 synco 같은 레포: 1~14 대부분 skip (이미 있음), 15~16도 skip (최신 상태)
- 부분 설정된 레포: 없는 것만 채움

**주의:** **Django app(`python manage.py startapp`)은 여기서 만들지 않는다.** App은 Stage 5 구현 시 태스크로 생성된다. 1f-4가 만드는 것은 "Stage 2~5가 문서/코드를 쓸 공간"이다.

**검증 (ensure 후):**
- `uv run python manage.py check` (경고 허용)
- `pytest --collect-only` (테스트 수집 가능 확인)

실패 시 해당 ensure 단계 재시도 또는 사용자에게 알림.

### Intake 번들 최종 구조

```
docs/intake/{YYYYMMDD}-{project}/
├── product-brief.md
├── user-workflows.md           ⭐ 1b 산출물 (모든 설계의 source of truth)
├── design-direction.md
├── design-approved.md
├── approved-mockups/
│   ├── {screen-1}.png
│   ├── {screen-2}.png
│   ├── ...
│   └── component-library.png
├── architecture-sketch.md
├── infrastructure-plan.md      ⭐ 1f-1 산출물
├── environment-check.md        ⭐ 1f-2/1f-3 스냅샷
└── zombie-cleanup-log.md       ⭐ 1f-3 조치 이력 (git stash ref 포함)
```

프로젝트 루트에는 1f-4가 ensure한 skeleton 파일들이 존재한다 (없었던 파일만 생성됨).

모든 파일은 git commit된다. 이 커밋이 **"이후 자동 실행"의 트리거**다.

---

## Stage 1.5: Session Planning (Auto)

### 목적

Intake 번들을 입력으로 받아, 이후 stage들이 어떻게 세션 단위로 쪼개질지 **동적으로 계획**한다. 정적 분할로는 프로젝트 규모에 적응할 수 없다. 동시에 **환경 drift**(Stage 1f 이후 좀비 재발생 등)를 가볍게 재검증한다.

### 입력

- Intake 번들 전체 (product-brief, architecture-sketch, infrastructure-plan, environment-check, approved-mockups)

### 처리

1. **설계 문서 수 결정** — 기본 9종, 프로젝트 규모에 따라 일부 통합 가능 (소규모에서 `06-workflow-map`을 `00-overview`에 통합 등)
2. **태스크 수 N 추정** — `architecture-sketch.md`의 모듈 개수 + 복잡도 기반
3. **각 논리 단위의 복잡도 분류** — 소/중/대
4. **세션 분할 결정:**
   - 소: 1 unit = 1 session
   - 중: 1 unit = 1 session (watchdog 감시)
   - 대: 1 unit = 2~3 sessions (의도적 분할)
5. **의존성 그래프 생성**
6. **Light drift check** — Stage 1f 종료 후 환경이 바뀌었을 수 있음:
   - 핵심 포트(8000, 5432) 재점검
   - Docker 데몬 살아있음
   - Git HEAD가 intake commit 뒤에 있음 (오염 없음)
   - 문제 발견 시 `session-plan.json`에 `blockers` 기록, 자동 진행 중단 후 사용자 재호출 대기

### 출력

`docs/forge/{project}/session-plan.json`

```json
{
  "schema_version": "1.0",
  "project": "{project}",
  "created_at": "2026-04-12T...",
  "stages": [
    {
      "id": "2.1",
      "type": "design-draft",
      "sessions": [
        {"unit": "00-overview", "complexity": "소", "estimated_minutes": 5},
        {"unit": "01-architecture", "complexity": "중", "estimated_minutes": 10},
        {"unit": "02-design-system", "complexity": "중", "estimated_minutes": 10},
        {"unit": "03-ux-flows", "complexity": "중", "estimated_minutes": 10},
        {"unit": "04-data-model", "complexity": "중", "estimated_minutes": 10},
        {"unit": "05-auth-rbac", "complexity": "중", "estimated_minutes": 10},
        {"unit": "06-workflow-map", "complexity": "소", "estimated_minutes": 5},
        {"unit": "99-implementation-plan", "complexity": "대", "estimated_minutes": 20}
      ]
    },
    {
      "id": "2.2",
      "type": "design-forge",
      "sessions": [
        {"unit": "00-overview", "complexity": "소"},
        {"unit": "01-architecture", "complexity": "대"},
        ...
      ]
    },
    {
      "id": "3",
      "type": "task-split",
      "sessions": [{"unit": "split", "complexity": "중"}]
    },
    {
      "id": "4",
      "type": "task-forge",
      "sessions": [],
      "deferred": true,
      "deferred_reason": "태스크 수 N은 Stage 3 종료 후 확정. 재평가 시 채워짐."
    },
    {
      "id": "5",
      "type": "impl",
      "sessions": [],
      "deferred": true,
      "deferred_reason": "태스크 수 N은 Stage 3 종료 후 확정. 재평가 시 채워짐."
    }
  ],
  "deps": {
    "2.2": ["2.1"],
    "3": ["2.2"],
    "4": ["3"],
    "5": ["4"]
  }
}
```

### 재평가 지점 (Re-planning)

세션 계획은 **단계 간에 갱신**된다:

| 재평가 지점 | 무엇을 갱신하는가 |
|---|---|
| Stage 2 종료 후 | 실제 설계 복잡도 → Stage 3 태스크 수 예측 |
| Stage 3 종료 후 | 실제 태스크 수 N 확정 → Stage 4, 5 세션 수 확정 |
| Stage 4 종료 후 | 담금질 결과 복잡도 → Stage 5 세션 분할 조정 |

재평가 로직은 `session-planner` 스킬이 각 단계 종료 시 자동 호출된다.

### 폭주 방지 (Watchdog)

`_forge-batch-engine`의 watchdog이 각 세션의 journal mtime과 CPU를 감시하여:
- hang 감지 시 kill + respawn
- 지속 시간이 임계치 초과 시 "세션 너무 큼" 경고를 `session-plan.json`에 기록
- 다음 재평가 때 해당 unit을 더 잘게 분할

---

## Stage 2: Design Package (Auto)

### 역할 재정의

Stage 2는 **디자인 결정을 하는 곳이 아니다.** Intake에서 이미 승인된 인풋을 **형식화(formalize)**하는 곳이다.

### 9-Doc Design Package

```
docs/designs/{YYYYMMDD}-{project}/
├── 00-overview.md            제품 개요, 목표, 성공 지표, 유스케이스
├── 01-architecture.md        ⭐ 모듈 경계, 인터페이스, 의존성, fault isolation
├── 02-design-system.md       디자인 시스템 (색·폰트·컴포넌트)
├── 03-ux-flows.md            화면·플로우 (intake의 승인된 목업 기반)
├── 04-data-model.md          엔티티·관계·인덱스·마이그레이션
├── 05-auth-rbac.md           인증, 역할/권한 매트릭스, 테넌시 모델
├── 06-workflow-map.md        사용자 여정, 기능 연계, 상태 전이
├── 07-infrastructure.md      ⭐ 런타임·DB·외부서비스·env vars·배포·CI/CD
└── 99-implementation-plan.md 구현 계획 (태스크는 01의 모듈 경계 준수)
```

### Intake ↔ Design Package 맵핑

| 설계 문서 | Intake 인풋 |
|---|---|
| `00-overview.md` | `product-brief.md` 재구성 |
| `01-architecture.md` | `architecture-sketch.md` 정식 확장 |
| `02-design-system.md` | `design-direction.md` + `approved-mockups/` 시스템화 |
| `03-ux-flows.md` | `approved-mockups/` + `product-brief.md` 플로우 확장 |
| `04-data-model.md` | `architecture-sketch.md` + `product-brief.md` 엔티티 도출 |
| `05-auth-rbac.md` | `product-brief.md` (사용자 역할) + `architecture-sketch.md` |
| `06-workflow-map.md` | `product-brief.md` + `architecture-sketch.md` |
| `07-infrastructure.md` | `infrastructure-plan.md` + `environment-check.md` 형식화 |
| `99-implementation-plan.md` | 위 모두 종합 |

### Stage 2a: Draft Generation

- 각 문서를 **1 session = 1 doc** 원칙으로 작성
- 8 sessions (또는 session-plan에 따라 조정)
- 각 세션은 `superpowers:brainstorming`의 **autonomous 변형** 또는 단순 문서 생성 프롬프트로 실행
- 출력: `{doc}.md` (draft)

### Stage 2b: Design Forging

- 각 draft 문서를 `design-forge-batch`가 담금질
- **담금질 구성 (기본):**
  - **1단계 — 개별 담금질:** 각 문서를 독립 세션에서 담금질 (관점별 깊이 확보). 9개 세션.
  - **2단계 — 쌍(pair) 담금질:** 강한 의존 관계가 있는 문서 쌍을 함께 담금질하여 문서 간 모순 탐지. 모든 조합이 아니라 O(N) 수준으로 제한:
    - `03-data-model` ↔ `05-auth-rbac` (엔티티·권한 일관성)
    - `01-architecture` ↔ `06-workflow-map` (모듈 경계·플로우 일관성)
    - `02-design-system` ↔ `03-ux-flows` (디자인·화면 일관성)
    - `99-implementation-plan` ↔ `01-architecture` (구현·모듈 경계 일관성)
    - `07-infrastructure` ↔ `04-data-model` (DB 설정·스키마 일관성)
    - `07-infrastructure` ↔ `05-auth-rbac` (외부 OAuth·인증 방식 일관성)
    - `07-infrastructure` ↔ `99-implementation-plan` (인프라 준비·구현 순서 일관성)
- 출력: `{doc}-agreed.md` + 센티널 마커
- 통합 검증(9종 모두 한 세션 로드)은 **하지 않는다** — 컨텍스트 부담이 크고 쌍 담금질로 대체 가능

### 01-architecture.md가 뼈대

**가장 중요한 문서.** 반드시 다음을 명시:

- 모듈 목록과 책임 범위 (한 줄 설명 + 상세)
- 모듈 간 의존성 방향 (단방향 DAG, 순환 금지)
- 모듈 간 인터페이스 (API shape, 이벤트, 데이터 구조)
- 각 모듈의 blast radius (버그 발생 시 영향 범위)
- **태스크 분할 규칙:** 한 태스크는 한 모듈 내부 작업만. 모듈 경계를 넘지 않음.

---

## Stage 3: Task Split (Auto)

### 입력

- `99-implementation-plan-agreed.md`
- `01-architecture-agreed.md`

### 처리

- 구현 계획을 **모듈 경계를 따라 분할**
- 한 태스크 = 한 모듈 내부의 일관된 작업 단위
- 태스크 간 의존성 추출
- 각 태스크에 대해:
  - `t{NN}.md` (태스크 상세 — 목적, 변경 대상 파일, 접근 방법, 완료 조건)
  - 모듈 소속 명시
  - 의존 태스크 명시

### 출력

```
docs/forge/{project}/
├── plan.md              # 전체 워크플로우 안내도 (모듈 목록 + 태스크 매핑)
├── t01.md
├── t02.md
├── ...
└── tN.md
```

### 핵심 제약

**태스크 분할 시 `01-architecture-agreed.md`의 모듈 경계를 절대 위반하지 않는다.** 이 제약이 fault isolation을 보장한다. 분할 결과는 Stage 3 종료 시 `session-planner`가 재평가하여 Stage 4, 5의 세션 수를 확정한다.

---

## Stage 4: Task Forging (Auto)

### 처리

- 각 태스크 문서(`t{NN}.md`)에 대해 `task-forge-batch` 실행
- `context` = Intake 번들 + 설계 패키지 9종 agreed
- 각 태스크가 별도 세션에서 담금질
- 출력: `t{NN}-agreed.md` + 센티널 마커

### 왜 UPFRONT 담금질인가

- 설계 패키지가 충실하므로 태스크 간 drift 위험 낮음
- 모든 태스크 계획이 구현 전에 확정되어 Stage 5는 순수 실행
- Stage 5 도중 담금질 실패로 인한 중단 없음
- 재실행 편의성: 구현만 다시 돌릴 수 있음

### 재평가

Stage 4 종료 후, 담금질에서 드러난 복잡도 변화를 반영하여 Stage 5의 세션 분할을 갱신.

---

## Stage 5: Implementation (Auto)

### 처리

- `impl-forge-batch`가 각 태스크에 대해:
  - 1 session: 구현 (subagent-driven-development 패턴)
  - 1 session: 구현 점검 (impl-check)
- 의존성 순서 준수
- 실패 전파 원칙 (상위 실패 → 하위 skip)
- 각 태스크 완료 시 git commit

### 환경 문제에 대한 태도

**"Stage 5에서 환경 문제가 발생하면 intake가 불완전했다"** 가 기본 가정이다. Stage 1f가 모든 환경 검증을 책임지므로, Stage 5에 와서 "DB 접속 실패", "env var 없음", "외부 서비스 credential 누락" 같은 문제가 생기면 이는 복구가 아니라 **학습**의 대상이다:

1. 해당 태스크 **skip + 에러 상세 기록**
2. 나머지 태스크는 의존성 따라 계속 진행
3. 종료 후 리포트에 "Stage 1f에서 누락된 체크 항목" 섹션 생성
4. 다음 버전 tts에서 1f의 검사 항목을 확장

즉 Stage 5는 **preflight를 다시 하지 않는다.** 신뢰하고 실행한다. 실패하면 기록한다.

### `impl-forge-batch` vs 기존 `plan-forge-batch`

`impl-forge-batch`는 기존 `plan-forge-batch`의 **복사본**이다. 차이:

- 담금질 단계 제거 (태스크는 이미 `*-agreed.md` 상태로 들어옴)
- 구현 + 점검만 수행
- 엔진은 `_forge-batch-engine`을 공유

기존 `plan-forge-batch`는 유지되어 담금질-포함 배치가 필요한 다른 워크플로우에서 사용 가능. 충분히 검증된 후 삭제 여부 결정.

---

## Post-tts: Deploy (User Manual)

tts는 Stage 5에서 **끝난다.** 배포는 tts 범위 밖이다.

**사용자가 하는 것:**

1. 완성된 코드 리뷰 (git log, 주요 변경 확인)
2. 로컬 테스트 실행 (`uv run pytest`, 수동 QA)
3. 준비된 `deploy.sh` 수동 실행
4. 운영 확인

**tts가 준비해 놓는 것:**

- `deploy.sh` 스크립트 (infrastructure-plan 기반, 1f-4에서 ensure됨)
- `07-infrastructure.md`의 배포 섹션 (어떤 서버, 어떤 파이프라인, 어떤 검증)
- 모든 태스크별 git commit (`tts(5/tXX): ...`) → 리뷰 용이

**이유:** 배포는 blast radius가 크고 사용자 판단(타이밍, 사전 공지, 롤백 준비)이 필요하다. 자동화의 가치보다 사용자 통제의 가치가 크다.

---

## Skill Architecture

### Layer Diagram

```
┌────────────────────────────────────────────────────────┐
│ taste-to-ship (tts)  ⭐                                │  ← Orchestrator
│ · Stage 1~5 체이닝                                     │
│ · trigger aliases: taste-to-ship, tts, /tts            │
└───────────────┬────────────────────────────────────────┘
                │ invokes
  ┌─────────────┼───────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
  ↓             ↓           ↓          ↓          ↓          ↓          ↓          ↓          ↓
┌──────┐ ┌───────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│office│ │user-      │ │design-  │ │ui-mockup│ │brain-   │ │env-     │ │session- │ │design-  │ │task-    │
│-hours│ │workflow-  │ │consul-  │ │(upgr.)  │ │storming │ │readiness│ │planner  │ │forge-   │ │forge-   │
│      │ │interview  │ │tation   │ │         │ │         │ │(1f)     │ │         │ │batch    │ │batch    │
└──────┘ └───────────┘ └─────────┘ └─────────┘ └─────────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
  1a          1b ⭐       1c          1d          1e          1f ⭐       1.5         2b          4
                                                                 │          │           │           │
                                                                 └──────────┴───────────┴───────────┤
                                                                                                     ↓
                                                                       ┌─────────────────────────────────┐
                                                                       │ _forge-batch-engine  ⭐          │  ← Shared lib
                                                                       │ · session-chaining              │
                                                                       │ · progress-tracking             │
                                                                       │ · watchdog                      │
                                                                       │ · sentinel marker               │
                                                                       │ · dependency analysis           │
                                                                       │ · env cleanup (from plan-forge  │
                                                                       │   -batch: pytest-pass criterion)│
                                                                       └─────────┬───────────────────────┘
                                                                                 │
                                                                                 ↓
                                                                          ┌──────────┐
                                                                          │impl-     │
                                                                          │forge-    │  ← Stage 5
                                                                          │batch     │
                                                                          └────┬─────┘
                                                                               │
                                                                               ↓
                                                                         ┌──────────┐
                                                                         │plan-forge│  ← 기존 유지
                                                                         └──────────┘
```

### 새 스킬 목록

| 스킬 | 역할 | 기반 |
|---|---|---|
| `taste-to-ship` (tts) | 최상위 워크플로우 오케스트레이터 (Stage 1~5 체이닝) | 신규 작성 |
| `_forge-batch-engine` | 세션 체이닝·진행 추적·watchdog·환경 정리 공유 라이브러리 | 기존 `plan-forge-batch`에서 추출 |
| `user-workflow-interview` | Stage 1b 로직: 사용자 업무 프로세스 7차원 인터뷰 | 신규 작성 |
| `env-readiness` | Stage 1f 로직: infrastructure intake + static check + zombie check + idempotent skeleton ensure | 신규 작성 |
| `session-planner` | Intake → session-plan.json 변환 + 재평가 + light drift check | 신규 작성 |
| `design-forge-batch` | 설계 문서 담금질만 (구현·점검 제거). 대상: 설계 패키지 9종 | `plan-forge-batch` 복사 → 구현·점검 제거 |
| `task-forge-batch` | 태스크 담금질만 (구현·점검 제거). 대상: t01~tN, UPFRONT 모드 | `plan-forge-batch` 복사 → 구현·점검 제거 |
| `impl-forge-batch` | 구현 + 점검만 (담금질 제거). 입력: 이미 agreed된 태스크 | `plan-forge-batch` 복사 → 담금질 제거 |

### 업그레이드 대상

| 스킬 | 변경 |
|---|---|
| `ui-mockup` | Gemini Nano Banana Pro 모델 도입 + design-shotgun의 핵심 기능 포팅 (병렬 생성, evolve, serve HTTP 피드백, iterate) |

### 기존 유지

| 스킬 | 상태 |
|---|---|
| `plan-forge` | 유지 (각 batch 스킬이 내부적으로 dispatch) |
| `plan-forge-batch` | 유지 (병존, 나중에 삭제 검토) |
| `office-hours` | 유지 (Stage 1a에서 사용) |
| `design-consultation` | 유지 (Stage 1b에서 사용) |
| `superpowers:brainstorming` | 유지 (Stage 1d에서 사용) |

### 트리거 키워드

`taste-to-ship` 스킬의 `description` 필드에 다음을 모두 포함:

- `taste-to-ship` (정식)
- `tts` (발음 가능한 alias, 원래 text-to-speech 약자지만 여기서는 taste-to-ship)
- `/tts` (slash command 형식)
- `풀 워크플로우 시작` (한국어 자연어)
- `아이디어부터 배포까지` (한국어 자연어)

---

## State Management

### 진실 소스 우선순위

| 우선순위 | 파일 | 용도 |
|---|---|---|
| 1 | 센티널 마커 (agreed 문서 끝 줄) | 완료 판정 |
| 2 | `*-agreed.md` | 합의된 최종본 |
| 3 | `*-rulings.md` | 담금질 판결 (사람이 읽는 서사) |
| 4 | `debate-log.json` | 라운드별 토론 기록 |
| 5 | `forge-progress.json` | 배치 진행 요약 (캐시) |
| 6 | `session-plan.json` | 세션 분할 계획 (캐시) |
| 7 | `workflow-progress.json` | 워크플로우 전체 진행 상태 (캐시) |
| 8 | `environment-check.md` | 환경 검사 스냅샷 (1f-2/1f-3) |
| 9 | `zombie-cleanup-log.md` | 파괴적 동작 이력 (감사 추적, git stash ref 포함) |

**git 커밋이 진실 소스의 최후 방어선:** 모든 Stage 종료 시 git commit. 캐시 파일과 git 상태가 충돌하면 git HEAD를 신뢰.

캐시와 진실 소스가 불일치하면 진실 소스를 신뢰.

### 디렉토리 레이아웃

```
docs/
├── intake/{YYYYMMDD}-{project}/        ← Stage 1 산출물
│   ├── product-brief.md
│   ├── user-workflows.md                ⭐ 1b 산출물
│   ├── design-direction.md
│   ├── design-approved.md
│   ├── approved-mockups/
│   ├── architecture-sketch.md
│   ├── infrastructure-plan.md
│   ├── environment-check.md
│   └── zombie-cleanup-log.md
├── designs/{YYYYMMDD}-{project}/       ← Stage 2 산출물 (9 docs)
│   ├── 00-overview.md ~ 07-infrastructure.md
│   ├── 99-implementation-plan.md
│   └── debate/ (담금질 로그)
└── forge/{project}/                    ← Stage 3~5 산출물
    ├── plan.md
    ├── session-plan.json
    ├── workflow-progress.json
    ├── forge-progress.json
    ├── logs/
    │   └── journal.log
    ├── t01.md, t01-agreed.md, debate/
    ├── t02.md, t02-agreed.md, debate/
    └── ...
```

**Stage 1f-4가 ensure한 skeleton 파일 (프로젝트 루트, 없었던 것만 생성):**

```
.
├── .git/
├── .gitignore
├── .env.example, .env
├── pyproject.toml, uv.lock
├── manage.py
├── config/                              ← Django settings 루트
├── docker-compose.yml
├── dev.sh
├── deploy.sh (template)
├── CLAUDE.md (template)
├── README.md
├── package.json, tailwind.config.js (Tailwind 사용 시)
└── docs/ (intake/designs/forge 들어갈 공간)
```

기존 레포의 경우 이미 있는 파일은 건드리지 않는다 — 결과적으로 아무 변화 없이 Stage 2로 진행될 수 있다.

### Git Commit 정책

- 각 Stage 종료 시 git commit (자동)
- 커밋 메시지 규칙: `tts({stage}/{unit}): {status}`
- 예: `tts(1a/product-brief): approved`, `tts(2.2/04-data-model): forged`, `tts(5/t03): implemented`
- 메모리의 "git commit은 전체가 기본" 원칙 준수

---

## Failure Handling

### 실패 전파 원칙

`plan-forge-batch`와 동일:
- 상위 Stage 실패 → 하위 Stage skip
- 같은 Stage 내 의존성 있는 unit 실패 → 후속 unit skip
- 독립 unit은 실패와 무관하게 계속

### Resume 지점

| 실패 지점 | Resume 방법 |
|---|---|
| Stage 1 sub-stage 중단 | 다음 실행 시 해당 sub-stage부터 재개 (intake 커밋 기준) |
| Stage 1f 환경 검증 실패 | 사용자가 환경 수정 후 재실행. 체크리스트의 미통과 항목부터 재검사 |
| Stage 1f-4 skeleton ensure 중 실패 | 해당 ensure 단계 재시도. idempotent하므로 재실행 안전 |
| Stage 1.5 drift 감지 | 자동 중단. 사용자에게 환경 재정리 요청 후 재실행 |
| Stage 2 draft 중 실패 | 실패한 문서만 재생성 |
| Stage 2 forge 중 실패 | `*-agreed.md` 미존재 문서만 재담금질 |
| Stage 3 split 실패 | 전체 재실행 (빠름) |
| Stage 4 forge 중 실패 | 실패한 태스크만 재담금질 |
| Stage 5 태스크 환경 문제로 실패 | 해당 태스크 skip + 리포트. 나머지 태스크 계속. intake 개선 학습 기록 |
| Stage 5 태스크 로직 실패 | 실패한 태스크부터 재개 (이전 태스크는 git commit으로 고정) |

### Watchdog 개입

- hang 세션 감지: journal mtime 고정 + CPU 낮음 → kill + respawn (최대 3회)
- 재시도 초과 시: 해당 unit을 "blocked"로 기록, 사용자 개입 요청

---

## Migration Path

### Phase 1: 엔진 추출

1. `_forge-batch-engine/` 디렉토리 생성
2. 기존 `plan-forge-batch/`에서 세션 체이닝·watchdog·progress-tracking 코드 추출
3. 기존 `plan-forge-batch`는 건드리지 않음 (라이브러리를 import하지도 않음, 독립 유지)

### Phase 2: 배치 스킬 3종 생성

4. `design-forge-batch/` 생성 (plan-forge-batch 복사 + 구현·점검 제거)
5. `task-forge-batch/` 생성 (plan-forge-batch 복사 + 구현·점검 제거 + UPFRONT 모드)
6. `impl-forge-batch/` 생성 (plan-forge-batch 복사 + 담금질 제거)
7. 각 스킬은 `_forge-batch-engine`을 import

### Phase 3: 보조 스킬

8. `user-workflow-interview/` 생성 (Stage 1b 로직: 7차원 사용자 업무 프로세스 인터뷰)
9. `env-readiness/` 생성 (Stage 1f 로직: infra intake + static check + zombie check + idempotent skeleton ensure)
10. `session-planner/` 생성 (Stage 1.5 로직 + 재평가 + light drift check)
11. `ui-mockup` 업그레이드 (Gemini Nano Banana Pro + design-shotgun 기능 포팅: parallel generation, evolve, serve HTTP feedback, iterate)

### Phase 4: 오케스트레이터

12. `taste-to-ship/` (tts) 생성
13. Stage 1~5 체이닝 구현 (idempotent ensure 모델, 분기 없음)
14. 트리거 키워드 등록 (`taste-to-ship`, `tts`, `/tts`, `풀 워크플로우 시작`, `아이디어부터 구현까지`)
15. Tech-stack baseline skeleton 템플릿 작성 (Django + HTMX + Postgres + Tailwind 표준 starter. synco 특정 구조 피함)

### Phase 5: 검증 (2가지 경로)

16. **빈 디렉토리에서 검증** — tts 실행하여 bootstrap + 최소 기능 구현까지 완주 (e.g., "간단한 TODO SaaS")
17. **기존 레포에서 검증** — synco 레포에 작은 기능 추가를 tts로 진행 (e.g., "후보자 북마크 기능"). 기존 파일이 건드려지지 않음을 확인
18. 각 Stage 개별 테스트
19. 실패/resume 시나리오 테스트 (중간에 좀비 발생, 세션 hang, 배치 도중 중단 등)
20. Zombie check 시나리오 테스트 (의도적으로 orphan 생성 후 tts 실행)

### Phase 6: 전환 결정

21. 실제 프로젝트 2~3건 taste-to-ship으로 진행
22. 안정성 확인
23. 기존 `plan-forge-batch` 삭제 여부 판단 (유지할 수도 있음)

---

## Open Questions

- **Q1.** Stage 2a draft 생성 시 `superpowers:brainstorming`을 그대로 쓸 수 없음 (인터랙티브). autonomous 변형을 만들 것인가, 아니면 단순 문서 생성 프롬프트로 대체할 것인가? → 구현 계획 단계에서 결정.
- **Q2.** 쌍 담금질에서 다루지 않는 조합(예: `04-data-model` ↔ `06-workflow-map`)은 개별 담금질에만 의존하는데, 모순이 있을 경우 어떻게 감지할 것인가? → 현재는 "개별 담금질이 충분히 foot print 넓어야 함"으로 가정. 실사용에서 문제가 발견되면 쌍 조합을 추가.
- **Q3.** Session planner의 복잡도 추정이 부정확할 때 fallback? → 재평가 지점에서 자동 보정. 그래도 실패 시 사용자에게 "프로젝트 규모가 예상과 다름, 수동 조정 요청" 알림.
- **Q4.** Multi-project 동시 실행 지원? → 현 버전에서는 non-goal. 단일 프로젝트 직렬 실행만.
- **Q5.** `workflow-progress.json` 스키마는 아직 정의되지 않음. → 구현 계획 단계에서 `forge-progress.json`과의 관계와 함께 확정.
- **Q6.** Skeleton baseline 템플릿의 관리 방식: 하드코딩 vs 별도 템플릿 레포 vs `cookiecutter` 같은 도구 활용? → 구현 계획 단계에서 결정. 초기에는 Django+HTMX+Postgres 표준 starter를 하드코딩으로 시작.
- **Q7.** Django app 생성 시점: Stage 1f-4에서 만들지 않고 Stage 5에서 태스크로 생성. `architecture-sketch`의 모듈 이름이 그대로 Django app 이름으로 사용되는가, 아니면 네이밍 변환이 필요한가? → 구현 계획 단계에서 결정.
- **Q8.** Zombie check가 false positive를 낼 경우(사용자 정상 작업 중인 프로세스를 zombie로 오판)? → 절대 자동 kill하지 않음. 항상 사용자 확인 후 조치. 사용자가 "아니, 그건 살려둬"라고 답하면 워크플로우 중단하고 사용자에게 환경 정리 후 재시작 요청. plan-forge-batch의 "pytest 실패 기준"을 적용하여 false positive 최소화.
- **Q9.** Stage 1b의 user workflow 7차원이 모든 SaaS에 적합한가? 특정 도메인(예: 관리자 도구, B2B, 내부 도구)에서 추가 차원이 필요할 수 있음 → 첫 버전에서는 7차원 고정, 실사용에서 확장.
- **Q10.** Stage 5에서 태스크 환경 실패 시 "학습 기록"은 구체적으로 어떻게 저장하고 활용하는가? → 구현 계획 단계에서 `forge/{project}/env-learnings.md` 같은 파일 형식 확정.

---

## Appendix: Design Package 문서 상세 스펙

각 문서의 필수 섹션 정의. 담금질 레드팀은 이 섹션들이 모두 채워졌는지 체크한다.

### 00-overview.md

- 제품 이름과 한 줄 정의
- 타겟 사용자 (페르소나)
- 해결하는 문제
- 가치 제안
- 핵심 유스케이스 (3~5)
- 성공 지표 (측정 가능)
- 범위 밖 (Non-goals)

### 01-architecture.md ⭐

- 모듈 목록 (이름 + 1줄 책임)
- 모듈 상세 (각 모듈당: 책임, 주요 엔티티, 의존 모듈, blast radius)
- 의존성 DAG (다이어그램 또는 인접 리스트)
- 모듈 간 인터페이스 (API, 이벤트, 공유 데이터)
- 기술 스택
- **태스크 분할 규칙** (이 섹션은 명시적으로 필수)

### 02-design-system.md

- 브랜드 톤 (intake의 design-direction 재서술)
- 색 팔레트 (primary, accent, neutral, semantic)
- 타이포그래피 (폰트, 크기 스케일, 행간)
- 컴포넌트 라이브러리 (버튼·입력·카드·네비게이션·테이블·모달 등 — intake 승인된 것 기반)
- Spacing scale
- 반응형 breakpoint
- 다크모드 (선택)

### 03-ux-flows.md

- 화면 목록 (intake 승인된 목업 기반)
- 각 화면: 목적, 주요 요소, 인터랙션, 엣지 케이스 (zero state, loading, error, long text)
- 화면 간 플로우 (state diagram or flowchart)
- 주요 사용자 여정 (3~5)

### 04-data-model.md

- 엔티티 목록 + 속성
- 엔티티 관계 (ERD)
- 인덱스 전략
- 제약 (unique, check, FK)
- 마이그레이션 고려사항 (데이터 마이그레이션 vs 스키마 변경 분리)
- 테넌시 모델 (있다면)

### 05-auth-rbac.md

- 인증 방식 (OAuth, magic link, email/password)
- 세션 관리
- 역할 목록 + 권한 매트릭스
- Row-level security 정책 (있다면)
- 테넌시 격리 (있다면)
- 로그인/로그아웃/가입/비밀번호 리셋 플로우

### 06-workflow-map.md

- 핵심 워크플로우 (상태 전이 + 트리거)
- 기능 간 연계 (A → B → C)
- 이벤트/알림 흐름
- 백그라운드 작업 (스케줄, 큐)

### 07-infrastructure.md ⭐

- **Runtime environment**
  - Python 버전 (≥ 3.13)
  - Django 버전 (≥ 5.2)
  - 패키지 매니저 (uv)
  - Node/Tailwind (있다면)
- **Database**
  - 개발 DB 구성 (로컬 Docker Postgres)
  - 운영 DB 구성 (49.247.45.243 or 별도)
  - 접속 문자열 패턴 (환경변수로 주입)
  - 백업·복원 전략
  - 마이그레이션 운영 원칙 (운영 DB 직접 수정 금지)
- **External services**
  - 각 서비스: 역할, credential 취득 방법, 필요한 env vars, fallback 전략
  - 예: `Stripe (결제) — 대시보드에서 키 발급, STRIPE_SECRET_KEY/STRIPE_PUBLISHABLE_KEY, 실패 시 결제 disabled UI`
- **Environment variables (complete list)**
  - 이름, 설명, 필수/선택, 예시값, 적용 환경 (dev/prod/test)
  - 민감도 등급 (secret/config)
- **Secrets management**
  - `.env.prod`, `.secrets/` 위치
  - Git ignore 여부
  - 운영 배포 시 동기화 방법
- **Docker**
  - 개발: `docker-compose.yml` 서비스 (DB, 기타)
  - 운영: `docker-stack-synco.yml` 또는 해당 프로젝트 stack
  - 이미지 빌드 전략
- **Deployment**
  - 배포 대상 서버 (IP, SSH, 접속 방법)
  - 배포 파이프라인 (deploy.sh 단계)
  - 도메인·SSL
  - 롤백 전략
- **CI/CD**
  - 현재 단계: 로컬 deploy.sh 기준
  - 향후 GitHub Actions 등 확장 시 계획
- **Red-team tools**
  - 담금질에 사용할 도구 (codex CLI, gemini CLI, codex API, gemini API, agent)
  - 각 도구의 필요 조건 (바이너리, API 키)
- **Environment check results (from Stage 1f)**
  - Stage 1f-2/1f-3이 생성한 `environment-check.md`의 결과 요약
  - 각 검사 항목의 통과 상태와 발견된 이슈
- **Observability**
  - 로깅 전략 (django logging, 구조화 로그)
  - 에러 리포팅 (있다면 Sentry 등)
  - 메트릭/모니터링 (있다면)
- **Zombie & cleanup policy**
  - Stage 1f-3의 검사 항목 목록
  - 각 항목별 자동/수동 조치 원칙

### 99-implementation-plan.md

- 구현 순서 (의존성 기반)
- 모듈별 구현 계획 (각 모듈당: 작업 단위, 파일, 테스트 전략)
- 마일스톤 (optional)
- 초기 데이터 시드 (있다면)
- 배포 준비 (env vars, secrets, 마이그레이션)

---

## 끝.

*이 스펙이 확정되면 `superpowers:writing-plans`로 넘어가 Migration Path Phase 1~6의 구현 계획을 상세화한다.*
