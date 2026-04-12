---
date: 2026-04-12
status: draft
topic: taste-to-ship (tts)
type: workflow design spec
---

# taste-to-ship (tts) — End-to-End AI Build Workflow

> *Choose your taste, I'll do the rest.*

SaaS 웹 애플리케이션을 **아이디어에서 배포까지** 하나의 워크플로우로 연결하는 메타-오케스트레이터. 사용자의 인간 개입을 **Stage 1 통합 인터뷰 한 자리 + 배포 직전 1-click 확인**으로 한정하고, 그 사이 전 과정을 **세션 체이닝 기반 자동 실행**으로 처리한다.

## Motivation

### 해결하려는 3가지 문제

1. **설계 공백으로 인한 경로 의존성**
   현재 워크플로우(office-hours → brainstorming → 구현 계획서 초안 → 태스크 분할 → plan-forge-batch)의 "구현 계획서 초안" 단계에서 UI/UX 품질, 데이터 모델, 인증·권한, 기능 간 연계 등이 충분히 검토되지 않는다. 이 공백은 구현 이후에 드러나 수정 비용이 폭발한다. 특히 **디자인 결정**은 모든 화면에 퍼지고 나면 리팩토링이 거의 불가능하므로, 결정 시점이 "사후 리뷰"에서 **"구현 이전 승인"**으로 앞당겨져야 한다.

2. **장시간 작업에서의 컨텍스트 오염**
   아이디어에서 배포까지 전 과정을 한 세션에서 돌리면 컨텍스트가 포화되어 hallucination, 무한 루프, 엉뚱한 방향 탐색 같은 증상이 누적된다. `plan-forge-batch`가 구현 단계에서 해결한 "세션 경계로 컨텍스트 격리" 원리를 **워크플로우 전체 레벨에서 재적용**해야 한다.

3. **사용자 개입의 산발성**
   현재는 중간중간 사용자에게 질문이 튀어나와 맥락 전환 비용이 크다. 사용자는 "중간에 한참 알아서 진행해놓고 어떻게 하냐고 물어보면 뭘 물어보는지 몰라서 또 물어보고 왔다 갔다" 하는 상황을 겪는다. **모든 인간 개입을 앞단 한 자리에 모아야** 한다.

### 핵심 통찰

**사용자의 taste가 확정되면 — 제품 개념, 디자인 방향, 아키텍처 초안, 승인된 목업 — 나머지는 확산(diffusion) 과정으로 자동화 가능하다.** 노이즈에서 형상이 드러나는 diffusion 모델처럼, taste가 seed/prompt가 되어 점진적으로 구체화된 최종 제품으로 수렴한다.

---

## Goals

- **G1.** 아이디어 → 배포를 단일 워크플로우 스킬로 연결
- **G2.** 사용자 인간 개입을 Stage 1 통합 인터뷰 + 배포 1-click으로 한정
- **G3.** 경로 의존성이 있는 결정(디자인 룩앤필, 브랜드 톤, 모듈 경계)을 **사용자 승인 후에만** 진행
- **G4.** 전 과정을 세션 체이닝으로 분할하여 컨텍스트 오염 방지
- **G5.** `plan-forge-batch`의 엔진 로직을 재사용 가능한 라이브러리로 추출
- **G6.** 동적 세션 분할 계획으로 프로젝트 규모에 적응
- **G7.** 기존 `plan-forge-batch`는 유지하고 새 스킬을 병존시켜 점진적 전환

## Non-Goals

- **NG1.** 완전 무인 실행 (사용자 개입 0건). Stage 1 인터뷰와 배포 확인은 사람이 반드시 한다.
- **NG2.** 예술적 디자인 자동 생성. 디자인은 **기능적 UX 품질**을 목표로 하며, 사용자 승인 없이 브랜드 정체성을 결정하지 않는다.
- **NG3.** 기존 `plan-forge-batch` 스킬의 즉시 폐기. 새 스킬과 병존하며 검증 후 삭제 여부를 결정한다.
- **NG4.** 다른 언어/프레임워크 지원. 현재 타겟은 Django + HTMX + Postgres 스택의 SaaS 웹 앱이다. 다른 스택은 추후 확장.
- **NG5.** 분산 실행. 로컬 단일 머신 기반으로 작동한다.

