---
date: 2026-04-13
status: in-progress
related_plan: 2026-04-13-tts-phase-1-forge-batch-engine.md
related_spec: 2026-04-12-taste-to-ship-design.md (v5)
---

# tts Phase 1 — Resume Handoff

컨텍스트 포화로 새 세션에서 이어서 진행하기 위한 상태 스냅샷과 재개 가이드.

## 어디까지 진행됐나 (10/15 완료)

### 완료된 태스크

| # | Task | 상태 | 비고 |
|---|---|---|---|
| 1 | 라이브러리 초기화 + 로컬 git | ✅ | `.gitignore`에 `.venv/`, `*.egg-info/` 추가 (코드 리뷰 개선) |
| 2 | `progress.py` 실패 테스트 (TDD red) | ✅ | 12 tests, ModuleNotFoundError로 실패 확인 |
| 3 | `progress.py` 구현 (TDD green) | ✅ | **코드 리뷰 픽스 반영:** 4가지 개선 (orphan temp file cleanup, dotted path 검증, `_cli` AssertionError fallthrough, stale docstring) |
| 4 | `sentinel.py` 실패 테스트 (TDD red) | ✅ | 13 tests |
| 5 | `sentinel.py` 구현 (TDD green) | ✅ | `_cli` fallthrough assertion 포함 (progress.py 패턴 일관성) |
| 6 | `watchdog.sh` 이식 + 통합 테스트 | ✅ | `plan-forge-batch/watchdog.sh`에서 포팅, `progress.py` CLI로 JSON 접근 |
| 7 | `journal.sh` + 통합 테스트 | ✅ | `journal_append` 함수 |
| 8 | `session-chain.sh` + 통합 테스트 | ✅ | mock claude로 검증 |
| 9 | `env-cleanup.sh` 함수 5개 | ✅ | `check_existing_tts_stashes`, `stash_uncommitted_work`, `clean_temp_forge_files`, `check_stale_lock_files`, `check_port_held` |
| 10 | `env-cleanup.sh` 통합 테스트 | ✅ | 실제 git repo + 실제 Python 소켓 리스너 + 실제 프로세스 |

### 남은 태스크 (5개)

- **Task 11**: 전체 스위트 체크포인트 실행 (pytest + 모든 통합 테스트)
- **Task 12**: `examples/minimal-usage.md` 작성
- **Task 13**: `README.md` 완전한 API 레퍼런스 작성
- **Task 14**: 엔드투엔드 스모크 테스트 (`test_smoke_e2e.sh`)
- **Task 15**: 최종 검증 (pytest + 통합 한 번 더, git log 확인)
- **Final review**: Phase 1 전체 대한 code-reviewer 서브에이전트 디스패치

각 태스크의 정확한 내용과 EXACT 코드 블록은 원본 계획서 `docs/superpowers/plans/2026-04-13-tts-phase-1-forge-batch-engine.md`에 있습니다. 새 세션은 그 파일을 읽으면 됩니다.

## 상태 위치

### 계획 + 스펙 (synco 레포, 현재 브랜치: `feat/rbac-onboarding`)

```
/home/work/synco/docs/superpowers/
├── specs/2026-04-12-taste-to-ship-design.md      (v5 스펙, 참고용)
├── plans/2026-04-13-tts-phase-1-forge-batch-engine.md  (원본 계획, Task 11~15 내용 여기)
└── plans/2026-04-13-tts-phase-1-RESUME.md        (이 문서)
```

### 구현 산출물 (별도 로컬 git, `~/.claude/skills/_forge-batch-engine/`)

**Git chain (최신 → 최초):**
```
e5351f2 test(env-cleanup): add integration tests using real git/procs/ports
ca449af feat(env-cleanup): add skill-agnostic cleanup functions
8003391 feat(session-chain): add session_spawn for claude -p chaining
d75b2f5 feat(journal): add journal_append helper
74fae06 feat(watchdog): port watchdog.sh from plan-forge-batch
44600fe feat(sentinel): implement sentinel marker read/write
5d224ac test(sentinel): add failing tests for sentinel.py
e82af23 fix(progress): harden write() cleanup, _walk validation, _cli fallthrough
185daf1 feat(progress): implement forge-progress.json management
46a4100 test(progress): add failing tests for progress.py
1031884 chore: preemptively ignore .venv/ and *.egg-info/
49fc4a0 chore: initialize _forge-batch-engine library
```

**Directory state:**
```
~/.claude/skills/_forge-batch-engine/
├── .git/                               (로컬 git repo, 12개 커밋)
├── .gitignore                          (7 lines)
├── README.md                           (스텁, Task 13에서 완성 예정)
├── conftest.py                         (pytest bootstrap)
├── lib/
│   ├── progress.py                     (12 tests 통과, 코드 리뷰 픽스 반영)
│   ├── sentinel.py                     (13 tests 통과)
│   ├── watchdog.sh                     (실행 권한 있음)
│   ├── journal.sh
│   ├── session-chain.sh
│   └── env-cleanup.sh
├── tests/
│   ├── test_progress.py                (12 tests)
│   ├── test_sentinel.py                (13 tests)
│   ├── fixtures/
│   │   ├── sample-forge-progress.json
│   │   └── sample-agreed.md
│   └── integration/
│       ├── test_watchdog.sh            (실행 권한)
│       ├── test_journal.sh             (실행 권한)
│       ├── test_session_chain.sh       (실행 권한)
│       └── test_env_cleanup.sh         (실행 권한)
└── examples/                           (비어있음, Task 12에서 작성 예정)
```

