---
name: plan-forge
description: >
  Use when you need a gap-free, battle-tested implementation plan.
  Triggers: "계획 검증", "plan-forge", "forge a plan", or when the cost of a bad
  plan is high (large scope, production-critical changes, multi-phase projects).
  For multiple todos, use plan-forge-batch instead.
---

# Plan Forge — Adversarial Consensus Planning

**Core loop:** 저자가 문서 작성 → 레드팀이 비판 → 저자가 반박 → 합의될 때까지 반복.

**Goal:** 최종 산출물은 **확정 구현계획서** (`impl-plan-agreed.md`). 설계서는 중간 산출물이다 — 구현계획서 초안이 이미 존재하면 곧바로 구현담금질로 진입한다.

## When to Use

- New feature or project that needs a solid, stress-tested plan
- Complex changes where a single AI perspective isn't enough
- When the cost of a bad plan is high (large scope, production-critical)

## When NOT to Use

- Simple bug fixes or single-file changes
- Tasks where implementation path is obvious
- When user explicitly wants to skip planning
- **할일이 여러 개일 때** → `plan-forge-batch` 사용

## 워크플로우

```
사전점검 ─── 환경/의존성 확인, 실패 시 중단
    │
문서탐색 ─── 기존 산출물 감지, 진입점 결정
    │
    ├─ 산출물 없음 ──────────── 브레인스토밍 ─── 설계서 초안 작성
    │                               │
    ├─ 설계서 초안 발견 ─────── 설계담금질 ─── 적대적 공방으로 설계서 벼림
    │                               │
    │                           구현계획 수립 ─── 확정 설계서 기반 구현계획서 작성
    │                               │
    ├─ 구현계획서 초안 발견 ──── 구현담금질 ─── 적대적 공방으로 구현계획서 벼림
    │                               │
    └─ 확정 구현계획서 발견 ──── 완료 (구현은 별도 수행)
```

## 용어 규칙

### 역할

| 명칭 | 대상 |
|------|------|
| **레드팀** | 비판적 리뷰어 (codex든 agent 서브에이전트든 구현 수단 무관) |
| **저자** | 문서 작성·반박 주체 (메인 Claude 세션) |

### 총칭 금지

아래 총칭은 사용하지 않는다. 항상 구체 명칭을 사용한다.

| 금지 총칭 | 사용할 구체 명칭 |
|----------|----------------|
| ~~합의본~~ | 확정 설계서 / 확정 구현계획서 |
| ~~초안~~ | 설계서 초안 / 구현계획서 초안 |

## 산출물 구조

```
docs/forge/{topic}/
  design-spec-agreed.md         # 확정 설계서 (설계담금질 산출물)
  impl-plan-agreed.md           # 확정 구현계획서 (구현담금질 산출물) ← 최종 목표
  debate/
    design-spec.md              # 설계서 초안 (브레인스토밍 산출물)
    design-rulings.md           # 설계 쟁점 판정 결과
    impl-plan.md                # 구현계획서 초안 (구현계획 수립 산출물 또는 외부 투입)
    impl-rulings.md             # 구현 쟁점 판정 결과
    debate-log.json             # 라운드별 토론 기록 (구조화된 과정 로그)
```

### 센티널 마커

각 확정 문서(`*-agreed.md`)의 마지막 줄에 기록. 파일 존재 + 이 마커가 있어야 완료로 인정.

```html
<!-- forge:{topic}:{단계명}:complete:{ISO 8601 timestamp} -->
```

### 토론 로그 (`debate-log.json`)

담금질 라운드의 구조화된 기록. 쟁점 판정 결과(`*-rulings.md`)가 사람이 읽는 판결문이라면, `debate-log.json`은 기계가 읽는 라운드별 과정 기록이다.

**용도:**
- `plan-forge-batch`에서 서브에이전트 종료 후에도 토론 과정 보존
- 실패한 할일 재시도 시 이전 토론 맥락 복원
- 같은 프로젝트 할일 간 교차 학습

**포맷:**

```json
{
  "topic": "{topic}",
  "stages": {
    "design-tempering": {
      "status": "completed|in_progress|failed",
      "rounds": [
        {
          "round": 1,
          "issues": [
            {
              "id": "D-R1-01",
              "severity": "CRITICAL|MAJOR|MINOR",
              "title": "issue title",
              "attack": "red-team's argument summary",
              "action": "accepted|rebutted|partial",
              "response": "author's response summary",
              "evidence_type": "code_reference|execution_result|logical_reasoning",
              "resolved": true
            }
          ]
        }
      ],
      "summary": {
        "rounds": 2,
        "issues": 3,
        "accepted": 2,
        "rebutted": 1,
        "escalated": 0
      }
    },
    "impl-tempering": null
  }
}
```

