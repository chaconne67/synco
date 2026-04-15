# Plan Forge Batch — RemoteTrigger 기반 세션 관리 + 구현 실행

## 변경 목적

1. 배치 스킬에서 구현 실행 제한을 제거하여 **담금질 + 구현까지 완전 자동화**
2. RemoteTrigger 기반 세션 클리어로 **컨텍스트 압박 제거**, 구현 품질 보장

## 핵심 원칙

| 원칙 | 이유 |
|------|------|
| 담금질은 병렬 가능 | .md 파일만 생성, 코드 충돌 없음 |
| 구현은 무조건 순차 | 실제 코드를 건드리므로 병렬 금지 |
| 담금질 → 구현 사이에 세션 클리어 | 담금질 컨텍스트가 구현 품질을 오염하지 않도록 |
| 구현 건건마다 세션 클리어 | 각 구현이 항상 fresh context에서 시작 |
| RemoteTrigger로 세션 간 자동 연결 | 사용자 개입 없이 자동 실행 |

## 실행 흐름

### 전체 흐름

```
[사용자 개입 구간 — 최초 1회, 로컬 세션]
소스 파싱 → 충돌 분석 → 스테이지 분할 → 사용자 승인
→ forge-progress.json 초기화
→ RemoteTrigger 생성 + 첫 실행

[자동 실행 구간 — RemoteTrigger 체인, 사용자 개입 없음]

  세션 A: Stage 1 담금질
    ├─ Agent(P10 담금질) ─┐ 병렬
    ├─ Agent(P12 담금질) ─┘
    └─ commit → forge-progress.json 업데이트 → RemoteTrigger

  세션 B: P10 구현
    ├─ impl-plan-agreed.md 읽기
    ├─ subagent-driven-development로 구현
    └─ 테스트 → commit → forge-progress.json 업데이트 → RemoteTrigger

  세션 C: P12 구현
    ├─ impl-plan-agreed.md 읽기
    ├─ subagent-driven-development로 구현
    └─ 테스트 → commit → forge-progress.json 업데이트 → RemoteTrigger

  세션 D: Stage 2 담금질
    ├─ Agent(P11 담금질) — 교차 학습 포함
    └─ commit → forge-progress.json 업데이트 → RemoteTrigger

  세션 E: P11 구현
    └─ ... → RemoteTrigger

  세션 F: P13 구현
    └─ ... → 완료 보고 + 알림
```

### 세션 경계 규칙

| 전환 지점 | 세션 경계 | 이유 |
|----------|---------|------|
| 스테이지 간 | O | 스테이지 독립성 보장 |
| 담금질 → 구현 | O | 담금질 컨텍스트가 구현을 오염하지 않도록 |
| 구현 → 구현 | O | 각 구현이 fresh context에서 시작 |
| 담금질 내 (Agent 병렬) | X | 한 세션에서 병렬 디스패치 |

## 배치 스킬의 두 가지 모드

### Setup 모드 (사용자 로컬 세션)

사용자가 `plan-forge-batch`를 호출하면 실행. 기존 섹션 1~3과 동일:

1. 소스 파싱 → 할일 목록 생성
2. 충돌 분석 → 병렬/순차 판별
3. 스테이지 분할 → 사용자 승인
4. `forge-progress.json` 초기화 (`batch_status: "running"`)
5. RemoteTrigger 생성
6. 첫 번째 trigger 실행

사용자 승인 후 세션 종료. 이후 모든 실행은 자동.

### Continue 모드 (RemoteTrigger 자동 세션)

RemoteTrigger가 새 세션을 시작할 때마다 실행:

1. `forge-progress.json` 읽기
2. 센티널 마커와 대조하여 정합성 검증
3. **다음 액션 결정** (아래 로직)
4. 액션 실행
5. `forge-progress.json` 업데이트 + git commit + git push
6. 배치 미완료 → RemoteTrigger 재실행 / 배치 완료 → 알림 + 종료

## 액션 결정 로직

`forge-progress.json`을 읽어 다음 규칙을 **위에서부터 순서대로** 매칭:

```
1. batch_status가 "complete" 또는 "failed"
   → 종료 (RemoteTrigger 체인 중단)

2. 현재 스테이지에서 tempering_status가 "pending"인 할일이 있음
   → 담금질 세션: 해당 스테이지의 모든 pending 할일을 병렬 담금질

3. 현재 스테이지에서 tempering_status가 "completed"이고
   impl_status가 "pending"인 할일이 있음
   → 구현 세션: 첫 번째 pending 할일 1건만 구현

4. 현재 스테이지의 모든 할일이 impl_status "completed" 또는 "skipped"
   → 스테이지 완료 처리 → 다음 스테이지로 phase 전환 → 규칙 2부터 재평가
   (같은 세션에서 바로 다음 스테이지 담금질을 시작하지 않는다.
    스테이지 완료 처리 후 RemoteTrigger로 새 세션에서 시작한다.)

5. 모든 스테이지 완료
   → batch_status를 "complete"로 변경 → 완료 보고 + 알림
```

### 현재 스테이지 판별

`stages` 배열에서 `phase`가 `"complete"`가 아닌 첫 번째 스테이지가 현재 스테이지.

## 담금질 세션 상세

기존 배치 스킬의 섹션 4와 동일하되, 디스패치 프롬프트를 변경:

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
    저장한 후 plan-forge 스킬의 워크플로우를 따르되,
    **구현담금질까지만** 실행하라.
    구현실행은 배치 오케스트레이터가 별도 세션에서 관리한다.
    
    {소스 문서 내용 — Context Snapshot Rules 적용}
    
    ## 진입점
    {design → 설계담금질부터 | impl → 구현담금질부터}
    
    {교차 학습 섹션 — 이전 스테이지 이슈가 있을 때만}
```

**변경점:** "구현실행은 포함하지 않는다" → "구현실행은 배치 오케스트레이터가 별도 세션에서 관리한다"
— 이 변경은 의미를 명확히 하기 위함. 담금질 Agent 자체는 여전히 구현을 하지 않는다.
병렬 Agent가 코드를 건드리면 충돌이 발생하기 때문. 구현은 오케스트레이터가
별도 세션에서 순차적으로 1건씩 실행한다.

### 담금질 세션 완료 시

1. 각 할일의 산출물 확인 (`*-agreed.md` + 센티널 마커 + `debate-log.json`)
2. 각 할일의 `tempering_status`를 `"completed"` 또는 `"failed"`로 업데이트
3. 스테이지 `phase`를 `"implementing"`으로 변경
4. git commit + git push
5. RemoteTrigger 실행 → 다음 세션(구현)으로 이동

## 구현 세션 상세

### 실행 규칙

- **세션당 1건만 구현한다.** 1건 완료 후 반드시 RemoteTrigger로 새 세션을 시작한다.
- 확정 구현계획서 (`impl-plan-agreed.md`)를 source로 사용한다.
- `superpowers:subagent-driven-development` 스킬을 사용하여 구현한다.
- 구현 완료 후 테스트를 실행하여 통과를 확인한다.

### 구현 세션 흐름

```
1. forge-progress.json 읽기
2. 현재 스테이지에서 impl_status가 "pending"인 첫 번째 할일 식별
3. 해당 할일의 impl-plan-agreed.md 읽기
4. impl_status를 "running"으로 업데이트 + commit
5. superpowers:subagent-driven-development 스킬로 구현 실행
6. 테스트 실행 (uv run pytest -v)
7. 성공 시:
   - 구현 코드 commit (impl 커밋 — forge 문서 커밋과 별도)
   - impl_status를 "completed"로, impl_commit에 커밋 해시 기록
8. 실패 시:
   - impl_status를 "failed"로, reason에 실패 사유 기록
   - 1회 재시도 후에도 실패하면 스킵
