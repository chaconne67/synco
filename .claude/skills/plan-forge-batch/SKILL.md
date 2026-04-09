---
name: plan-forge-batch
description: >
  Orchestrate multiple plan-forge todos in parallel/sequential batches.
  Triggers: "배치 포지", "plan-forge-batch", or when plan-forge detects multiple
  todos. Analyzes dependencies and file conflicts, dispatches plan-forge per todo
  via Agent tool, uses staged execution with progress journal for context management.
  Now includes implementation execution via RemoteTrigger session chaining.
---

# Plan Forge Batch — Multi-Todo Orchestrator

복수의 할일을 분석하여 **스테이지 단위로** `plan-forge`를 디스패치하고, **구현까지 완전 자동화**하는 래퍼 스킬.

**원칙:**
- 이 스킬은 **오케스트레이션 + 구현 실행 관리**를 한다. 담금질은 `plan-forge`가, 구현은 `subagent-driven-development`가 수행한다
- **RemoteTrigger 기반 세션 관리.** 각 작업 단위마다 새 세션을 시작하여 컨텍스트 압박을 원천 차단한다
- **담금질은 병렬, 구현은 순차.** 담금질은 .md 파일만 생성하므로 병렬 안전. 구현은 실제 코드를 건드리므로 반드시 순차
- **`forge-progress.json`이 배치 진행 상황의 조회 소스.** 센티널 마커 + `*-agreed.md`가 완료 판정의 단일 진실 소스
- **`debate-log.json`이 토론 과정의 조회 소스.** 각 할일의 담금질 라운드 기록을 보존한다

## 진실 소스 우선순위

1. **센티널 마커** — 완료 판정. 형식: `<!-- forge:{topic}:{단계명}:complete:{ISO 8601 timestamp} -->` (각 `*-agreed.md` 마지막 줄. `plan-forge` 스킬이 생성)
2. **`*-agreed.md`** — 합의된 최종본
3. **`*-rulings.md`** — 최종 판결 (사람이 읽는 산문체)
4. **`debate-log.json`** — 라운드별 토론 과정 기록 (기계가 읽는 구조화 로그)
5. **`forge-progress.json`** — 배치 진행 요약 (조회용 캐시)

`forge-progress.json`과 센티널 마커가 불일치하면 센티널 마커를 신뢰한다.

## When to Use

- 소스 문서가 여러 개일 때 (디렉토리, 파일 목록)
- 하나의 프로젝트에 독립적인 할일이 2개 이상일 때
- `plan-forge`가 "할일이 여러 개입니다. 배치 모드를 사용할까요?"라고 제안할 때

## When NOT to Use

- 할일이 1개 → `plan-forge` 직접 사용
- 소스 문서 없이 처음부터 시작 → `plan-forge`로 브레인스토밍부터

## 모드 판별

스킬 진입 시 `forge-progress.json`을 확인하여 모드를 결정한다:

| 조건 | 모드 |
|------|------|
| `forge-progress.json` 없음 | **Setup** |
| `forge-progress.json` 존재 + `batch_status: "setup"` | **Setup** (초기화 중 중단됨, 재개) |
| `forge-progress.json` 존재 + `batch_status: "running"` | **Continue** |
| `forge-progress.json` 존재 + `batch_status: "complete"` 또는 `"failed"` | **종료** (이미 완료) |

## 워크플로우

```
[Setup 모드 — 사용자 로컬 세션]

1. 소스 파싱 ─── 소스 문서 읽기, 할일 목록 생성
       │
2. 충돌 분석 ─── 파일 충돌 + 의존성 → 병렬/순차 판별
       │
3. 스테이지 분할 ─── 할일을 스테이지로 묶기 (자동 크기 조정)
       │
4. 사용자 승인 + 실행 범위 선택 → forge-progress.json 초기화 → RemoteTrigger 생성 + 실행

[Continue 모드 — RemoteTrigger 자동 세션 체인]

5. 스테이지별 담금질 ─── Agent 도구로 plan-forge 병렬 호출
       │                    → commit → forge-progress.json 업데이트
       │                    → RemoteTrigger (세션 클리어)
       │
6. 할일별 구현 ──────── 순차 1건씩, 각각 새 세션
       │                    → subagent-driven-development로 구현
       │                    → 테스트 → commit → forge-progress.json 업데이트
       │                    → RemoteTrigger (세션 클리어)
       │
       └─ 다음 스테이지 → 5번으로 돌아감
       │
7. 할일별 구현점검 ─── (실행 범위가 "구현점검 포함"인 경우만)
       │                    → 순차 1건씩, 각각 새 세션
       │                    → impl-check 스킬로 점검+수정
       │                    → commit → forge-progress.json 업데이트
       │                    → RemoteTrigger (세션 클리어)
       │
8. 보고 ─────── forge-progress.json 기반 전체 결과 요약 + 알림
```