**`resolved` 판정:** `accepted` → `true` (이슈 수용, 공방 종료), `rebutted` → `false` (다음 라운드에서 재공격 가능), `partial` → 수용된 부분만 별도 이슈로 분리하여 `true`, 미수용 부분은 `false`. **주의:** `resolved: false`이더라도 stage `status`가 `"completed"`이면 해당 이슈는 종결된 것이다 (레드팀이 재공격하지 않았거나 라운드 제한 도달). `resolved`는 "저자가 수용했는가"이지 "공방이 끝났는가"가 아니다.

**기록 시점:** 각 담금질 라운드의 저자 반박 완료 직후 해당 라운드를 append. 합의 완료 시 stage `status`와 `summary`를 기록한다.

**진실 소스 우선순위:** 센티널 마커 > `*-agreed.md` > `*-rulings.md` > `debate-log.json`. debate-log는 조회/참조용이며, 완료 판정에 사용하지 않는다.

### 임시 산출물 생명주기

담금질 중 `debate/round-{N}-redteam.md`, `debate/round-{N}-author.md`가 임시 생성된다. **합의 완료 시** round 파일은 삭제하고, 쟁점 판정 결과 파일과 `debate-log.json`만 남긴다.

---

## 사전점검

확인 항목: codex binary (없으면 agent fallback), git repo, 서브스킬 가용성. 하나라도 필수 조건 실패 시 중단.

### 레드팀 모드

| 모드 | 조건 | 레드팀 구현 |
|------|------|------------|
| **codex** | `codex` binary 사용 가능 | Codex (OpenAI) via `run_codex_review.py` |
| **agent** | Codex 불가 또는 실행 중 실패 | Agent 서브에이전트 (레드팀 역할) |

**자동 fallback:** Codex 호출이 non-zero로 실패하면:
1. 사용자에게 `Codex 실패 ({error}). Agent 레드팀으로 전환합니다.` 알림
2. 해당 라운드부터 agent 모드로 전환 (다시 codex로 돌아가지 않음)

### Agent 레드팀

Codex 대신 **Agent 도구로 독립 서브에이전트를 생성**하여 레드팀 역할을 맡긴다.

**핵심 원칙:** 컨텍스트 오염 방지. 현재 대화의 맥락을 모르는 새로운 에이전트로, 편향 없는 비판적 리뷰를 수행한다.

#### Round 1 프롬프트

```
Agent 도구 호출:
  description: "Red-team review: {document_name}"
  prompt: |
    당신은 독립적인 레드팀 리뷰어입니다.
    현재 프로젝트의 {설계서/구현계획서}를 비판적으로 검토해야 합니다.

    ## 리뷰 대상
    파일: {document_path}

    ## 프로젝트 컨텍스트
    {CLAUDE.md에서 추출한 PROJECT CONTEXT}

    {구현담금질인 경우:
    ## 확정 설계서
    {Context Snapshot Rules 적용: 200줄 이하 → 전문, 초과 → 핵심 결정 8-15개 bullet 요약
     + 구현계획서가 참조하는 섹션 원문 발췌 + Source: {design-spec-agreed.md 경로}}}

    ## 리뷰 지침
    - 코드베이스를 직접 읽고, 테스트를 실행하여 주장을 검증하라
    - 설계/구현의 빈틈, 모순, 누락을 찾아라
    - 근거 없는 추측이 아닌 구체적 증거를 제시하라
    - 의심스러우면 지적하라. 놓친 문제는 복구할 수 없다
    - 각 이슈는 저자에 의해 개별적으로 반박될 수 있다.
      반박을 견딜 수 있는 구체적이고 검증 가능한 증거를 제시하라.

    ## 출력 형식
    NUMBER each issue. For each issue provide:
    - SEVERITY: "이 이슈를 무시하고 구현했을 때, 언제 문제가 드러나는가?"
      - CRITICAL: 구현 단계에서 (기능 미동작, 데이터 손실 위험)
      - MAJOR: 운영/부하 상황에서 (성능, 보안, 유지보수성에 심각한 영향)
      - MINOR: 코드 리뷰에서 (개선 기회, 현재 설계로도 동작에 문제 없음)
    - DESCRIPTION: What's wrong
    - EVIDENCE: Quote the specific text or code that has the problem
    - SUGGESTION: How to fix it
```

#### Follow-up 프롬프트 (Round 2+)