9. forge-progress.json 업데이트 + commit + push
10. RemoteTrigger 실행
```

### 구현 실패 처리

| 상황 | 처리 |
|------|------|
| 테스트 실패 | 1회 재시도 (같은 세션 내) |
| 재시도 후에도 실패 | `impl_status: "failed"`, `reason` 기록, 다음 할일로 이동 |
| 의존하는 후속 구현 | 함께 스킵 (`impl_status: "skipped"`) |

## forge-progress.json 스키마 변경

### 추가 필드

**Top level:**

```json
{
  "project": "{project}",
  "total_todos": 8,
  "created_at": "2026-04-08T10:00:00Z",
  "batch_status": "running",
  "trigger_id": "trg_abc123",
  "stages": [...]
}
```

- `batch_status`: `"setup"` | `"running"` | `"complete"` | `"failed"`
- `trigger_id`: RemoteTrigger ID (세션 체인에 사용)

**Per stage:**

```json
{
  "stage": 1,
  "phase": "implementing",
  "todos": [...],
  "summary": null
}
```

- `phase`: `"tempering"` | `"implementing"` | `"complete"`

**Per todo:**

```json
{
  "slug": "P10",
  "tempering_status": "completed",
  "impl_status": "pending",
  "impl_commit": null,
  "entry_point": "design",
  "complexity": "medium",
  "artifacts": ["design-spec-agreed.md", "impl-plan-agreed.md"],
  "committed": true,
  "debate_summary": {
    "design": {"rounds": 2, "issues": 3, "accepted": 2, "rebutted": 1, "escalated": 0},
    "impl": {"rounds": 3, "issues": 5, "accepted": 3, "rebutted": 2, "escalated": 0}
  }
}
```

- `tempering_status`: `"pending"` | `"completed"` | `"failed"`
- `impl_status`: `"pending"` | `"running"` | `"completed"` | `"failed"` | `"skipped"`
- `impl_commit`: 구현 커밋 해시 (완료 시 기록)

### 기존 `status` 필드 제거

기존 `status` 필드를 `tempering_status` + `impl_status`로 분리한다.
마이그레이션: `status: "completed"` → `tempering_status: "completed"`, `impl_status: "pending"`.

## RemoteTrigger 설정

### 트리거 생성 (Setup 모드에서)

```
RemoteTrigger(action: "create", body: {
  "name": "forge-batch-{project}",
  "prompt": "plan-forge-batch 스킬을 continue 모드로 실행하라.\n\nforge-progress.json 경로: docs/forge/{project}/forge-progress.json\n\n1. forge-progress.json을 읽어 다음 액션을 결정하라\n2. 액션을 실행하라\n3. forge-progress.json을 업데이트하라\n4. 배치가 완료되지 않았으면 RemoteTrigger(action: run, trigger_id: {self})를 실행하라\n5. 완료되었으면 텔레그램 알림을 보내라",
  "max_turns": 200
})
```

### 트리거 체인

각 세션 종료 시:
1. `forge-progress.json` 업데이트 + git commit + git push
2. `RemoteTrigger(action: "run", trigger_id: "{trigger_id}")` 실행
3. 현재 세션 종료 (트리거가 새 세션을 시작함)

### 완료 시

1. `batch_status`를 `"complete"`로 변경
2. `forge-progress.json` 최종 커밋 + push
3. 텔레그램 알림 발송 (설정된 경우)
4. RemoteTrigger 체인 종료 (더 이상 run 하지 않음)

## 보고

### 스테이지 완료 시 (forge-progress.json에 기록)

```
Stage 1 완료:
  담금질: ✓ P10 (설계2R/구현3R), ✓ P12 (설계1R/구현2R)
  구현: ✓ P10 (abc1234), ✓ P12 (def5678)
```

### 전체 완료 시 (텔레그램 알림)

```
배치 포지 완료: {project}
  Stage 1: ✓ P10, ✓ P12 — 담금질+구현 완료
  Stage 2: ✓ P11, ✓ P13 — 담금질+구현 완료

성공: 4/4, 실패: 0/4
```

## SKILL.md 수정 요약

### 변경 사항

1. **원칙 섹션** — "오케스트레이션만" → "오케스트레이션 + 구현 실행 관리"
2. **워크플로우 다이어그램** — 구현 실행 단계 + RemoteTrigger 체인 추가
3. **섹션 4 디스패치 프롬프트** — "구현실행은 포함하지 않는다" → "구현실행은 배치 오케스트레이터가 별도 세션에서 관리한다"
4. **새 섹션: RemoteTrigger 기반 세션 관리** — Setup/Continue 모드, 트리거 생성/체인
5. **새 섹션: 액션 결정 로직** — forge-progress.json 기반 상태 머신
6. **새 섹션: 구현 실행** — 순차 실행, 세션당 1건, subagent-driven-development 사용
7. **forge-progress.json 스키마** — `batch_status`, `trigger_id`, `phase`, `tempering_status`, `impl_status`, `impl_commit` 추가
8. **보고 섹션** — 구현 결과 포함
9. **체크리스트** — 구현 관련 항목 추가