## 1. 소스 파싱

**할일 1개 감지 시:** 파싱 결과 할일이 1개뿐이면 사용자에게 알리고 `plan-forge`로 리다이렉트한다: "할일이 1개입니다. `plan-forge`로 직접 처리합니다."

입력 유형:

| 입력 | 처리 |
|------|------|
| 디렉토리 경로 | 내부 `.md` 파일 각각을 할일 1개로 (README.md 제외) |
| 파일 목록 | 각 파일을 할일 1개로 |
| 단일 문서 내 복수 섹션 | 사용자에게 "섹션별로 분리할까요?" 확인 후 분리 |

각 할일에 대해:
- **slug 생성:** 파일명 기반, lowercase with hyphens
- **문서 유형 판별:** 사용자에게 확인 ("이 문서들은 설계서입니까, 구현계획서입니까?")
- **변경 대상 파일 추출:** 문서 내용에서 변경/생성/수정 대상 파일 경로를 추출
- **복잡도 추정:** 변경 대상 파일 수 + 소스 문서 크기로 복잡도 산정 (스테이지 분할에 사용)

### 변경 대상 파일 추출 방법

각 할일이 변경/생성/수정할 모든 파일을 문서 내용과 코드베이스를 대조하여 추출한다. 명시적 파일 경로뿐 아니라 컴포넌트/기능 언급("auth 미들웨어를 수정", "검색 로직 개선" 등)도 실제 파일로 매핑한다. 확신할 수 없는 경우 해당 파일을 포함시킨다 (누락보다 과잉 포함이 안전).

추출 결과를 사용자에게 보여주고 확인받는다:
```
할일별 변경 대상 파일:
  auth-module:  accounts/models.py, accounts/views.py, accounts/urls.py
  search-api:   candidates/services/search.py, candidates/views.py
  → 파일 겹침 없음. 병렬 처리 가능합니다. 진행할까요?
```

### 복잡도 추정

복잡도는 **변경의 깊이**(각 파일의 수정 범위)와 **넓이**(파일 수)를 종합하여 소/중/대로 판정한다.

**기본 기준** (참고값이며, 실제 변경 내용에 따라 조정한다):

| 지표 | 소 | 중 | 대 |
|------|---|---|---|
| 변경 대상 파일 수 | ≤5 | 6-15 | >15 |
| 소스 문서 크기 | ≤100줄 | 101-300줄 | >300줄 |

**조정 원칙:** 파일 수가 많더라도 변경이 기계적(import 추가, 필드 1개 추가 등)이면 한 등급 낮춘다. 반대로 파일 수가 적더라도 서비스 로직 전면 재작성이면 한 등급 높인다. 판단 기준은 "이 할일이 서브에이전트 하나의 컨텍스트 윈도우 안에서 구현계획서 전문 + 관련 코드를 동시에 보면서 작업을 완료할 수 있는가"이다.

복잡도 = 파일 수와 문서 크기의 기본 등급에서 위 조정을 적용. 스테이지 분할 시 사용.

## 2. 충돌 분석

### 파일 충돌 검사

```
for each pair (할일A, 할일B):
  filesA = 할일A의 변경 대상 파일 집합
  filesB = 할일B의 변경 대상 파일 집합

  if filesA ∩ filesB ≠ ∅:
    → 순차 강제 (충돌 파일 목록 기록)
```

### 명시적 의존성 검사

소스 문서 내에서:
- "depends on", "requires", "선행:", "의존:" 등의 키워드
- README.md의 순서/의존성 명시

### 판별 결과

| 조건 | 처리 |
|------|------|
| 파일 충돌 없음 + 의존성 없음 | **병렬** |
| 파일 충돌 있음 | **순차** (충돌 파일 기준 순서 결정) |
| 명시적 의존성 있음 | **순차** (의존성 순서) |
| 판별 불확실 | **순차** (안전 우선) |

사용자에게 분석 결과를 보고하고 승인을 받는다:
```
충돌 분석 결과:
  병렬 그룹 1: [auth-module, search-api] — 파일 겹침 없음
  순차 체인: notification → email-service — notification이 email-service에 의존
  
이대로 진행할까요?
```

## 3. 스테이지 분할

충돌 분석 결과 + 복잡도를 기반으로 할일을 스테이지로 묶는다.

### 분할 규칙

1. **의존성 순서 우선:** 의존 체인은 반드시 별도 스테이지 (선행 → 후행)
2. **스테이지당 용량 제한:** 복잡도 가중치 합산으로 제한
   - 소 = 1, 중 = 2, 대 = 3
   - **스테이지당 가중치 합산 최대 4** (예: 대1+소1, 중2, 소4). 이유: 한 스테이지 내 병렬 에이전트의 누적 변경 규모를 제한하여, 스테이지 완료 후 병합·검토가 관리 가능한 수준을 유지한다. 합산 5 이상이면 병합 충돌과 부작용 검증의 부담이 급격히 증가한다