---

## Core Principles

| 원칙 | 적용 |
|---|---|
| **Path-dependency prevention** | 경로 의존성 있는 결정은 Stage 1에서 사용자 승인 후 확정 |
| **Context isolation via session chaining** | 모든 자동 실행 단위는 별도 세션. 상태는 파일시스템으로 전달 |
| **Human front-loading** | 인간 개입은 워크플로우 앞단에 뭉쳐서 한 번에 끝 |
| **Dynamic session planning** | Intake 이후 session-plan을 자동 생성하고 단계 사이에 재평가 |
| **Fault isolation via module boundaries** | 태스크는 architecture 문서의 모듈 경계를 절대 넘지 않음 |
| **Forge everything** | 설계 문서, 태스크 문서, 구현 계획 모두 adversarial review(담금질) 통과 |
| **Engine/content separation** | batch 엔진(세션 체이닝, 진행 추적)과 콘텐츠(담금질·구현·점검)를 분리 |

---

## User Involvement Boundary

### 인간 접촉 포인트 (2개만)

| 포인트 | 성격 | 소요 시간 | 이유 |
|---|---|---|---|
| **Stage 1: Intake** (필수) | 인터랙티브 인터뷰, 1 sitting | 수십 분 ~ 1시간 | 제품 개념·디자인 룩앤필·아키텍처 제약은 머릿속에만 있음. 질문으로만 꺼낼 수 있음 |
| **Gate: Pre-Deploy** (필수) | 1-click y/n | 초 단위 | 배포는 blast radius 큼. 자동 금지 |

### 자동화 대상 (중간 개입 없음)

- 설계 문서 초안 작성
- 설계 담금질
- 태스크 분할
- 태스크 담금질
- 구현 + 구현 점검
- 배포 실행

**원칙:** Stage 1 종료 시점에 생성된 `intake/` 번들이 사용자 taste의 최종본이다. 이후 단계는 이 번들을 seed로 받아 실행한다. 중간에 사용자에게 추가 질문을 하지 않는다.

---

## Pipeline Overview

