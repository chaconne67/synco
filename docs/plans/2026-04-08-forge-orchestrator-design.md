# plan-forge 오케스트레이터 설계서

> **날짜:** 2026-04-08
> **배경:** plan-forge 스킬을 19개 phase에 실행했을 때 컨텍스트 압력으로 Step 2.5 누락, Phase 3-5 미진입 발생. forge-index.md가 "설계 리뷰 완료 = 전체 완료"로 프레이밍하여 모델의 scope를 좁힘.
> **목표:** plan-forge 스킬에 세션 기반 오케스트레이터를 추가하여, phase별 독립 세션으로 컨텍스트 압력을 해소하고 완전 무인 실행을 지원한다.

---

## 1. 실행 모델

### 기존 → 변경

| 항목 | 기존 | 변경 |
|------|------|------|
| 실행 단위 | 한 세션에서 모든 phase | **1 phase = 2 세션** |
| 상태 관리 | forge-index.md (markdown) | **forge-state.json** (기계 읽기) + forge-index.md (자동 생성) |
| Phase 5 | 사용자 선택 (실행 or 중단) | **항상 실행** |
| Phase 1 | 세션 내 brainstorming | **오케스트레이터 범위 밖** (수동 실행) |
| 상태 쓰기 | Claude + 오케스트레이터 혼재 | **단일 쓰기 원칙** |

### 세션 분리

| 세션 유형 | 실행 Step | 근거 |
|----------|----------|------|
| `document` | Phase 2(설계리뷰) → 3(구현계획) → 4(구현리뷰) | 문서 작업. ~2000줄, 한 세션으로 충분 |
| `execution` | Phase 5(구현실행) | 코드 작성. 컨텍스트 소모 큼, 별도 세션 필수 |

각 세션 완료 시 git commit으로 상태 저장. 비정상 종료 시 step 단위로 분할 재시도.

---

## 2. 상태 관리 구조

### 파일 레이아웃

forge 디렉토리 기본값은 `docs/forge/{project}/`이며, `--forge-dir` 옵션으로 변경 가능하다.

```
{forge-dir}/
  forge-state.json          ← 오케스트레이터 단독 쓰기/읽기
  forge-index.md            ← forge-state.json에서 자동 생성 (읽기 전용)
  {phase}/
    status.json             ← Claude 세션이 쓰기, 오케스트레이터가 읽기
    design-spec-agreed.md   ← Phase 2 산출물
    impl-plan-agreed.md     ← Phase 4 산출물
    debate/
      design-spec.md        ← 설계서 초안
      design-consensus.md   ← 설계 토론 합의 요약
      impl-plan.md          ← 구현계획 초안
      impl-consensus.md     ← 구현 토론 합의 요약
```

### 단일 쓰기 원칙

| 파일 | 쓰기 주체 | 읽기 주체 |
|------|----------|----------|
| `forge-state.json` | 오케스트레이터만 | 오케스트레이터 |
| `forge-index.md` | 오케스트레이터만 (자동 생성) | 사람 |
| `{phase}/status.json` | Claude 세션만 | 오케스트레이터 |
| `{phase}/*.md` | Claude 세션만 | Claude 세션, 오케스트레이터(검증용) |

### forge-state.json

```json
{
  "project": "{project}",
  "source": "{source_path}",
  "phases": {
    "p01": {
      "batch": 1,
      "deps": [],
      "doc_type": "design",
      "steps": {
        "design_draft": "done",
        "design_review": "done",
        "impl_plan": "pending",
        "impl_review": "pending",
        "execution": "pending"
      },
      "current": "impl_plan"
    },
    "p02": {
      "batch": 2,
      "deps": ["p01"],
      "doc_type": "design",
      "steps": {
        "design_draft": "done",
        "design_review": "done",
        "impl_plan": "pending",
        "impl_review": "pending",
        "execution": "pending"
      },
      "current": "blocked:p01"
    }
  },
  "execution_log": [
    {
      "phase": "p01",
      "step": "design_review",
      "session": "session-001",
      "started": "2026-04-08T14:00:00",
      "result": "done",
      "commit": "a1b2c3d"
    }
  ]
}
```

**상태값:** `done`, `pending`, `skip`, `blocked:{phase}`

### phase별 status.json (Claude 세션 산출물)

```json
{
  "phase": "p01",
  "step_completed": "impl_review",
  "sentinel": true,
  "timestamp": "2026-04-08T14:32:00",
  "artifacts": {
    "design-spec-agreed.md": "created",
    "impl-plan-agreed.md": "created",
    "debate/round-files": "cleaned"
  },
  "next_step": "execution"
}
```