3. **병렬 가능한 할일만 같은 스테이지에 배치**

### 분할 예시

```
할일 8개, 충돌 분석 결과:
  독립: P01(중), P02(소), P03(소), P06(소), P07(대), P08(중)
  의존: P04(중) → P01에 의존, P05(중) → P03에 의존

스테이지 분할:
  Stage 1: [P01(중), P02(소), P03(소)]  — 가중치 4, 병렬
  Stage 2: [P04(중), P05(중)]            — 가중치 4, 병렬 (선행 완료 후)
  Stage 3: [P06(소), P07(대)]            — 가중치 4, 병렬
  Stage 4: [P08(중)]                     — 가중치 2
```

사용자에게 스테이지 분할 결과를 보고하고 승인을 받는다:
```
스테이지 분할 (총 4 스테이지):
  Stage 1: [P01, P02, P03] — 병렬, 가중치 4/4
  Stage 2: [P04, P05]      — 병렬 (P01, P03 완료 후), 가중치 4/4
  Stage 3: [P06, P07]      — 병렬, 가중치 4/4
  Stage 4: [P08]           — 단독, 가중치 2/4

이대로 진행할까요?

실행 범위:
  A) 구현까지 — 담금질 + 구현 (기본값)
  B) 구현점검 포함 — 담금질 + 구현 + impl-check 점검
```

실행 범위 선택 결과를 `forge-progress.json`의 `scope` 필드에 기록한다. **scope가 `"verify"`이면 모든 할일의 `verification_status`를 `"pending"`으로 초기화한다.** scope가 `"impl_only"`이면 `verification_status`는 `null`로 둔다.

## 4. RemoteTrigger 기반 세션 관리

### Setup 모드 완료 시 트리거 생성

사용자 승인 후, `forge-progress.json`을 초기화하고 (`batch_status`를 `"running"`으로 설정) RemoteTrigger를 생성한다:

```
RemoteTrigger(action: "create", body: {
  "name": "forge-batch-{project}",
  "prompt": "plan-forge-batch 배치의 다음 단계를 실행하라.\n\n## 컨텍스트\n- 워킹 디렉토리: {working_dir}\n- 프로젝트: {project}\n- forge-progress.json 경로: docs/forge/{project}/forge-progress.json\n\n## 실행 절차\n1. CLAUDE.md를 읽어 프로젝트 컨텍스트를 파악하라\n2. plan-forge-batch 스킬을 호출하라 (Skill 도구 사용). 스킬이 forge-progress.json을 읽고 자동으로 Continue 모드로 진입한다\n3. 스킬이 완료되면 forge-progress.json을 업데이트하고 git commit + push하라\n4. 배치가 완료되지 않았으면 forge-progress.json에서 trigger_id를 읽어 RemoteTrigger(action: run)를 실행하라\n5. 완료되었으면 최종 보고 후 텔레그램 알림을 보내라",
  "max_turns": 200
})
```

생성된 `trigger_id`를 `forge-progress.json`에 기록한다. Continue 모드 세션은 항상 `forge-progress.json`에서 `trigger_id`를 읽어 자기 참조한다 (create 시점에는 trigger_id를 모르므로 프롬프트에 하드코딩하지 않는다).

첫 번째 트리거 실행:
```
RemoteTrigger(action: "run", trigger_id: "{trigger_id}")
```

### Continue 모드 진입

RemoteTrigger가 새 세션을 시작하면:

1. `forge-progress.json` 읽기
2. 센티널 마커와 대조하여 정합성 검증
3. **액션 결정** (아래 로직)
4. 액션 실행
5. `forge-progress.json` 업데이트 + git commit + git push
6. 배치 미완료 → `RemoteTrigger(action: "run", trigger_id: "{trigger_id}")` / 배치 완료 → 알림 + 종료

### 액션 결정 로직

`forge-progress.json`을 읽어 다음 규칙을 **위에서부터 순서대로** 매칭:

```
1. batch_status가 "complete" 또는 "failed"
   → 종료 (RemoteTrigger 체인 중단)

2. impl_status 또는 verification_status가 "running"인 할일이 있음 (이전 세션 중단으로 인한 잔류 상태)
   → 먼저 해당 할일 관련 uncommitted changes를 정리한다:
     `git status`로 변경 파일 확인 → `git stash -m "forge-batch: orphan changes from {todo-slug}"`로 보존.
     이미 커밋된 부분 구현이 있으면 `git log`로 확인하여 판단에 활용.
   → 해당 필드를 "pending"으로 리셋한 후 아래 규칙부터 재평가.
   이유: "running"은 이전 세션이 비정상 종료된 것이므로, 디스크의 불완전한 상태를 정리한 후 재시도해야 한다.

3. 현재 스테이지에서 tempering_status가 "pending"인 할일이 있음
   → 담금질 세션: 해당 스테이지의 모든 pending 할일을 병렬 담금질
   (참고: 규칙 3이 4보다 먼저 매칭되므로, 담금질 pending과 구현 pending이 공존하면 담금질이 우선한다)

4. 현재 스테이지에서 tempering_status가 "completed"이고
   impl_status가 "pending"인 할일이 있음
   → **depends_on 안전 검사:** 해당 할일의 `depends_on` 대상 중 `impl_status`가 `"failed"` 또는 `"skipped"`인 것이 있으면, 이 할일도 `impl_status: "skipped"` (scope가 `"verify"`이면 `verification_status: "skipped"`)로 설정하고 건너뛴다
   → 검사 통과 시 구현 세션: 첫 번째 pending 할일 1건만 구현

5. 현재 스테이지의 모든 할일이 impl_status "completed", "failed", 또는 "skipped"
   → 스테이지 완료 처리 + forge-progress.json 업데이트
   → 다음 스테이지가 있으면: RemoteTrigger로 새 세션에서 다음 스테이지 시작
     (같은 세션에서 다음 스테이지를 바로 시작하지 않는다)
   → 마지막 스테이지이면: 규칙 6 또는 7로 직행 (같은 세션)

6. 모든 스테이지의 구현이 완료되었고, scope가 "verify"이고,
   impl_status가 "completed"인 할일 중 verification_status가 "pending"인 할일이 있음
   → 구현점검 세션: 첫 번째 pending 할일 1건만 점검

7. 모든 할일의 verification_status가 "completed", "failed", 또는 "skipped"(또는 scope가 "impl_only")
   → batch_status를 "complete"로 변경 → 완료 보고 + 알림

batch_status "failed"는 오케스트레이션 장애(RemoteTrigger 생성/실행 실패, forge-progress.json 손상 등)에만 사용한다. 개별 할일의 실패는 해당 할일의 status 필드로 추적하며 batch_status에 반영하지 않는다.
```

**현재 스테이지 판별:** `stages` 배열에서 `phase`가 `"complete"`가 아닌 첫 번째 스테이지.

## 5. 스테이지별 담금질

### 스테이지 시작 프로토콜

각 스테이지 시작 시:
1. `forge-progress.json`을 읽어 이전 스테이지 결과 확인
2. 이전 스테이지에서 실패한 할일에 의존하는 할일이 있으면 스킵 처리
3. **교차 학습:** 이전 스테이지 할일들의 `debate-log.json`에서 반복 패턴을 추출하여 디스패치 프롬프트에 포함

### 교차 학습

이전 스테이지의 `debate-log.json`에서 CRITICAL/MAJOR 이슈 중 `accepted`된 것을 수집한다.

**반복 가능 판별 기준:** 기술 스택 수준의 공통 패턴(Django ORM 동작 방식, DB 인덱스 전략, API 설계 관례 등)은 반복 가능 → 포함. 특정 모델/테이블/필드에 종속된 이슈("User 모델의 FK를 수정")는 해당 할일 고유 → 제외. 판별 불확실하면 포함한다(누락보다 과잉 포함이 안전).

반복 가능한 패턴이면 후속 할일 디스패치 프롬프트에 추가:

```
## 이전 할일에서 제기된 주요 이슈 (참고)
- P01: UUID v4의 B-tree 인덱스 비효율 → UUID v7로 변경 (CRITICAL, accepted)
- P02: bulk_create 시 auto_now_add 누락 → DB default 추가 (MAJOR, accepted)

위 이슈가 이 할일에도 해당되는지 설계 시 검토하라.
```

### 병렬 디스패치

파일 충돌이 없는 할일들을 Agent 도구로 동시 디스패치한다.

```
Agent 도구 호출 (병렬로 여러 개):
  description: "plan-forge: {todo-slug}"
  prompt: |
    plan-forge 스킬을 호출하여 다음 할일을 처리하라.
    
    ## 할일
    토픽: {todo-slug}
    forge 디렉토리: docs/forge/{project}/{todo-slug}/
    
    ## 소스 문서
    아래 내용을 docs/forge/{project}/{todo-slug}/debate/{design-spec|impl-plan}.md로
    저장한 후 plan-forge 스킬의 워크플로우를 따르라.
    
    {소스 문서 내용 — Context Snapshot Rules 적용}

Context Snapshot Rules (소스 문서 — 서브에이전트 프롬프트의 토큰 예산을 관리하면서 맥락 손실을 최소화하기 위함):
- **200줄 이하** (약 4K 토큰): 소스 문서 전문 인라인
- **200줄 초과**: 문서 규모에 비례하여 핵심 결정을 bullet 요약 + 관련 섹션 원문 발췌 + `Source: {원본 경로}` (서브에이전트가 필요 시 직접 읽도록). "핵심 결정"의 판단 기준: 이 결정이 바뀌면 구현이 달라지는 것(아키텍처 선택, 데이터 모델, API 계약, 제약조건). 구현 세부사항(변수명, 유틸 함수 시그니처 등)은 제외
    
    ## 진입점
    {design → 설계담금질부터 | impl → 구현담금질부터}
    
    {교차 학습 섹션 — 이전 스테이지 이슈가 있을 때만}
```