미해결 쟁점이 있을 때 Agent 모드로 후속 라운드를 실행하는 프롬프트. Codex 모드는 `references/{design|impl}-followup-prompt.md` 템플릿을 사용한다.

```
Agent 도구 호출:
  description: "Red-team follow-up R{N}: {document_name}"
  prompt: |
    당신은 독립적인 레드팀 리뷰어입니다. 이전 라운드에서 지적한 이슈 중
    일부가 저자에 의해 반박되었습니다. 반박이 타당한지 검증해야 합니다.

    ## 리뷰 대상
    원본 문서: {document_path}
    쟁점 판정 기록: {rulings_path} (Disputed Items 섹션 참조)

    ## 프로젝트 컨텍스트
    {CLAUDE.md에서 추출한 PROJECT CONTEXT}

    {구현담금질인 경우:
    ## 확정 설계서
    {Context Snapshot Rules 적용 — Round 1과 동일}}

    ## 미해결 쟁점
    {각 Disputed Item에 대해:
    ### Issue {N}: {title} [{SEVERITY}]
    YOUR ORIGINAL POINT: {레드팀의 원래 지적}
    AUTHOR'S REBUTTAL: {저자의 반박과 증거}
    EVIDENCE TYPE: CODE REFERENCE / EXECUTION RESULT / LOGICAL REASONING}

    ## 규칙
    - 저자가 코드 참조나 실행 결과를 제시한 경우, 직접 해당 코드/명령을 확인하라
    - 사실적 증거(코드 참조, 실행 결과)는 논리적 추론보다 우선한다
    - 저자의 반박이 타당하면: ACCEPT하고 이유를 설명하라
    - 여전히 동의하지 않으면: **새로운 증거로 새로운 반론**을 제시하라
    - 이전 주장을 새 증거 없이 반복하지 마라. 반복은 concession으로 간주한다.
      이유: 다중 라운드의 목적은 새로운 정보를 발굴하는 것이지,
      상대를 소모시키는 것이 아니다. 새 증거가 없으면 상대 주장이 유지된다.

    ## 출력 형식
    각 미해결 쟁점에 대해:
    - VERDICT: ACCEPT (반박 인정) 또는 CHALLENGE (새 반론)
    - REASONING: 판단 근거
    - NEW EVIDENCE: (CHALLENGE인 경우) 새로운 구체적 증거
```

### 서브스킬 가용성

의존 스킬: `superpowers:brainstorming` (브레인스토밍), `superpowers:writing-plans` (구현계획 수립). 각 단계 시작 시 호출 가능 여부를 확인하고, "skill not found" 시 사용자에게 보고.

### 외부 호출 인터페이스

`plan-forge-batch`에서 호출될 때 적용되는 파라미터 계약.

| 파라미터 | 설명 | 기본값 |
|----------|------|--------|
| `topic` | 식별자 (slug). **슬래시 불포함.** 센티널 마커 `forge:{topic}:...`에 사용 | 사용자 지정 |
| `forge_dir` | 산출물 디렉토리 경로 | `docs/forge/{topic}/` |

- 단독 실행: `topic`만 지정. `forge_dir`은 기본값 사용
- batch에서 호출: `topic`에 할일 slug(예: `P01`), `forge_dir`에 `docs/forge/{project}/{todo-slug}/` 전달
- 센티널 마커는 항상 `forge:{topic}:{단계명}:complete:{timestamp}` 형식. `topic`에 슬래시가 포함되면 안 된다

### `SKILL_DIR` 경로

codex 모드에서 `run_codex_review.py`를 실행할 때 사용하는 `${SKILL_DIR}`은 이 스킬의 base directory이다. 스킬 로딩 시 표시되는 "Base directory for this skill: ..." 경로를 사용한다. bash 환경변수로 자동 설정되지 않으므로, 저자(메인 세션)가 절대경로로 치환하여 실행한다.

---

## 문서탐색

기존 산출물을 스캔하여 진입 단계를 결정한다.

| 감지 조건 (위에서부터 매칭) | 진입 단계 | 실행 흐름 |
|---------------------------|----------|----------|
| `impl-plan-agreed.md` 존재 | 완료 | 이미 확정됨. 구현은 별도 수행 |
| `impl-plan.md` 존재 (debate/ 또는 루트) | 구현담금질 | 구현담금질 → 완료 |
| `design-spec-agreed.md` 존재 | 구현계획 수립 | 구현계획 수립 → 구현담금질 → 완료 |
| `design-spec.md` 존재 (debate/ 또는 루트) | 설계담금질 | 설계담금질 → 구현계획 수립 → 구현담금질 → 완료 |
| 아무것도 없음 | 브레인스토밍 | 전체 흐름 |