```
[HUMAN, 1 sitting]
Stage 1: Intake ─────────────────────────────────┐
  1a. Product Brief      (/office-hours)         │
  1b. Design Direction   (design-consultation)   │
  1c. Visual Approval    (ui-mockup upgraded) ⭐ │ Session chain
  1d. Architecture Sketch (brainstorming)        │ (each sub-stage = 1 session)
                                                  │
  → intake/ bundle (committed to git) ────────────┘
  ═════════════════ 이후 100% 자동 ═════════════════

[AUTO]
Stage 1.5: Session Planning
  → session-plan.json

Stage 2: Design Package
  2a. Draft generation (8 docs)
  2b. design-forge-batch (문서별 담금질)
  2c. Re-plan (session-plan 갱신)

Stage 3: Task Split
  99-agreed.md + 01-architecture.md → t01..tN + plan.md

Stage 4: Task Forging
  task-forge-batch (태스크별 담금질)

Stage 5: Implementation
  impl-forge-batch (구현 + 점검)

[HUMAN, 1-click]
Gate: Pre-Deploy 확인

[AUTO]
Stage 6: Deploy
  ./deploy.sh
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
  - 핵심 유스케이스 3~5개
  - 성공 지표
  - 경쟁/차별화 포인트

### 1b. Design Direction

- **실행 스킬:** `design-consultation` (gstack)
- **입력:** product-brief.md + 사용자 선호 질의
- **출력:** `docs/intake/{project}/design-direction.md`
- **내용:**
  - 브랜드 톤 (professional, playful, minimal, technical 등)
  - 색감 방향 (primary, accent, 중립 팔레트)
  - 타이포그래피 (Pretendard 기본, 대안 제안)
  - 참고 사이트 3~5개
  - 피하고 싶은 시각적 요소

### 1c. Visual Approval ⭐

**가장 중요한 sub-stage.** 경로 의존성을 앞단에서 끊는 단계.

- **실행 스킬:** `ui-mockup` (업그레이드판, Gemini Nano Banana Pro 기반)
- **입력:** product-brief.md + design-direction.md
- **출력:**
  - `docs/intake/{project}/approved-mockups/dashboard.png`
  - `docs/intake/{project}/approved-mockups/list.png`
  - `docs/intake/{project}/approved-mockups/detail.png`
  - `docs/intake/{project}/approved-mockups/component-library.png` (버튼·카드·네비)
  - `docs/intake/{project}/design-approved.md` (승인 근거, 피드백 정리)
- **프로세스:**
  1. 핵심 화면 3~5개 식별 (product-brief의 유스케이스 기반)
  2. 각 화면 variant 3~5개 병렬 생성 (Gemini Nano Banana Pro)
  3. 비교 보드 표시
  4. **사용자가 직접 선택** (일괄, 변형 승인 가능)
  5. 컴포넌트 라이브러리 샘플 생성 (버튼, 입력, 카드, 네비)
  6. 사용자가 최종 승인

**이 단계 없이 Stage 2로 진행 금지.** 디자인 미승인 상태로 워크플로우가 자동으로 넘어가면 안 된다.

### 1d. Architecture Sketch

- **실행 스킬:** `superpowers:brainstorming` (인터랙티브)
- **입력:** product-brief.md + (선택) 기존 시스템 제약
- **출력:** `docs/intake/{project}/architecture-sketch.md`
- **내용:**
  - 모듈 목록 초안 (이름, 책임 범위)
  - 모듈 간 의존성 방향 (DAG)
  - 기술 스택 확인 (기본: Django 5.2 + HTMX + Postgres)
  - 외부 통합 목록 (결제, 메일, 인증 등)
  - 기존 시스템과의 연계 제약

### Intake 번들 최종 구조

```
docs/intake/{YYYYMMDD}-{project}/
├── product-brief.md
├── design-direction.md
├── design-approved.md
├── approved-mockups/
│   ├── dashboard.png
│   ├── list.png
│   ├── detail.png
│   └── component-library.png
└── architecture-sketch.md
```

모든 파일은 git commit된다. 이 커밋이 **"이후 자동 실행"의 트리거**다.

---

## Stage 1.5: Session Planning (Auto)

### 목적

Intake 번들을 입력으로 받아, 이후 stage들이 어떻게 세션 단위로 쪼개질지 **동적으로 계획**한다. 정적 분할로는 프로젝트 규모에 적응할 수 없다.

### 입력

- Intake 번들 전체

### 처리

1. **설계 문서 수 결정** — 기본 8종, 프로젝트 규모에 따라 일부 통합 가능 (소규모에서 `06-workflow-map`을 `00-overview`에 통합 등)
2. **태스크 수 N 추정** — `architecture-sketch.md`의 모듈 개수 + 복잡도 기반
3. **각 논리 단위의 복잡도 분류** — 소/중/대
4. **세션 분할 결정:**
   - 소: 1 unit = 1 session
   - 중: 1 unit = 1 session (watchdog 감시)
   - 대: 1 unit = 2~3 sessions (의도적 분할)
5. **의존성 그래프 생성**

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

### 8-Doc Design Package

```
docs/designs/{YYYYMMDD}-{project}/
├── 00-overview.md            제품 개요, 목표, 성공 지표, 유스케이스
├── 01-architecture.md        ⭐ 모듈 경계, 인터페이스, 의존성, fault isolation
├── 02-design-system.md       디자인 시스템 (색·폰트·컴포넌트)
├── 03-ux-flows.md            화면·플로우 (intake의 승인된 목업 기반)
├── 04-data-model.md          엔티티·관계·인덱스·마이그레이션
├── 05-auth-rbac.md           인증, 역할/권한 매트릭스, 테넌시 모델
├── 06-workflow-map.md        사용자 여정, 기능 연계, 상태 전이
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
| `99-implementation-plan.md` | 위 모두 종합 |

### Stage 2a: Draft Generation

- 각 문서를 **1 session = 1 doc** 원칙으로 작성
- 8 sessions (또는 session-plan에 따라 조정)
- 각 세션은 `superpowers:brainstorming`의 **autonomous 변형** 또는 단순 문서 생성 프롬프트로 실행
- 출력: `{doc}.md` (draft)

### Stage 2b: Design Forging