---

## 3. 입력 감지 & 초기화

오케스트레이터 첫 실행 시 입력 상태를 감지하여 forge-state.json을 생성한다.

### 입력 매트릭스

| # | 입력 상태 | 감지 조건 | 처리 |
|---|----------|----------|------|
| 1 | 파일 없음 | 대상 경로 비어있거나 미존재 | **오케스트레이터 범위 밖.** Phase 1(brainstorming)은 사람이 수동 실행 후 재시도 |
| 2 | 설계서 1개 | `*.md` 1개, doc_type=design (사용자 지정) | forge-state 1행, `design_draft=done`, Phase 2부터 |
| 3 | 구현계획서 1개 | `*.md` 1개, doc_type=impl (사용자 지정) | forge-state 1행, `design_*=skip, impl_plan=done`, Phase 4부터 |
| 4 | 여러 파일 flat | 디렉토리에 `*.md` 복수, 서브폴더 없음 | 파일당 1행. 의존성 없음 → Batch 모두 1 |
| 5 | 서브폴더+README | README에 의존성 테이블 존재 | README 파싱 → 의존성 기반 Batch 산출 |
| 6 | forge-state.json 존재 | 파일 존재 | **파일 검증 후** 재개 |

### 문서 유형 판별

자동 판별을 하지 않는다. 초기화 시 사용자가 명시한다.

```bash
# 초기화 예시
./forge-runner.sh init {project} --source {path} --doc-type {design|impl}
```

---

## 4. 오케스트레이터 메인 루프

```bash
#!/bin/bash
# forge-runner.sh

FORGE_DIR="${FORGE_DIR:-docs/forge/$PROJECT}"
STATE="$FORGE_DIR/forge-state.json"

# 1. 상태 검증: forge-state의 주장 vs 실제 파일 + 센티널
validate_state "$STATE"

# 2. 메인 루프
while true; do
    NEXT=$(get_next_phase "$STATE")
    
    [[ "$NEXT" == "ALL_DONE" ]] && { log "전체 완료"; break; }
    [[ "$NEXT" == "ALL_BLOCKED" ]] && { log "모든 phase blocked"; break; }
    
    PHASE=$(echo "$NEXT" | jq -r '.phase')
    STEP=$(echo "$NEXT" | jq -r '.step')
    SESSION_TYPE=$(echo "$NEXT" | jq -r '.session_type')
    
    # 3. 세션 실행
    log "[$PHASE] $STEP 시작 (type: $SESSION_TYPE)"
    run_session "$PHASE" "$STEP" "$SESSION_TYPE"
    EXIT_CODE=$?
    
    # 4. 결과 확인 & 실패 처리
    if [[ $EXIT_CODE -ne 0 ]]; then
        handle_failure "$PHASE" "$STEP" "$EXIT_CODE"
        continue
    fi
    
    # 5. phase/status.json → forge-state.json 동기화
    sync_phase_status "$PHASE"
    
    # 6. git commit
    commit_phase "$PHASE" "$STEP"
    
    # 7. forge-index.md 재생성
    regenerate_index "$STATE"
    
    # 8. blocked phase 해제 검사
    update_blocked_phases "$STATE"
done
```

### get_next_phase 로직

```
for phase in phases (batch 오름차순, 같은 batch 내 순차):
    if phase.current == blocked:{dep}:
        # 선행 phase의 impl_review가 done이면 unblock
        if all(phases[dep].steps.impl_review == "done" for dep in phase.deps):
            phase.current = next_pending_step(phase)
    
    if phase.current not in (done, blocked:*):
        session_type = "execution" if phase.current == "execution" else "document"
        # document 세션은 current부터 impl_review까지 한 세션으로 묶음
        # build_prompt가 current에 따라 필요한 step 블록만 조합
        return {phase, step: phase.current, session_type}

return ALL_DONE (또는 ALL_BLOCKED)
```

**의존성 해제 조건:** 선행 phase의 `impl_review`가 `done` (impl-plan-agreed.md 존재). 구현실행 완료를 기다리지 않는다.

### 세션 실행