### 순차 디스패치

의존성이 있는 할일은 선행 할일 완료 + git commit 후에 디스패치한다.

```
1. 선행 할일 Agent 완료 대기
2. 선행 할일의 산출물을 git commit
3. 후속 할일 Agent 디스패치
   - prompt에 추가: "선행 할일 '{선행 slug}'의 확정 구현계획서를 참고하라.
     경로: docs/forge/{project}/{선행 slug}/impl-plan-agreed.md"
```

### 혼합 (병렬 + 순차)

```
예시: A, B는 독립, C는 A에 의존, D는 B에 의존

Stage 1: Agent(A), Agent(B) — 병렬 디스패치
Stage 2: A 완료 → git commit → Agent(C)
         B 완료 → git commit → Agent(D)
         C, D도 서로 독립이면 같은 스테이지에서 병렬
```

### 담금질 할일 완료 처리

각 할일의 Agent가 완료되면:

1. 산출물 존재 확인 (`*-agreed.md` + 센티널 마커)
2. `debate-log.json` 존재 확인 (토론 과정 기록 보존 검증)
3. `tempering_status`를 `"completed"` 또는 `"failed"`로 업데이트
4. **`tempering_status`가 `"failed"`이면 `impl_status`를 `"skipped"`로, scope가 `"verify"`이면 `verification_status`도 `"skipped"`로 설정**
5. `git add docs/forge/{project}/{todo-slug}/`
6. `git commit -m "forge({project}/{todo-slug}): tempering complete"`

### 담금질 세션 완료 프로토콜

스테이지 내 모든 할일의 담금질이 완료(또는 실패)되면:

1. 스테이지 `phase`를 `"implementing"`으로 변경
2. `forge-progress.json` 업데이트 — 해당 스테이지 담금질 결과 기록
3. `git add docs/forge/{project}/forge-progress.json`
4. `git commit -m "forge-batch({project}): stage {N} tempering complete"`
5. `git push` — 실패 시 최대 2회 재시도 (아래 "git push 실패 처리" 참조)
6. `RemoteTrigger(action: "run", trigger_id: "{trigger_id}")` — 새 세션에서 구현 시작

## 6. 할일별 구현

### 실행 규칙

- **세션당 1건만 구현한다.** 1건 완료 후 반드시 RemoteTrigger로 새 세션을 시작한다.
- 확정 구현계획서 (`impl-plan-agreed.md`)를 source로 사용한다.
- `superpowers:subagent-driven-development` 스킬을 **직접** 호출하여 구현한다. plan-forge를 거치지 않는다 — 사전점검은 배치 오케스트레이터의 세션 관리가 대체한다.
- 구현 완료 후 테스트를 실행하여 통과를 확인한다.

### 구현 세션 흐름

```
1. forge-progress.json 읽기
2. 현재 스테이지에서 impl_status가 "pending"인 첫 번째 할일 식별
3. 해당 할일의 impl-plan-agreed.md 읽기
4. impl_status를 "running"으로 업데이트 + commit
5. superpowers:subagent-driven-development 스킬로 구현 실행
6. 테스트 실행 (프로젝트의 테스트 명령어 사용)
7. 성공 시:
   - 구현 코드 commit
   - impl_status를 "completed"로, impl_commit에 커밋 해시 기록
8. 실패 시:
   - 재시도 원칙에 따라 판단 (같은 세션 내)
   - 최대 재시도 후에도 실패 → impl_status를 "failed"로, reason에 실패 사유 기록. scope가 "verify"이면 verification_status를 "skipped"로 설정
   - 실패한 할일에 의존하는 후속 할일도 impl_status를 "skipped"로 설정 (scope가 "verify"이면 verification_status도 "skipped")
9. forge-progress.json 업데이트 + commit + push (실패 시 아래 "git push 실패 처리" 참조)
10. RemoteTrigger(action: "run", trigger_id: "{trigger_id}")
```

### 구현 실패 처리