### 보고 형식

```
사전점검 결과:
  ✓ git repo: {repo name}
  ✓ sub-skills: available
  레드팀 모드: {codex (v...) | agent}

문서 감지: {감지된 산출물 목록 또는 "없음"}
→ {진입 단계명}부터 시작. 계속 진행합니까?
```

---

## 브레인스토밍

**REQUIRED SUB-SKILL:** Use `superpowers:brainstorming`

Follow the brainstorming skill's full process. **IMPORTANT OVERRIDE:** 완료 시 `writing-plans`를 호출하지 않는다. 대신 `docs/forge/{topic}/debate/design-spec.md`(설계서 초안)로 저장하고 설계담금질로 진행한다.

---

## 설계담금질 + 구현담금질 (공통 구조)

설계담금질과 구현담금질은 동일한 담금질 루프를 따른다. 쟁점 판정 결과 파일 포맷은 `references/consensus-format.md` 참조. 차이점은 아래 테이블 참조.

| 항목 | 설계담금질 | 구현담금질 |
|------|----------|----------|
| 대상 문서 | `debate/design-spec.md` (설계서 초안) | `debate/impl-plan.md` (구현계획서 초안) |
| Round 1 프롬프트 | `references/design-round1-prompt.md` | `references/impl-round1-prompt.md` |
| Follow-up 프롬프트 | `references/design-followup-prompt.md` | `references/impl-followup-prompt.md` |
| 쟁점 판정 결과 파일 | `debate/design-rulings.md` | `debate/impl-rulings.md` |
| 확정 문서 | 확정 설계서 (`design-spec-agreed.md`) | 확정 구현계획서 (`impl-plan-agreed.md`) |
| 센티널 단계명 | `설계담금질` | `구현담금질` |
| 저자 반박 증거 우선순위 | 논리적 추론과 설계 원칙 | **코드 참조 > 실행 결과 > 논리적 추론** |
| 추가 컨텍스트 | — | 확정 설계서 존재 시 Context Snapshot Rules 적용 (아래 참조) |

### Context Snapshot Rules

대상 문서나 참조 문서를 프롬프트에 포함할 때 적용하는 규칙. Codex 템플릿(`references/`)과 Agent 프롬프트 양쪽에 동일하게 적용한다.

| 조건 | 처리 |
|------|------|
| **200줄 이하** | 전문 포함 |
| **200줄 초과** | 핵심 결정 8-15개 bullet 요약 + 관련 섹션 원문 발췌 + `Source: {파일 경로}` |

- 항상 원본 파일 경로를 포함한다 (Agent 모드에서 서브에이전트가 필요 시 직접 읽을 수 있도록)
- 구현담금질의 확정 설계서: 구현계획서가 참조하는 섹션을 발췌 대상으로 우선
- Follow-up 라운드의 대상 문서: 쟁점 관련 섹션을 발췌 대상으로 우선 + `Omitted sections: [list]`

### 레드팀 공격

1. 대상 문서를 읽는다
2. CLAUDE.md에서 `PROJECT CONTEXT`를 추출한다
3. (구현담금질만) 확정 설계서 존재 시 포함 (Context Snapshot Rules 적용)
4. 모드에 따라 프롬프트를 준비한다:
   - **codex 모드:** `references/{design|impl}-round1-prompt.md` 템플릿에 변수를 채워 넣는다
   - **agent 모드:** 아래 "Agent 레드팀" 섹션의 Round 1 프롬프트를 사용한다

**codex 모드 실행:**
```bash
python3 "${SKILL_DIR}/scripts/run_codex_review.py" \
  --repo-dir "$(git rev-parse --show-toplevel)" \
  --prompt-file /tmp/forge-prompt.md
```
Non-zero 실패 시 agent 모드로 자동 fallback.

**agent 모드 실행:** Agent 도구로 레드팀 서브에이전트 생성 (아래 "Agent 레드팀" 섹션 참조).

Save to `debate/round-{N}-redteam.md`.

### 저자 반박

저자는 레드팀의 프레이밍과 무관하게 해당 영역을 독립적으로 평가한다. 레드팀이 "보안 위험"이라고 분류했더라도, 실제 성격에 맞게 재분류하고 평가한다.

**판단 원칙:** "이 이슈가 해결되지 않았을 때 실제 사용자/시스템에 영향이 있는가?"
- 영향 없음: **REBUT** — 구체적 근거를 인용
- 영향 있음: **ACCEPT**
- 일부만 영향 있음: **PARTIAL** — 분리하여 판정