```bash
run_session() {
    local PHASE=$1 STEP=$2 TYPE=$3
    local PROMPT=$(build_prompt "$PHASE" "$STEP" "$TYPE")
    local LOG="logs/forge-${PHASE}-${STEP}-$(date +%Y%m%dT%H%M%S).log"
    
    claude --print "$PROMPT" \
        --allowedTools "Read,Write,Edit,Bash,Agent,Glob,Grep,Skill" \
        --output-format text \
        2>"$LOG"
}
```

### 실패 처리

```
실패 감지: exit code != 0 또는 status.json 미생성 또는 센티널 미확인

재시도 1-2회:
  - 센티널 없는 불완전 산출물 삭제
  - 동일 step 재실행 (멱등)

2회 실패:
  - document 세션인 경우 → step 분할 모드로 전환
    (Phase 2만 실행 → commit → Phase 3-4 실행 → commit)
  - execution 세션인 경우 → 오케스트레이터 중단 + 로그 출력

git commit 실패:
  - git stash → 오케스트레이터 중단 → 로그에 stash ref 기록
```

---

## 5. 세션 프롬프트 템플릿

### 프롬프트 생성 로직

`build_prompt`는 `current` step에 따라 필요한 step만 포함한 프롬프트를 생성한다.

| current | 포함 step | 세션 유형 |
|---------|----------|----------|
| `design_review` | Phase 2 → 3 → 4 | document |
| `impl_plan` | Phase 3 → 4 (설계리뷰 이미 완료) | document |
| `impl_review` | Phase 4만 (구현계획 이미 작성) | document |
| `execution` | Phase 5 | execution |

각 step 블록은 독립적이며, `build_prompt`가 해당하는 블록만 조합한다.

### document 세션 프롬프트 구조

```markdown
# Forge Session: {phase} — {session_description}

당신은 plan-forge 스킬의 한 세션입니다.
이 세션의 범위: **{phase}의 {step_range_description}**
이 세션에서 구현(코드 작성)은 하지 않습니다.

## 프로젝트 컨텍스트
- CLAUDE.md를 읽어라
- forge 디렉토리: {forge_dir}/{phase}/

## 선행 Phase 변경사항
{upstream_changes 또는 "없음"}

## 이미 완료된 산출물
{existing_artifacts 또는 "없음"}

## 실행 순서

{step_blocks — current에 따라 아래에서 필요한 블록만 포함}

## 완료 조건
{completion_checklist — 포함된 step에 해당하는 항목만}

## 마지막 필수 작업
모든 완료 조건 충족 후, 반드시 {phase}/status.json을 작성하라:

    {
      "phase": "{phase}",
      "step_completed": "{last_step}",
      "sentinel": true,
      "timestamp": "{ISO 8601}",
      "artifacts": { ... },
      "next_step": "{next_step}"
    }

센티널 마커 형식 (각 agreed 파일 마지막 줄):
<!-- forge:{phase}:{step}:complete:{timestamp} -->
```

### step 블록 (개별 조각)

**Phase 2 블록 (설계 adversarial review):**
```markdown
### 설계 adversarial review (Phase 2)
1. debate/design-spec.md를 읽어라
2. Codex 또는 Agent 레드팀 리뷰를 실행하라
3. 각 이슈에 대해 ACCEPT/REBUT/PARTIAL 판정하라
4. 합의될 때까지 반복하라 (CRITICAL 최대 7라운드, MAJOR 최대 5라운드)
5. 합의 완료 시:
   - design-spec-agreed.md를 phase 루트에 저장하라 (센티널 마커 포함)
   - debate/round-* 파일을 삭제하라
   - debate/design-consensus.md만 남겨라
```

**Phase 3 블록 (구현계획 작성):**
```markdown
### 구현계획 작성 (Phase 3)
1. design-spec-agreed.md를 기반으로 구현계획을 작성하라
2. superpowers:writing-plans 스킬을 호출하라
3. debate/impl-plan.md로 저장하라
```

**Phase 4 블록 (구현계획 adversarial review):**
```markdown
### 구현계획 adversarial review (Phase 4)
1. debate/impl-plan.md를 읽어라
2. Phase 2와 동일한 adversarial review를 실행하라
3. 반박 시 코드 참조, 실행 결과를 우선 증거로 사용하라
4. 합의 완료 시:
   - impl-plan-agreed.md를 phase 루트에 저장하라 (센티널 마커 포함)
   - debate/round-* 파일을 삭제하라
   - debate/impl-consensus.md만 남겨라
```

### execution 세션 (Phase 5)