- 각 draft 문서를 `design-forge-batch`가 담금질
- **담금질 구성 (기본):**
  - **1단계 — 개별 담금질:** 각 문서를 독립 세션에서 담금질 (관점별 깊이 확보). 8개 세션.
  - **2단계 — 쌍(pair) 담금질:** 강한 의존 관계가 있는 문서 쌍을 함께 담금질하여 문서 간 모순 탐지. 모든 조합이 아니라 O(N) 수준으로 제한:
    - `03-data-model` ↔ `05-auth-rbac` (엔티티·권한 일관성)
    - `01-architecture` ↔ `06-workflow-map` (모듈 경계·플로우 일관성)
    - `02-design-system` ↔ `03-ux-flows` (디자인·화면 일관성)
    - `99-implementation-plan` ↔ `01-architecture` (구현·모듈 경계 일관성)
- 출력: `{doc}-agreed.md` + 센티널 마커
- 통합 검증(8종 모두 한 세션 로드)은 **하지 않는다** — 컨텍스트 부담이 크고 쌍 담금질로 대체 가능

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
- `context` = Intake 번들 + 설계 패키지 8종 agreed
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

### `impl-forge-batch` vs 기존 `plan-forge-batch`

`impl-forge-batch`는 기존 `plan-forge-batch`의 **복사본**이다. 차이:

- 담금질 단계 제거 (태스크는 이미 `*-agreed.md` 상태로 들어옴)
- 구현 + 점검만 수행
- 엔진은 `_forge-batch-engine`을 공유

기존 `plan-forge-batch`는 유지되어 담금질-포함 배치가 필요한 다른 워크플로우에서 사용 가능. 충분히 검증된 후 삭제 여부 결정.

---

## Gate: Pre-Deploy Confirm (Human)

- 1-click y/n
- 타임아웃: 24시간 (기본). 초과 시 워크플로우 일시정지, 사용자 재개 대기
- 승인 시 Stage 6 진행
- 거부 시 워크플로우 종료, 사용자에게 "언제든 재개 가능" 안내

---

## Stage 6: Deploy (Auto)

- `./deploy.sh` 실행 (1 session)
- 파이프라인: check_migrations → test → save → backup_db → build → validate → deploy
- 실패 시 abort, 사용자에게 보고

---

## Skill Architecture

### Layer Diagram

```
┌─────────────────────────────────────────────┐
│ taste-to-ship (tts)  ⭐                     │  ← Orchestrator
│ · Stage 1~6 체이닝                          │
│ · Gate 관리                                 │
│ · trigger aliases: taste-to-ship, tts       │
└──────────────┬──────────────────────────────┘
               │ invokes
    ┌──────────┴──────────┬──────────┬──────────┬──────────┐
    ↓                     ↓          ↓          ↓          ↓
┌────────┐  ┌──────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│office- │  │session-      │  │design-   │  │task-     │  │impl-     │
│hours   │  │planner       │  │forge-    │  │forge-    │  │forge-    │
│        │  │              │  │batch     │  │batch     │  │batch     │
└────────┘  └──────────────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
                                    │             │             │
                                    ↓             ↓             ↓
                            ┌─────────────────────────────────────┐
                            │ _forge-batch-engine  ⭐              │  ← Shared library
                            │ · session-chaining                  │
                            │ · progress-tracking                 │
                            │ · watchdog                          │
                            │ · sentinel marker                   │
                            │ · dependency analysis               │
                            └─────────────────────────────────────┘
                                             │
                                             ↓
                                      ┌──────────┐
                                      │plan-forge│  ← 기존 유지
                                      └──────────┘
```

### 새 스킬 목록

| 스킬 | 역할 | 기반 |
|---|---|---|
| `taste-to-ship` (tts) | 최상위 워크플로우 오케스트레이터 | 신규 작성 |
| `_forge-batch-engine` | 세션 체이닝·진행 추적·watchdog 공유 라이브러리 | 기존 `plan-forge-batch`에서 추출 |
| `session-planner` | Intake → session-plan.json 변환 + 재평가 | 신규 작성 |
| `design-forge-batch` | 설계 문서 담금질만 (구현·점검 제거). 대상: 설계 패키지 8종 | `plan-forge-batch` 복사 → 구현·점검 제거 |
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