| 상황 | 처리 |
|------|------|
| 테스트 실패 | 재시도 원칙에 따라 판단 (같은 세션 내) |
| 최대 재시도 후에도 실패 | `impl_status: "failed"`, `reason` 기록. scope가 `"verify"`이면 `verification_status: "skipped"`. 다음 할일로 이동 |
| 실패한 할일에 의존하는 후속 구현 | 함께 스킵 (`impl_status: "skipped"`, scope가 `"verify"`이면 `verification_status: "skipped"`) |

## 7. 할일별 구현점검

`scope`가 `"verify"`인 경우에만 실행한다. 모든 스테이지의 구현이 완료된 후 진행한다.

### 실행 규칙

- **세션당 1건만 점검한다.** 1건 완료 후 반드시 RemoteTrigger로 새 세션을 시작한다.
- `impl-check` 스킬을 호출하여 점검한다. 입력 문서는 해당 할일의 `impl-plan-agreed.md`(구현계획서)와 `design-spec-agreed.md`(설계서, 존재 시).
- impl-check이 FAIL 이슈를 발견하면 자동으로 수정하고 재검증한다 (impl-check 스킬의 내부 루프).
- 구현이 실패(`impl_status: "failed"`)하거나 스킵된 할일은 점검하지 않는다.

### 구현점검 세션 흐름

```
1. forge-progress.json 읽기
2. verification_status가 "pending"인 첫 번째 할일 식별
3. verification_status를 "running"으로 업데이트 + commit
4. impl-check 스킬 호출 (입력: impl-plan-agreed.md + design-spec-agreed.md)
5. impl-check 완료 시:
   - 수정이 있었으면 commit
   - verification_status를 "completed"로, verification_result에 요약 기록
6. impl-check 실패 시:
   - verification_status를 "failed"로, reason에 실패 사유 기록
7. forge-progress.json 업데이트 + commit + push (실패 시 아래 "git push 실패 처리" 참조)
8. RemoteTrigger(action: "run", trigger_id: "{trigger_id}")
```

### 구현점검 순서

모든 스테이지의 할일을 스테이지 순서대로, 스테이지 내에서는 할일 순서대로 점검한다. 이유: 선행 할일의 점검 수정이 후속 할일에 영향을 줄 수 있으므로 의존성 순서를 유지한다.

## 8. Progress Journal (`forge-progress.json`)

`docs/forge/{project}/forge-progress.json`에 배치 진행 상황을 기록한다.

### 포맷

```json
{
  "project": "{project}",
  "total_todos": 8,
  "created_at": "2026-04-08T10:00:00Z",
  "batch_status": "running",
  "trigger_id": "trg_abc123",
  "scope": "verify",
  "stages": [
    {
      "stage": 1, "phase": "complete",
      "todos": [
        {
          "slug": "P01-models", "tempering_status": "completed",
          "impl_status": "completed", "impl_commit": "abc1234",
          "verification_status": "completed", "verification_result": "PASS 8/8, REVIEW 1",
          "entry_point": "design", "complexity": "medium",
          "artifacts": ["design-spec-agreed.md", "impl-plan-agreed.md"],
          "committed": true,
          "debate_summary": {
            "design": {"rounds": 2, "issues": 3, "accepted": 2, "rebutted": 1, "escalated": 0},
            "impl": {"rounds": 3, "issues": 5, "accepted": 3, "rebutted": 2, "escalated": 0}
          }
        },
        { "slug": "P03-extraction", "tempering_status": "failed",
          "impl_status": "skipped", "impl_commit": null,
          "verification_status": "skipped", "verification_result": null,
          "entry_point": "design", "complexity": "small",
          "artifacts": [], "committed": false,
          "reason": "CRITICAL issue unresolved after 7 rounds",
          "debate_summary": { "design": {"rounds": 7, "issues": 2, "accepted": 0, "rebutted": 2, "escalated": 2}, "impl": null }
        }
      ],
      "summary": "1/2 성공. P03는 설계담금질에서 CRITICAL 이슈 미해결로 실패."
    },
    {
      "stage": 2, "phase": "tempering",
      "todos": [
        { "slug": "P04-search", "tempering_status": "pending",
          "impl_status": "pending", "impl_commit": null,
          "verification_status": "pending", "verification_result": null,
          "entry_point": "design", "complexity": "medium", "depends_on": ["P01-models"] }
      ],
      "summary": null
    }
  ],
  "decisions": [
    { "stage": 1, "decision": "P03 실패 → P03에 의존하는 할일도 스킵 예정", "timestamp": "2026-04-08T14:30:00Z" }
  ]
}
```

### 필드 설명

**Top level:**

| 필드 | 타입 | 설명 |
|------|------|------|
| `batch_status` | string | `"setup"` \| `"running"` \| `"complete"` \| `"failed"` |
| `trigger_id` | string | RemoteTrigger ID (세션 체인에 사용) |
| `scope` | string | `"impl_only"` \| `"verify"` — 실행 범위 (Setup 시 사용자 선택) |