```markdown
# Forge Session: {phase} — Implementation Execution

당신은 plan-forge 스킬의 구현 세션입니다.
이 세션의 범위: **{phase}의 impl-plan-agreed.md에 따라 코드를 구현**

## 구현계획
{forge_dir}/{phase}/impl-plan-agreed.md를 읽어라.

## 실행 방법
superpowers:subagent-driven-development 스킬을 호출하여
impl-plan-agreed.md를 입력으로 구현을 실행하라.

## 완료 조건
- impl-plan-agreed.md의 모든 항목 구현 완료
- 프로젝트의 테스트 커맨드 실행 및 통과 (CLAUDE.md에서 테스트 커맨드를 확인하라)

## 마지막 필수 작업
{phase}/status.json 작성:

    {
      "phase": "{phase}",
      "step_completed": "execution",
      "sentinel": true,
      "timestamp": "{ISO 8601}",
      "test_result": "pass|fail",
      "next_step": "done"
    }
```

---

## 6. 상태 검증

매 세션 시작 전 오케스트레이터가 forge-state.json의 주장을 실제 파일로 검증한다.

### 검증 규칙

| 상태 주장 | 검증 대상 | 검증 방법 |
|----------|----------|----------|
| `design_draft: done` | `debate/design-spec.md` | 파일 존재 + 10줄 이상 |
| `design_review: done` | `design-spec-agreed.md` | 파일 존재 + 센티널 마커 |
| `impl_plan: done` | `debate/impl-plan.md` | 파일 존재 + 10줄 이상 |
| `impl_review: done` | `impl-plan-agreed.md` | 파일 존재 + 센티널 마커 |
| `execution: done` | `status.json` | `step_completed=execution` + `test_result=pass` |

**불일치 시:** 해당 step을 `pending`으로 강제 보정하고 로그에 경고 기록.

### 센티널 마커

```html
<!-- forge:{phase}:{step}:complete:{ISO 8601 timestamp} -->
```

각 agreed 파일의 마지막 줄에 위치. 파일 존재 + 이 마커가 있어야 `done` 인정.

---

## 7. 안전장치 요약

| 장치 | 목적 | 동작 |
|------|------|------|
| 센티널 마커 | 부분 완료 감지 | 파일 끝에 마커 없으면 미완료 취급 |
| status.json | 세션 완료 신호 | 오케스트레이터가 이걸 읽어야 다음 진행 |
| 상태 검증 | forge-state 정합성 | 매 세션 전 파일 vs 주장 크로스체크 |
| 재시도 2회 | 일시적 실패 복구 | 2회 실패 시 step 분할 모드 |
| 라운드 캡 | 무한 토론 방지 | CRITICAL 7R, MAJOR 5R, MINOR 3R → 자동 에스컬레이션 |
| 세션 로그 | 디버깅 | `logs/forge-{phase}-{step}.log` 세션별 분리 |
| git commit | 상태 영속화 | 매 세션 완료 후 자동 커밋 |

---

## 8. CLI 인터페이스

```bash
# 초기화: 소스 문서에서 forge-state.json 생성
./forge-runner.sh init {project} --source {path} --doc-type {design|impl}

# forge 디렉토리 변경 (기본값: docs/forge/{project}/)
./forge-runner.sh init {project} --source {path} --doc-type design --forge-dir {path}

# 실행: 전체 자동 실행
./forge-runner.sh run {project}

# 특정 phase만
./forge-runner.sh run {project} --phase {phase}

# 상태 확인
./forge-runner.sh status {project}

# 재개: forge-state.json 기반으로 중단된 지점부터
./forge-runner.sh run {project}  # (자동으로 재개)
```

---

## 9. 기존 산출물 마이그레이션

기존 forge 산출물이 스킬 명세와 다른 디렉토리 구조를 사용하는 경우 (예: `design-debate/` vs `debate/`), 오케스트레이터 실행 전 정규화가 필요하다.

오케스트레이터 `init` 단계에서 기존 산출물을 감지하면:
1. 비표준 디렉토리명(`*-debate/`)을 `debate/`로 정규화
2. phase 루트에 있는 초안 파일(`design-spec.md`)을 `debate/`로 이동
3. 정규화 결과를 로그에 기록

---

## 10. 향후 확장

- **V1 (현재 설계):** 같은 Batch 내 phase 순차 실행
- **V2:** 같은 Batch 내 병렬 실행 (`claude --print` 프로세스를 `&`로 분기, `wait`로 대기). forge-state.json 구조가 이미 병렬을 지원하므로 오케스트레이터 루프만 수정.