**담금질의 핵심 원칙: 확신 없으면 REBUT하라.**
잘못된 REBUT은 다음 라운드에서 레드팀이 더 강한 증거로 재반박하므로 자기 교정된다. 잘못된 ACCEPT은 해당 항목의 공방이 즉시 종료되어 복구 경로가 없다. 저자의 역할은 레드팀의 주장을 **검증**하는 것이지, 수용하는 것이 아니다.

(구현담금질에서) REBUT 시 반드시 `evidence_type`을 명시: `code_reference` > `execution_result` > `logical_reasoning`. 이 값은 `debate-log.json`에도 동일하게 기록한다.

Save to `debate/round-{N}-author.md`.

### 토론 로그 기록

저자 반박 완료 직후, 해당 라운드를 `debate/debate-log.json`에 append한다.

1. 파일이 없으면 초기 구조 생성 (`topic`, `stages` 키)
2. 현재 담금질 단계의 `rounds` 배열에 라운드 객체 추가
3. 각 이슈의 `id`, `severity`, `title`, `attack`(레드팀 주장 1-2문장 요약), `action`, `response`(저자 반박 1-2문장 요약), `evidence_type`, `resolved` 기록
4. stage `status`를 `"in_progress"`로 설정

**요약은 간결하게.** `attack`과 `response`는 원문 전체가 아닌 핵심 논거 1-2문장 요약. 상세 원문은 `*-rulings.md`에 있다.

### 합의 판정

심각도별 종료 조건:

| Severity | 라운드 제한 | 종료 조건 |
|----------|-----------|----------|
| **CRITICAL** | soft cap 7 | 7라운드 후 또는 순환 논증 감지 시 → 사용자 에스컬레이션 |
| **MAJOR** | 최대 5 | 5라운드 후 미해결 → 사용자 에스컬레이션 |
| **MINOR** | 최대 3 | 3라운드 후 미해결 → 자동으로 사용자 에스컬레이션 |

**순환 논증 감지:** 양측이 새로운 증거 없이 같은 주장을 반복하면 즉시 사용자 에스컬레이션.

**Short-circuit:** Round 1에서 CRITICAL/MAJOR가 0개면 사용자에게 묻는다:
```
CRITICAL/MAJOR 이슈 없음. MINOR {N}개.
A) 전체 담금질 프로세스 계속 B) MINOR만 빠르게 처리하고 다음 단계로
```

**미해결 쟁점이 남은 경우:**
- **codex 모드:** `references/{design|impl}-followup-prompt.md` 템플릿에 변수를 채워 다음 라운드를 실행한다.
- **agent 모드:** "Agent 레드팀 > Follow-up 프롬프트 (Round 2+)" 섹션의 프롬프트를 사용한다.

에스컬레이션 시 양측 입장을 정리하여 사용자에게 결정을 요청. `USER_DECIDED`로 기록.

### 합의 적용

모든 항목이 RESOLVED 또는 USER_DECIDED이면:

1. 대상 문서에 합의된 변경을 적용
2. 확정 문서를 토픽 루트에 저장 (not debate/)
3. 센티널 마커를 마지막 줄에 추가
4. 쟁점 판정 결과 파일 status를 COMPLETE로 변경
5. `debate-log.json`의 해당 stage `status`를 `"completed"` (또는 `"failed"`)로, `summary` 집계 기록
6. **`debate/round-*` 파일 전부 삭제** — 쟁점 판정 결과와 `debate-log.json`만 남긴다

사용자에게 담금질 결과 보고 후 다음 단계로 진행.

---

## 구현계획 수립

**REQUIRED SUB-SKILL:** Use `superpowers:writing-plans`

- 확정 설계서(`design-spec-agreed.md`)를 source spec으로 사용 (NOT the original)
- `docs/forge/{topic}/debate/impl-plan.md`(구현계획서 초안)로 저장
- 구현담금질로 진행


## Checklist

1. [ ] 사전점검 통과
2. [ ] 문서탐색 완료, 진입 단계 결정
3. [ ] 브레인스토밍 완료, 설계서 초안 작성 *(기존 산출물 있으면 skip)*
   **writing-plans를 호출하지 않는다. 설계담금질로 직행.**
4. [ ] 설계담금질 완료 — 확정 설계서 저장 + 센티널 마커 *(구현계획서 초안 있으면 skip)*
5. [ ] 구현계획 수립 완료 — 구현계획서 초안 작성 *(구현계획서 초안 있으면 skip)*
6. [ ] 구현담금질 완료 — 확정 구현계획서 저장 + 센티널 마커