캐시와 진실 소스가 불일치하면 진실 소스를 신뢰.

### 디렉토리 레이아웃

```
docs/
├── intake/{YYYYMMDD}-{project}/       ← Stage 1 산출물
├── designs/{YYYYMMDD}-{project}/      ← Stage 2 산출물
└── forge/{project}/                   ← Stage 3~5 산출물
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
| Stage 2 draft 중 실패 | 실패한 문서만 재생성 |
| Stage 2 forge 중 실패 | `*-agreed.md` 미존재 문서만 재담금질 |
| Stage 3 split 실패 | 전체 재실행 (빠름) |
| Stage 4 forge 중 실패 | 실패한 태스크만 재담금질 |
| Stage 5 구현 중 실패 | 실패한 태스크부터 재개 (이전 태스크는 git commit으로 고정) |
| Gate 거부 | 워크플로우 일시정지, 사용자 명령으로 재개 |
| Stage 6 deploy 실패 | `./deploy.sh` 단계별 실패 지점 리포트, 수동 복구 후 재실행 |

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

4. `design-forge-batch/` 생성 (plan-forge-batch 복사 + 콘텐츠 교체)
5. `task-forge-batch/` 생성 (plan-forge-batch 복사 + UPFRONT 모드)
6. `impl-forge-batch/` 생성 (plan-forge-batch 복사 + 담금질 제거)
7. 각 스킬은 `_forge-batch-engine`을 import

### Phase 3: 보조 스킬

8. `session-planner/` 생성
9. `ui-mockup` 업그레이드 (Gemini Nano Banana Pro + design-shotgun 기능 포팅)

### Phase 4: 오케스트레이터

10. `taste-to-ship/` (tts) 생성
11. Stage 1~6 체이닝 구현
12. Gate 관리 구현
13. 트리거 키워드 등록

### Phase 5: 검증

14. 소규모 더미 프로젝트로 end-to-end 실행
15. 각 Stage 개별 테스트
16. 실패/resume 시나리오 테스트

### Phase 6: 전환 결정

17. 실제 프로젝트 1~2건 taste-to-ship으로 진행
18. 안정성 확인
19. 기존 `plan-forge-batch` 삭제 여부 판단 (유지할 수도 있음)

---

## Open Questions

- **Q1.** Stage 2a draft 생성 시 `superpowers:brainstorming`을 그대로 쓸 수 없음 (인터랙티브). autonomous 변형을 만들 것인가, 아니면 단순 문서 생성 프롬프트로 대체할 것인가? → 구현 계획 단계에서 결정.
- **Q2.** 쌍 담금질에서 다루지 않는 조합(예: `04-data-model` ↔ `06-workflow-map`)은 개별 담금질에만 의존하는데, 모순이 있을 경우 어떻게 감지할 것인가? → 현재는 "개별 담금질이 충분히 foot print 넓어야 함"으로 가정. 실사용에서 문제가 발견되면 쌍 조합을 추가.
- **Q3.** Gate 24시간 타임아웃이 적절한가? 주말 고려하면 72시간? → 사용자 설정 가능하게.
- **Q4.** Session planner의 복잡도 추정이 부정확할 때 fallback? → 재평가 지점에서 자동 보정. 그래도 실패 시 사용자에게 "프로젝트 규모가 예상과 다름, 수동 조정 요청" 알림.
- **Q5.** Multi-project 동시 실행 지원? → 현 버전에서는 non-goal. 단일 프로젝트 직렬 실행만.
- **Q6.** `workflow-progress.json` 스키마는 아직 정의되지 않음. → 구현 계획 단계에서 `forge-progress.json`과의 관계와 함께 확정.

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

### 99-implementation-plan.md

- 구현 순서 (의존성 기반)
- 모듈별 구현 계획 (각 모듈당: 작업 단위, 파일, 테스트 전략)
- 마일스톤 (optional)
- 초기 데이터 시드 (있다면)
- 배포 준비 (env vars, secrets, 마이그레이션)

---

## 끝.

*이 스펙이 확정되면 `superpowers:writing-plans`로 넘어가 Phase 1~6의 구현 계획을 상세화한다.*