**Per stage:**

| 필드 | 타입 | 설명 |
|------|------|------|
| `phase` | string | `"tempering"` \| `"implementing"` \| `"complete"` |

**Per todo:**

| 필드 | 타입 | 설명 |
|------|------|------|
| `tempering_status` | string | `"pending"` \| `"completed"` \| `"failed"` |
| `impl_status` | string | `"pending"` \| `"running"` \| `"completed"` \| `"failed"` \| `"skipped"` |
| `impl_commit` | string \| null | 구현 커밋 해시 (완료 시 기록) |
| `verification_status` | string \| null | `"pending"` \| `"running"` \| `"completed"` \| `"failed"` \| `"skipped"` — scope가 `"verify"`일 때만 사용. Setup 시 `"pending"`으로 초기화. `impl_status`가 `"failed"` 또는 `"skipped"`이면 `"skipped"`로 전이 |
| `verification_result` | string \| null | impl-check 점검 결과 요약 (완료 시 기록) |
| `depends_on` | string[] \| null | 이 할일이 의존하는 할일의 slug 목록. Setup의 충돌 분석에서 결정. 의존 대상이 실패/스킵 시 이 할일도 스킵 |

### 업데이트 시점

| 시점 | 기록 내용 |
|------|----------|
| 배치 시작 (Setup) | 초기 구조 생성 (전체 할일 목록, 스테이지 분할, `trigger_id`) |
| 담금질 할일 완료/실패 | 해당 할일의 `tempering_status`, `artifacts`, `debate_summary` |
| 담금질 세션 완료 | 해당 스테이지 `phase`를 `"implementing"`으로 변경 |
| 구현 시작 | 해당 할일의 `impl_status`를 `"running"`으로 |
| 구현 완료/실패 | 해당 할일의 `impl_status`, `impl_commit` 또는 `reason`. 실패/스킵 시 `verification_status`를 `"skipped"`로 |
| 스테이지 완료 | 해당 스테이지 `phase`를 `"complete"`로, `summary` 기록, `decisions` |
| 구현점검 시작 | 해당 할일의 `verification_status`를 `"running"`으로 |
| 구현점검 완료/실패 | 해당 할일의 `verification_status`, `verification_result` 또는 `reason` |
| 배치 종료 | `batch_status`를 `"complete"` 또는 `"failed"`로 |

### debate_summary 생성

**스테이지 키 매핑:** `debate-log.json`과 `forge-progress.json`의 키 이름이 다르다.

| `debate-log.json` 키 | `forge-progress.json` 키 |
|----------------------|-------------------------|
| `design-tempering` | `design` |
| `impl-tempering` | `impl` |

각 할일 완료 시 `debate-log.json`에서 `summary`를 읽어 위 매핑을 적용한 후 `forge-progress.json`의 `debate_summary`에 인라인한다. `debate-log.json`의 상세 라운드 정보는 각 할일 디렉토리에 남아있으므로, `forge-progress.json`에는 집계만 기록.

## 9. 보고

### 스테이지 완료 시 (forge-progress.json summary에 기록)

```
Stage 1 완료:
  담금질: ✓ P01 (설계2R/구현3R), ✓ P02 (설계1R/구현2R)
  구현: ✓ P01 (abc1234), ✓ P02 (def5678)
```

### 전체 완료 시 (텔레그램 알림)

```
배치 포지 완료: {project}
  Stage 1: ✓ P01, ✓ P02 — 담금질+구현 완료
  Stage 2: ✓ P04 — 담금질+구현 완료
  Stage 3: ✓ P06, ✓ P07 — 담금질+구현 완료
  Stage 4: ✓ P08 — 담금질+구현 완료

성공: 7/8, 실패: 1/8 (P03 담금질 실패), 스킵: 0/8

구현점검: (scope: verify)
  ✓ P01 — PASS 8/8, REVIEW 1
  ✓ P02 — PASS 6/6
  ✓ P04 — PASS 10/10

실패한 할일은 plan-forge로 개별 재시도하세요.
  재시도 시 debate-log.json의 이전 토론 맥락이 자동 참조됩니다.
```

## 실패 처리

### 재시도 원칙

재시도 여부는 실패 원인으로 판단한다:
- **일시적 실패** (네트워크, rate limit, 타임아웃) → 재시도 가치 있음
- **구조적 실패** (설계 모순, 순환 참조, 스키마 불일치) → 같은 원인이면 재시도해도 같은 결과. 즉시 실패 처리
- **판별 불확실** → 1회 재시도 후 같은 에러면 구조적 실패로 간주