## 최종 검증 스냅샷 (이 시점 기준)

```bash
$ cd ~/.claude/skills/_forge-batch-engine
$ uv run --with pytest pytest tests/ -q
25 passed in 0.41s

$ for t in tests/integration/test_*.sh; do bash "$t" > /tmp/itest-out 2>&1 && tail -1 /tmp/itest-out; done
All env-cleanup integration tests passed.
All journal integration tests passed.
All session-chain integration tests passed.
All watchdog integration tests passed.
```

## 새 세션에서 재개하는 방법

### 옵션 A: 그냥 아래 프롬프트를 새 세션에 붙여넣기 (권장)

다음 내용을 새 Claude Code 세션에 그대로 붙여넣으세요:

```
tts Phase 1 구현을 Task 11부터 이어서 진행한다.

컨텍스트:
- 원본 계획서: /home/work/synco/docs/superpowers/plans/2026-04-13-tts-phase-1-forge-batch-engine.md
- 재개 상태 문서: /home/work/synco/docs/superpowers/plans/2026-04-13-tts-phase-1-RESUME.md
- 구현 위치: ~/.claude/skills/_forge-batch-engine/ (별도 로컬 git)
- 완료된 태스크: 1~10 (12개 commit, 25 pytest passed, 4개 통합 테스트 모두 passed)
- 남은 태스크: 11(체크포인트) → 12(examples/minimal-usage.md) → 13(README API 레퍼런스) → 14(smoke e2e 테스트) → 15(최종 검증) → Final code review

실행 방식: superpowers:subagent-driven-development으로 Task 11부터 순차 진행.
각 태스크의 정확한 내용은 원본 계획서에서 "## Task 11:" 섹션부터 찾으면 된다.
RESUME 문서를 먼저 읽어서 현재 상태를 파악한 후, 원본 계획서의 Task 11~15를 읽고, TodoWrite로 남은 태스크 트래킹한 뒤 subagent-driven-development을 호출해라.
```

### 옵션 B: 수동 컨텍스트 복구

새 세션에서:

1. `docs/superpowers/plans/2026-04-13-tts-phase-1-RESUME.md` 읽기 (이 파일)
2. `docs/superpowers/plans/2026-04-13-tts-phase-1-forge-batch-engine.md` 에서 Task 11~15 섹션 읽기
3. `cd ~/.claude/skills/_forge-batch-engine && git log --oneline` 로 현 상태 확인
4. `uv run --with pytest pytest tests/` 로 25개 테스트 여전히 통과하는지 확인
5. TodoWrite로 Task 11~15 + Final review 트래킹 시작
6. `superpowers:subagent-driven-development` 스킬 호출 후 Task 11 implementer 디스패치

## 주의사항

1. **`~/.claude/skills/_forge-batch-engine/`는 synco와 별개의 git repo**입니다. 커밋은 그 안에서만 하고 synco의 브랜치와 무관합니다.
2. **`plan-forge-batch` 기존 스킬은 절대 건드리지 않습니다** — Phase 1의 원칙.
3. **테스트는 실제 환경 기반** (mock 최소화). 메모리의 "실전 동일 테스트" 원칙 준수 중.
4. Task 11은 단순 체크포인트(pytest + 4개 통합 테스트 재실행). 실패 없으면 그대로 통과시키고 Task 12로 진행.
5. Task 14의 smoke test는 `test_smoke_e2e.sh`라는 이름이며, mock claude를 PATH에 두고 session_spawn까지 전 라이브러리를 엮어 검증합니다.

## 이어서 해야 할 작업 순서 요약

1. 🏁 Task 11: checkpoint (별도 파일 생성 없음, 테스트만 재실행)
2. ✏️  Task 12: `~/.claude/skills/_forge-batch-engine/examples/minimal-usage.md` 작성
3. ✏️  Task 13: `~/.claude/skills/_forge-batch-engine/README.md` 를 완전한 API 레퍼런스로 교체
4. ✏️  Task 14: `~/.claude/skills/_forge-batch-engine/tests/integration/test_smoke_e2e.sh` 작성 + 실행
5. 🏁 Task 15: 최종 검증 (checkpoint)
6. 🔍 Final review: Phase 1 전체에 대해 `superpowers:code-reviewer` 디스패치

모든 새 커밋은 `~/.claude/skills/_forge-batch-engine/` 로컬 git repo에 들어갑니다. 이 RESUME 문서와 원본 계획서 외에는 synco 레포에 아무것도 추가되지 않습니다.