기본 최대 재시도: 2회 (일시적 실패는 대부분 2회 이내에 해소되며, 3회 이상 반복이면 구조적 실패일 확률이 높다). 단, 에러 메시지가 이전과 동일하면 즉시 중단.

### 담금질 실패

| 상황 | 처리 |
|------|------|
| Agent 세션 실패 | 재시도 원칙에 따라 판단 |
| 최대 재시도 후에도 실패 | 해당 할일 스킵, `tempering_status: "failed"` 기록 |
| 담금질 실패한 할일 | `impl_status: "skipped"` 자동 설정. scope가 `"verify"`이면 `verification_status: "skipped"`도 설정 |
| 실패한 할일에 의존하는 후속 할일 | 함께 스킵, `decisions`에 이유 기록 |
| 센티널 마커 없이 Agent 종료 | 미완료로 판정, 재시도 원칙 적용 |
| `debate-log.json` 없이 Agent 종료 | 산출물은 유효하나 토론 기록 미보존으로 경고 |

### 구현 실패

| 상황 | 처리 |
|------|------|
| 테스트 실패 | 재시도 원칙에 따라 판단 (같은 세션 내) |
| 최대 재시도 후에도 실패 | `impl_status: "failed"`, `reason` 기록. scope가 `"verify"`이면 `verification_status: "skipped"` |
| 실패한 구현에 의존하는 후속 구현 | 함께 스킵 (`impl_status: "skipped"`). scope가 `"verify"`이면 `verification_status: "skipped"` |

### git push 실패 처리

RemoteTrigger 세션 체인은 push 성공을 전제로 한다. push 실패 시:

1. 최대 2회 재시도 (5초 간격 — 원격 서버 일시적 지연에 충분한 대기 시간)
2. 재시도 후에도 실패 → `forge-progress.json`의 `decisions`에 실패 사유 기록 + 텔레그램 알림
3. **RemoteTrigger 체인을 중단한다** (`batch_status`는 `"running"` 유지 — 수동 push 후 재개 가능)
4. 재개 방법: 수동으로 `git push` 후 `RemoteTrigger(action: "run")`을 실행하면 Continue 모드로 정상 재개

`batch_status`를 `"failed"`로 변경하지 않는 이유: push 실패는 일시적 네트워크 문제일 가능성이 높으며, 로컬 커밋은 유효하므로 push만 해결하면 재개 가능하기 때문이다.

## 세션 중단 시 복구

`forge-progress.json`을 우선 확인하고, 센티널 마커로 검증한다:

1. `forge-progress.json` 읽기
2. 각 할일에 대해 센티널 마커와 대조하여 `forge-progress.json` 정확성 검증
3. 구현 상태는 git log와 대조 (`impl_commit` 해시가 실제 존재하는지)
4. 불일치 발견 시 실제 상태 기준으로 `forge-progress.json` 수정
5. 완료된 할일/스테이지는 건너뛰고, 미완료 작업부터 재개
6. 사용자에게 복구 상태 보고 후 RemoteTrigger 재실행

`forge-progress.json`이 없으면 기존 방식(디스크 스캔)으로 복구:
1. `docs/forge/{project}/` 하위 디렉토리 스캔
2. 각 디렉토리에서 산출물 + 센티널 마커 + `debate-log.json` 확인
3. git log에서 구현 커밋 확인
4. 스캔 결과를 기반으로 `forge-progress.json`을 재생성
5. 완료된 할일은 건너뛰고, 미완료 할일부터 재개

## 산출물 구조

```
docs/forge/{project}/
  forge-progress.json                ← 배치 진행 상황 + 트리거 ID
  {todo-slug}/                       # 할일별 독립 디렉토리
    design-spec-agreed.md
    impl-plan-agreed.md
    debate/
      design-spec.md
      design-rulings.md
      impl-plan.md
      impl-rulings.md
      debate-log.json                ← 라운드별 토론 기록
```

## Checklist

1. [ ] 소스 파싱 완료 — 할일 목록 + 변경 대상 파일 + 복잡도 추정
2. [ ] 충돌 분석 완료 — 병렬/순차 그룹 확정, 사용자 승인
3. [ ] 스테이지 분할 완료 — 가중치 기반 분할, 사용자 승인
4. [ ] `forge-progress.json` 초기화 + RemoteTrigger 생성
5. [ ] RemoteTrigger 첫 실행 (자동 실행 시작)
6. [ ] 모든 스테이지 담금질 완료 (각 스테이지 내 할일은 병렬/순차)
7. [ ] 모든 할일 구현 완료 (순차, 세션당 1건)
8. [ ] 각 할일 산출물 + 구현 코드 git commit
9. [ ] 모든 할일 구현점검 완료 (scope가 "verify"인 경우, 순차 세션당 1건)
10. [ ] `forge-progress.json` 기반 전체 결과 보고 + 알림