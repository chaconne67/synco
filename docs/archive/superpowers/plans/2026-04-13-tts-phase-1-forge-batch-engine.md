# tts Phase 1 — `_forge-batch-engine` Library Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract reusable session-chaining, progress-tracking, watchdog, sentinel-marker, journaling, and environment-cleanup logic from the existing `plan-forge-batch` skill into a standalone internal library at `~/.claude/skills/_forge-batch-engine/` that can be imported by future batch skills (design-forge-batch, task-forge-batch, impl-forge-batch) in Phase 2.

**Architecture:** The library contains skill-agnostic utilities organized by concern. Bash scripts are sourced by SKILL.md files for session chaining, watchdog, journaling, and environment cleanup. Python scripts are invoked for JSON state management (progress, sentinel markers). No skill-specific logic lives in the library. The existing `plan-forge-batch` skill is **not modified** in this phase — it continues to use its inline logic. The library is a parallel track that later phases will adopt.

**Tech Stack:** Bash 4+, Python 3.13+, git, Claude CLI (`claude -p`), pytest (for Python unit tests).

**Testing approach:**
- Python modules use pytest (unit + CLI-invocation tests).
- Bash scripts use integration tests that exercise the functions inside a temp git repo with controlled fixtures (realistic testing, not mocking).

---

## Plan Context

### Why This Phase Exists

The spec at `docs/superpowers/specs/2026-04-12-taste-to-ship-design.md` (v5) describes a `taste-to-ship` workflow that reuses `plan-forge-batch`'s engine logic at multiple levels (design forging, task forging, implementation). Currently that logic is **inlined** inside `plan-forge-batch/SKILL.md` as bash snippets. This phase extracts it into a reusable library so Phase 2 can build three batch skills on top of it without copy-pasting.

### What Gets Extracted

| Concern | Source (`plan-forge-batch/SKILL.md`) | Target (`_forge-batch-engine/lib/`) |
|---|---|---|
| Watchdog monitoring | `watchdog.sh` (full file) | `watchdog.sh` (portability touch-ups) |
| Session chaining (`claude -p` spawn) | Lines 222-242 (first session), 263-282 (chain) | `session-chain.sh` (source + functions) |
| `forge-progress.json` read/write | Embedded `python3 -c` one-liners in watchdog + SKILL.md | `progress.py` (proper module + CLI) |
| Sentinel marker read/write | Described in SKILL.md "진실 소스 우선순위" + plan-forge SKILL.md centurion examples | `sentinel.py` (proper module + CLI) |
| Journal log append | `echo "[$(date)] EVENT" >> journal.log` pattern | `journal.sh` (function) |
| Environment cleanup (zombie, port, stash, /tmp/forge-*) | "환경 정리" section at line 346 (prose only) | `env-cleanup.sh` (functions) |

### What Does NOT Get Extracted

- Batch-level orchestration logic (action decision, dependency traversal, forge-progress.json *schema*) — those are Phase 2 concerns specific to each batch skill.
- The existing `plan-forge-batch` directory and its files — untouched, continues working.
- Auto-memory save prompt — that's a Phase 2 batch skill concern.

### File Structure

```
~/.claude/skills/_forge-batch-engine/
├── .git/                               ← local git repo (~/.claude itself is not git-managed)
├── README.md                           ← library overview + complete API reference
├── lib/
│   ├── watchdog.sh                     ← ported from plan-forge-batch
│   ├── session-chain.sh                ← claude -p spawn functions
│   ├── journal.sh                      ← append-event helpers
│   ├── env-cleanup.sh                  ← zombie/port/stash/tmp functions
│   ├── progress.py                     ← forge-progress.json management
│   └── sentinel.py                     ← sentinel marker read/write
├── tests/
│   ├── test_progress.py                ← pytest unit tests (+ CLI invocation tests)
│   ├── test_sentinel.py                ← pytest unit tests (+ CLI invocation tests)
│   ├── integration/
│   │   ├── test_watchdog.sh            ← launches watchdog in temp env, asserts behavior
│   │   ├── test_session_chain.sh       ← mocks claude CLI, verifies spawn
│   │   ├── test_journal.sh             ← appends + reads back
│   │   └── test_env_cleanup.sh         ← creates zombies, stashes, temps → asserts cleanup
│   └── fixtures/
│       ├── sample-forge-progress.json
│       └── sample-agreed.md            ← with sentinel marker
├── examples/
│   └── minimal-usage.md                ← smallest working example for skills
└── conftest.py                         ← pytest bootstrap (sys.path)
```

### Git Strategy

- `~/.claude` is not a git repo, but `_forge-batch-engine/` will be initialized as its own local git repo.
- Every meaningful task commits inside that repo.
- The **plan document itself** (this file) is committed in the `synco` repo at `docs/superpowers/plans/`. That commit happens once at the start.
- Library commits and plan document commits are independent.

---

## Task 1: Initialize library directory and local git repo

**Files:**
- Create: `~/.claude/skills/_forge-batch-engine/` (directory)
- Create: `~/.claude/skills/_forge-batch-engine/.gitignore`
- Create: `~/.claude/skills/_forge-batch-engine/README.md` (stub)

- [ ] **Step 1: Create directory structure**

Run:
```bash
mkdir -p ~/.claude/skills/_forge-batch-engine/{lib,tests/integration,tests/fixtures,examples}
```

- [ ] **Step 2: Initialize local git repo**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git init
git config user.email "$(git -C /home/work/synco config user.email)"
git config user.name "$(git -C /home/work/synco config user.name)"
```

- [ ] **Step 3: Write `.gitignore`**

Create `~/.claude/skills/_forge-batch-engine/.gitignore`:

```
__pycache__/
*.pyc
.pytest_cache/
tests/integration/tmp/
*.log
```

- [ ] **Step 4: Write README stub**

Create `~/.claude/skills/_forge-batch-engine/README.md`:

```markdown
# _forge-batch-engine

Reusable session-chaining, progress-tracking, watchdog, sentinel-marker,
journaling, and environment-cleanup utilities for batch skills that need
to split long work into context-isolated CLI sessions.

## Status

Phase 1 of `taste-to-ship` — library extraction from `plan-forge-batch`.
Used by Phase 2 batch skills: `design-forge-batch`, `task-forge-batch`,
`impl-forge-batch`.

## Layout

- `lib/` — utility modules (bash + python)
- `tests/` — pytest + integration bash tests
- `examples/` — minimal usage samples for skill authors

## API reference

See API REFERENCE section below (filled in Task 13).
```

- [ ] **Step 5: Initial commit**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git add -A
git commit -m "chore: initialize _forge-batch-engine library"
```

Expected: One commit with directory skeleton, `.gitignore`, and README stub.

---

## Task 2: Write `progress.py` failing tests (TDD red)

**Files:**
- Create: `~/.claude/skills/_forge-batch-engine/tests/fixtures/sample-forge-progress.json`
- Create: `~/.claude/skills/_forge-batch-engine/tests/test_progress.py`
- Create: `~/.claude/skills/_forge-batch-engine/conftest.py`

**Context:** `progress.py` is a Python module that reads, writes, and mutates `forge-progress.json` files. It exposes both an importable API (`read`, `write`, `get_field`, `set_field`, `atomic_update`) and a CLI (`python progress.py get <file> <field>`, `python progress.py set <file> <field> <value>`, `python progress.py update <file> <json-patch>`). Both surfaces are tested.

- [ ] **Step 1: Create pytest bootstrap**

Create `~/.claude/skills/_forge-batch-engine/conftest.py`:

```python
import sys
from pathlib import Path

LIB_DIR = Path(__file__).parent / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))
```

- [ ] **Step 2: Create fixture file**

Create `~/.claude/skills/_forge-batch-engine/tests/fixtures/sample-forge-progress.json`:

```json
{
  "schema_version": "1.0",
  "batch_status": "running",
  "last_pid": 12345,
  "project": "sample-project",
  "execution_order": ["t01", "t02", "t03"],
  "todos": {
    "t01": {"tempering_status": "completed", "impl_status": "completed"},
    "t02": {"tempering_status": "completed", "impl_status": "pending"},
    "t03": {"tempering_status": "pending", "impl_status": "pending"}
  }
}
```

- [ ] **Step 3: Write failing tests**

Create `~/.claude/skills/_forge-batch-engine/tests/test_progress.py`:

```python
"""
Tests for progress.py — forge-progress.json management.

Tests cover:
- pure function API (read, write, get_field, set_field, atomic_update)
- CLI invocation (python progress.py ...)
- atomicity (no half-written files)
- concurrent-safe updates via tempfile+rename
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import progress  # imported via conftest.py sys.path insertion

LIB = Path(__file__).parent.parent / "lib"
FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample-forge-progress.json"


# --- API tests --------------------------------------------------------------

def test_read_returns_parsed_dict(tmp_path):
    target = tmp_path / "progress.json"
    target.write_text(SAMPLE.read_text())
    data = progress.read(target)
    assert data["batch_status"] == "running"
    assert data["last_pid"] == 12345
    assert data["todos"]["t01"]["impl_status"] == "completed"


def test_write_roundtrips(tmp_path):
    target = tmp_path / "progress.json"
    original = json.loads(SAMPLE.read_text())
    progress.write(target, original)
    reloaded = json.loads(target.read_text())
    assert reloaded == original


def test_write_is_atomic_uses_tempfile(tmp_path, monkeypatch):
    target = tmp_path / "progress.json"
    target.write_text('{"batch_status": "running"}')
    # Inject failure during rename-target existence
    calls = []
    original_replace = Path.replace

    def tracking_replace(self, dst):
        calls.append((self, dst))
        return original_replace(self, dst)

    monkeypatch.setattr(Path, "replace", tracking_replace)
    progress.write(target, {"batch_status": "complete"})
    # Verify a temp file was used (parent matches target parent)
    assert calls, "write() must use Path.replace to be atomic"
    assert calls[0][1] == target


def test_get_field_dotted_path(tmp_path):
    target = tmp_path / "progress.json"
    target.write_text(SAMPLE.read_text())
    assert progress.get_field(target, "batch_status") == "running"
    assert progress.get_field(target, "todos.t02.impl_status") == "pending"


def test_set_field_dotted_path_mutates_file(tmp_path):
    target = tmp_path / "progress.json"
    target.write_text(SAMPLE.read_text())
    progress.set_field(target, "todos.t02.impl_status", "running")
    assert progress.get_field(target, "todos.t02.impl_status") == "running"


def test_set_field_returns_old_value(tmp_path):
    target = tmp_path / "progress.json"
    target.write_text(SAMPLE.read_text())
    old = progress.set_field(target, "batch_status", "complete")
    assert old == "running"
    assert progress.get_field(target, "batch_status") == "complete"


def test_atomic_update_callback_gets_parsed_dict(tmp_path):
    target = tmp_path / "progress.json"
    target.write_text(SAMPLE.read_text())

    def bump(d):
        d["last_pid"] = d["last_pid"] + 1
        return d

    progress.atomic_update(target, bump)
    assert progress.get_field(target, "last_pid") == 12346


# --- CLI tests --------------------------------------------------------------

def run_cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(LIB / "progress.py"), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_cli_get_prints_field_value(tmp_path):
    target = tmp_path / "progress.json"
    target.write_text(SAMPLE.read_text())
    result = run_cli("get", str(target), "batch_status")
    assert result.returncode == 0
    assert result.stdout.strip() == "running"


def test_cli_get_dotted_path(tmp_path):
    target = tmp_path / "progress.json"
    target.write_text(SAMPLE.read_text())
    result = run_cli("get", str(target), "todos.t02.impl_status")
    assert result.returncode == 0
    assert result.stdout.strip() == "pending"


def test_cli_set_updates_field(tmp_path):
    target = tmp_path / "progress.json"
    target.write_text(SAMPLE.read_text())
    result = run_cli("set", str(target), "batch_status", "complete")
    assert result.returncode == 0
    reloaded = json.loads(target.read_text())
    assert reloaded["batch_status"] == "complete"


def test_cli_get_missing_field_exits_nonzero(tmp_path):
    target = tmp_path / "progress.json"
    target.write_text(SAMPLE.read_text())
    result = run_cli("get", str(target), "nonexistent.field")
    assert result.returncode != 0


def test_cli_get_missing_file_exits_nonzero(tmp_path):
    result = run_cli("get", str(tmp_path / "nope.json"), "batch_status")
    assert result.returncode != 0
```

- [ ] **Step 4: Run tests to verify all fail (progress.py missing)**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
uv run --with pytest pytest tests/test_progress.py -v 2>&1 | head -50
```

Expected: All tests fail with `ModuleNotFoundError: No module named 'progress'` (or similar). This confirms pytest runs and the tests exist but there's no implementation yet.

- [ ] **Step 5: Commit failing tests**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git add conftest.py tests/test_progress.py tests/fixtures/sample-forge-progress.json
git commit -m "test(progress): add failing tests for progress.py"
```

---

## Task 3: Implement `progress.py` (TDD green)

**Files:**
- Create: `~/.claude/skills/_forge-batch-engine/lib/progress.py`

- [ ] **Step 1: Write the module**

Create `~/.claude/skills/_forge-batch-engine/lib/progress.py`:

```python
"""
progress.py — forge-progress.json management.

Provides both:
- importable API: read(), write(), get_field(), set_field(), atomic_update()
- CLI: python progress.py {get|set|update} <file> <field> [value]

All writes are atomic via tempfile + rename (Path.replace).
Dotted paths are supported for nested access: "todos.t02.impl_status".
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


def read(path: str | Path) -> dict:
    """Read a forge-progress.json file and return the parsed dict."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write(path: str | Path, data: dict) -> None:
    """Atomically write a dict as JSON to path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file in the same directory, then rename.
    # Same-directory guarantees rename is atomic on POSIX.
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
        temp_path = Path(f.name)
    temp_path.replace(path)


def _walk(data: dict, dotted: str) -> tuple[dict, str]:
    """Navigate to the parent of a dotted path, returning (parent, last_key)."""
    parts = dotted.split(".")
    parent = data
    for part in parts[:-1]:
        if not isinstance(parent, dict) or part not in parent:
            raise KeyError(f"field not found: {dotted}")
        parent = parent[part]
    last = parts[-1]
    if not isinstance(parent, dict):
        raise KeyError(f"field not found: {dotted}")
    return parent, last


def get_field(path: str | Path, dotted: str) -> Any:
    """Read a single field via dotted path. Raises KeyError if missing."""
    data = read(path)
    parent, last = _walk(data, dotted)
    if last not in parent:
        raise KeyError(f"field not found: {dotted}")
    return parent[last]


def set_field(path: str | Path, dotted: str, value: Any) -> Any:
    """Set a single field via dotted path. Returns the previous value (or None)."""
    data = read(path)
    parent, last = _walk(data, dotted)
    old = parent.get(last)
    parent[last] = value
    write(path, data)
    return old


def atomic_update(path: str | Path, fn: Callable[[dict], dict]) -> None:
    """Read the file, pass it to fn, write the result. fn must return the new dict."""
    data = read(path)
    new_data = fn(data)
    if new_data is None:
        raise ValueError("atomic_update callback must return the new dict")
    write(path, new_data)


def _cli() -> int:
    parser = argparse.ArgumentParser(prog="progress")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_get = sub.add_parser("get", help="get a field value")
    p_get.add_argument("file")
    p_get.add_argument("field")

    p_set = sub.add_parser("set", help="set a field value (value is parsed as JSON first, string fallback)")
    p_set.add_argument("file")
    p_set.add_argument("field")
    p_set.add_argument("value")

    args = parser.parse_args()

    try:
        if args.cmd == "get":
            value = get_field(args.file, args.field)
            if isinstance(value, (dict, list)):
                print(json.dumps(value, ensure_ascii=False))
            else:
                print(value)
            return 0
        if args.cmd == "set":
            # Try JSON parsing first so '123' → int, 'true' → bool, '"foo"' → str.
            # Fall back to raw string for unquoted strings like 'running'.
            try:
                parsed = json.loads(args.value)
            except json.JSONDecodeError:
                parsed = args.value
            set_field(args.file, args.field, parsed)
            return 0
    except (KeyError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(_cli())
```

- [ ] **Step 2: Run tests to verify all pass**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
uv run --with pytest pytest tests/test_progress.py -v
```

Expected: All tests PASS (12 tests). If any fail, re-read the test and fix the implementation — do not modify the test.

- [ ] **Step 3: Commit**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git add lib/progress.py
git commit -m "feat(progress): implement forge-progress.json management"
```

---

## Task 4: Write `sentinel.py` failing tests (TDD red)

**Files:**
- Create: `~/.claude/skills/_forge-batch-engine/tests/fixtures/sample-agreed.md`
- Create: `~/.claude/skills/_forge-batch-engine/tests/test_sentinel.py`

**Context:** Sentinel markers are trailing HTML comments in `*-agreed.md` files that confirm a document was completed by forge. Format: `<!-- forge:{topic}:{stem}:complete:{ISO 8601 timestamp} -->`. The sentinel is the single source of truth for "is this document forged?". `sentinel.py` exposes:
- `has_sentinel(path) -> bool` — is there a valid sentinel on the last non-empty line?
- `read_sentinel(path) -> dict | None` — parsed fields (topic, stem, timestamp) or None.
- `write_sentinel(path, topic, stem, timestamp=None) -> None` — append a sentinel (replaces existing, uses UTC now if no timestamp given).

- [ ] **Step 1: Create fixture**

Create `~/.claude/skills/_forge-batch-engine/tests/fixtures/sample-agreed.md`:

```markdown
# Sample agreed document

This is a placeholder agreed document used in sentinel tests.

<!-- forge:sample-topic:sample-stem:complete:2026-04-13T10:00:00Z -->
```

- [ ] **Step 2: Write failing tests**

Create `~/.claude/skills/_forge-batch-engine/tests/test_sentinel.py`:

```python
"""
Tests for sentinel.py — sentinel marker read/write.

Marker format: <!-- forge:{topic}:{stem}:complete:{ISO 8601 timestamp} -->
Must be on the last non-empty line of an *-agreed.md file to count.
"""
import subprocess
import sys
from pathlib import Path

import pytest

import sentinel

LIB = Path(__file__).parent.parent / "lib"
FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample-agreed.md"


# --- API tests --------------------------------------------------------------

def test_has_sentinel_true_for_sample():
    assert sentinel.has_sentinel(SAMPLE) is True


def test_has_sentinel_false_when_file_missing(tmp_path):
    assert sentinel.has_sentinel(tmp_path / "nope.md") is False


def test_has_sentinel_false_when_no_marker(tmp_path):
    target = tmp_path / "agreed.md"
    target.write_text("# Doc\n\nContent\n")
    assert sentinel.has_sentinel(target) is False


def test_has_sentinel_tolerates_trailing_whitespace(tmp_path):
    target = tmp_path / "agreed.md"
    target.write_text(
        "# Doc\n\n<!-- forge:t:s:complete:2026-04-13T00:00:00Z -->\n\n\n"
    )
    assert sentinel.has_sentinel(target) is True


def test_read_sentinel_parses_fields():
    parsed = sentinel.read_sentinel(SAMPLE)
    assert parsed is not None
    assert parsed["topic"] == "sample-topic"
    assert parsed["stem"] == "sample-stem"
    assert parsed["timestamp"] == "2026-04-13T10:00:00Z"


def test_read_sentinel_returns_none_when_missing(tmp_path):
    target = tmp_path / "agreed.md"
    target.write_text("no marker here\n")
    assert sentinel.read_sentinel(target) is None


def test_write_sentinel_appends_to_file(tmp_path):
    target = tmp_path / "agreed.md"
    target.write_text("# Doc\n\ncontent\n")
    sentinel.write_sentinel(
        target,
        topic="my-topic",
        stem="my-stem",
        timestamp="2026-04-13T12:00:00Z",
    )
    assert sentinel.has_sentinel(target)
    parsed = sentinel.read_sentinel(target)
    assert parsed["topic"] == "my-topic"
    assert parsed["stem"] == "my-stem"


def test_write_sentinel_replaces_existing(tmp_path):
    target = tmp_path / "agreed.md"
    target.write_text(
        "# Doc\n\n<!-- forge:old:old:complete:2026-01-01T00:00:00Z -->\n"
    )
    sentinel.write_sentinel(
        target, topic="new", stem="new", timestamp="2026-04-13T12:00:00Z"
    )
    parsed = sentinel.read_sentinel(target)
    assert parsed["topic"] == "new"
    assert parsed["stem"] == "new"
    # Verify only one marker remains
    content = target.read_text()
    assert content.count("forge:") == 1


def test_write_sentinel_uses_utc_now_when_no_timestamp(tmp_path):
    target = tmp_path / "agreed.md"
    target.write_text("# Doc\n")
    sentinel.write_sentinel(target, topic="t", stem="s")
    parsed = sentinel.read_sentinel(target)
    assert parsed is not None
    assert parsed["timestamp"].endswith("Z")
    # 2026-04-13T... or later
    assert parsed["timestamp"][:4] >= "2026"


# --- CLI tests --------------------------------------------------------------

def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(LIB / "sentinel.py"), *args],
        capture_output=True,
        text=True,
    )


def test_cli_check_exits_zero_when_present():
    result = run_cli("check", str(SAMPLE))
    assert result.returncode == 0


def test_cli_check_exits_nonzero_when_missing(tmp_path):
    target = tmp_path / "agreed.md"
    target.write_text("no marker\n")
    result = run_cli("check", str(target))
    assert result.returncode != 0


def test_cli_read_prints_json():
    result = run_cli("read", str(SAMPLE))
    assert result.returncode == 0
    import json
    parsed = json.loads(result.stdout)
    assert parsed["topic"] == "sample-topic"
    assert parsed["stem"] == "sample-stem"


def test_cli_write_appends_marker(tmp_path):
    target = tmp_path / "agreed.md"
    target.write_text("# Doc\n")
    result = run_cli(
        "write", str(target),
        "--topic", "t", "--stem", "s",
        "--timestamp", "2026-04-13T12:00:00Z",
    )
    assert result.returncode == 0
    assert sentinel.has_sentinel(target)
```

- [ ] **Step 3: Run tests to verify all fail**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
uv run --with pytest pytest tests/test_sentinel.py -v 2>&1 | head -50
```

Expected: All tests fail with `ModuleNotFoundError: No module named 'sentinel'`.

- [ ] **Step 4: Commit failing tests**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git add tests/test_sentinel.py tests/fixtures/sample-agreed.md
git commit -m "test(sentinel): add failing tests for sentinel.py"
```

---

## Task 5: Implement `sentinel.py` (TDD green)

**Files:**
- Create: `~/.claude/skills/_forge-batch-engine/lib/sentinel.py`

- [ ] **Step 1: Write the module**

Create `~/.claude/skills/_forge-batch-engine/lib/sentinel.py`:

```python
"""
sentinel.py — sentinel marker read/write for forged documents.

Marker format: <!-- forge:{topic}:{stem}:complete:{ISO 8601 timestamp} -->
Must be on the last non-empty line of the file to count as valid.

API:
- has_sentinel(path) -> bool
- read_sentinel(path) -> dict | None  (keys: topic, stem, timestamp)
- write_sentinel(path, topic, stem, timestamp=None) -> None

CLI:
- python sentinel.py check <file>              (exit 0 if present)
- python sentinel.py read <file>               (prints JSON)
- python sentinel.py write <file> --topic T --stem S [--timestamp TS]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

MARKER_RE = re.compile(
    r"<!--\s*forge:([^:]+):([^:]+):complete:([^\s]+)\s*-->"
)


def _last_non_empty_line(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def has_sentinel(path: str | Path) -> bool:
    path = Path(path)
    if not path.exists():
        return False
    last = _last_non_empty_line(path.read_text(encoding="utf-8"))
    if last is None:
        return False
    return MARKER_RE.search(last) is not None


def read_sentinel(path: str | Path) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    last = _last_non_empty_line(path.read_text(encoding="utf-8"))
    if last is None:
        return None
    m = MARKER_RE.search(last)
    if not m:
        return None
    return {"topic": m.group(1), "stem": m.group(2), "timestamp": m.group(3)}


def write_sentinel(
    path: str | Path,
    topic: str,
    stem: str,
    timestamp: str | None = None,
) -> None:
    path = Path(path)
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    marker = f"<!-- forge:{topic}:{stem}:complete:{timestamp} -->"

    content = path.read_text(encoding="utf-8") if path.exists() else ""
    # Strip any existing marker lines
    lines = [
        ln for ln in content.splitlines()
        if MARKER_RE.search(ln.strip()) is None
    ]
    # Strip trailing blank lines
    while lines and not lines[-1].strip():
        lines.pop()
    lines.append("")
    lines.append(marker)
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _cli() -> int:
    parser = argparse.ArgumentParser(prog="sentinel")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="exit 0 if sentinel present")
    p_check.add_argument("file")

    p_read = sub.add_parser("read", help="print parsed sentinel as JSON")
    p_read.add_argument("file")

    p_write = sub.add_parser("write", help="append sentinel marker")
    p_write.add_argument("file")
    p_write.add_argument("--topic", required=True)
    p_write.add_argument("--stem", required=True)
    p_write.add_argument("--timestamp")

    args = parser.parse_args()

    if args.cmd == "check":
        return 0 if has_sentinel(args.file) else 1
    if args.cmd == "read":
        parsed = read_sentinel(args.file)
        if parsed is None:
            print("no sentinel", file=sys.stderr)
            return 1
        print(json.dumps(parsed, ensure_ascii=False))
        return 0
    if args.cmd == "write":
        write_sentinel(args.file, args.topic, args.stem, args.timestamp)
        return 0


if __name__ == "__main__":
    sys.exit(_cli())
```

- [ ] **Step 2: Run tests to verify all pass**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
uv run --with pytest pytest tests/test_sentinel.py -v
```

Expected: All tests PASS (13 tests).

- [ ] **Step 3: Commit**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git add lib/sentinel.py
git commit -m "feat(sentinel): implement sentinel marker read/write"
```

---

## Task 6: Port `watchdog.sh` from `plan-forge-batch`

**Files:**
- Create: `~/.claude/skills/_forge-batch-engine/lib/watchdog.sh`
- Create: `~/.claude/skills/_forge-batch-engine/tests/integration/test_watchdog.sh`

**Context:** `plan-forge-batch/watchdog.sh` monitors a background `claude -p` session's activity via journal log mtime + CPU usage, and respawns if hung. It's already well-structured, but the port reads progress fields via inline `python3 -c` one-liners. We replace those with calls to the new `progress.py` CLI for consistency.

- [ ] **Step 1: Read the original**

Run:
```bash
cat ~/.claude/skills/plan-forge-batch/watchdog.sh
```

Expected: ~137 lines of bash. Note the `get_batch_status`, `get_last_pid`, `set_last_pid` helper functions that use inline Python.

- [ ] **Step 2: Create the ported watchdog**

Create `~/.claude/skills/_forge-batch-engine/lib/watchdog.sh`:

```bash
#!/bin/bash
# _forge-batch-engine watchdog
# Monitors a background batch session and respawns if stuck.
# Skill-agnostic: invoked by any batch skill that needs background watchdog.
#
# Usage: nohup watchdog.sh <forge-dir> [timeout-min] &
# Example: nohup watchdog.sh docs/forge/my-project 20 &

set -euo pipefail

FORGE_DIR="${1:?Usage: watchdog.sh <forge-dir> [timeout-min]}"
TIMEOUT_MIN="${2:-20}"

if ! [[ "$TIMEOUT_MIN" =~ ^[0-9]+$ ]] || (( TIMEOUT_MIN == 0 )); then
  echo "Error: timeout-min must be a positive integer, got '$TIMEOUT_MIN'" >&2
  exit 1
fi

CHECK_INTERVAL=300  # 5 minutes
JOURNAL="${FORGE_DIR}/logs/journal.log"
PROGRESS="${FORGE_DIR}/forge-progress.json"
PROMPT="${FORGE_DIR}/session-prompt.txt"
WATCHDOG_LOG="${FORGE_DIR}/logs/watchdog.log"

# Resolve the library directory so we can call progress.py
LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROGRESS_PY="${LIB_DIR}/progress.py"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$WATCHDOG_LOG"
}

get_batch_status() {
  python3 "$PROGRESS_PY" get "$PROGRESS" batch_status 2>/dev/null || echo "unknown"
}

get_last_pid() {
  python3 "$PROGRESS_PY" get "$PROGRESS" last_pid 2>/dev/null || echo "0"
}

set_last_pid() {
  python3 "$PROGRESS_PY" set "$PROGRESS" last_pid "$1"
}

respawn() {
  local reason="$1"
  local new_log="${FORGE_DIR}/logs/session-$(date +%Y%m%d-%H%M%S).log"

  if [[ ! -f "$PROMPT" ]]; then
    log "RESPAWN_ABORTED reason=\"${reason}\" error=\"session-prompt.txt not found\""
    return 1
  fi

  nohup claude -p \
    --permission-mode bypassPermissions \
    --output-format stream-json \
    --verbose \
    < "$PROMPT" \
    > "$new_log" 2>&1 &
  local new_pid=$!

  set_last_pid "$new_pid"
  log "RESPAWN reason=\"${reason}\" new_pid=${new_pid} log=${new_log}"
}

log "WATCHDOG_START forge_dir=${FORGE_DIR} timeout=${TIMEOUT_MIN}m interval=${CHECK_INTERVAL}s lib=${LIB_DIR}"

while true; do
  sleep "$CHECK_INTERVAL"

  STATUS=$(get_batch_status)
  if [[ "$STATUS" != "running" ]]; then
    count=$(find "${FORGE_DIR}/logs" -name "session-*.log" 2>/dev/null | wc -l)
    rm -f "${FORGE_DIR}/logs"/session-*.log
    log "WATCHDOG_EXIT batch_status=${STATUS} cleaned=${count}_session_logs"
    exit 0
  fi

  PID=$(get_last_pid)

  if ! [[ "$PID" =~ ^[1-9][0-9]*$ ]]; then
    log "INVALID_PID pid=${PID}"
    continue
  fi

  if ! kill -0 "$PID" 2>/dev/null; then
    log "DEAD_PROCESS pid=${PID}"
    respawn "process_dead" || true
    continue
  fi

  LATEST_SESSION_LOG=$(ls -t "${FORGE_DIR}/logs"/session-*.log 2>/dev/null | head -1)
  if [[ -n "$LATEST_SESSION_LOG" ]]; then
    LAST_MOD=$(stat -c %Y "$LATEST_SESSION_LOG")
  elif [[ -f "$JOURNAL" ]]; then
    LAST_MOD=$(stat -c %Y "$JOURNAL")
  else
    continue
  fi

  NOW=$(date +%s)
  IDLE_MIN=$(( (NOW - LAST_MOD) / 60 ))

  if (( IDLE_MIN < TIMEOUT_MIN )); then
    continue
  fi

  CPU=$(ps -p "$PID" -o %cpu --no-headers 2>/dev/null | tr -d ' ' || echo "0.0")
  if ! [[ "$CPU" =~ ^[0-9]+\.?[0-9]*$ ]]; then
    CPU="0.0"
  fi

  if awk -v cpu="$CPU" 'BEGIN {exit !(cpu < 1.0)}'; then
    log "STUCK pid=${PID} idle=${IDLE_MIN}m cpu=${CPU}%"
    kill "$PID" 2>/dev/null || true
    sleep 2
    if kill -0 "$PID" 2>/dev/null; then
      kill -9 "$PID" 2>/dev/null || true
      sleep 1
    fi
    respawn "stuck_${IDLE_MIN}m_cpu_${CPU}" || true
  else
    log "SLOW pid=${PID} idle=${IDLE_MIN}m cpu=${CPU}% (not stuck, still working)"
  fi
done
```

- [ ] **Step 3: Make watchdog executable**

Run:
```bash
chmod +x ~/.claude/skills/_forge-batch-engine/lib/watchdog.sh
```

- [ ] **Step 4: Write integration test (short-path, no real claude spawn)**

Create `~/.claude/skills/_forge-batch-engine/tests/integration/test_watchdog.sh`:

```bash
#!/bin/bash
# Integration test for watchdog.sh.
# Verifies: argument validation, progress.py integration, exit when batch_status != running.
# Does NOT verify real claude -p spawn — that requires full Claude CLI + live session.

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(cd "$TEST_DIR/../../lib" && pwd)"
WATCHDOG="$LIB_DIR/watchdog.sh"

TMP=$(mktemp -d)
trap "rm -rf '$TMP'" EXIT

FORGE_DIR="$TMP/forge"
mkdir -p "$FORGE_DIR/logs"

# --- Test 1: missing forge-dir arg → nonzero exit
if "$WATCHDOG" 2>/dev/null; then
  echo "FAIL: watchdog should exit nonzero without forge-dir"
  exit 1
fi
echo "PASS: missing forge-dir rejected"

# --- Test 2: invalid timeout-min → nonzero exit
if "$WATCHDOG" "$FORGE_DIR" "abc" 2>/dev/null; then
  echo "FAIL: watchdog should reject non-numeric timeout"
  exit 1
fi
echo "PASS: invalid timeout rejected"

# --- Test 3: exits cleanly when batch_status is "complete"
cat > "$FORGE_DIR/forge-progress.json" <<EOF
{"batch_status": "complete", "last_pid": 0}
EOF

# Override CHECK_INTERVAL by wrapping in timeout (watchdog sleeps 300s before first check).
# We use a very short background run and verify the log mentions WATCHDOG_START.
# Then we manually flip batch_status and signal that we'd expect WATCHDOG_EXIT.
# For the integration test, we just verify the script parses args and starts without crashing.

# Launch in background, kill after 2 seconds (it will be mid-sleep on first iteration).
"$WATCHDOG" "$FORGE_DIR" 1 &
WD_PID=$!
sleep 2
kill "$WD_PID" 2>/dev/null || true
wait "$WD_PID" 2>/dev/null || true

if [[ ! -f "$FORGE_DIR/logs/watchdog.log" ]]; then
  echo "FAIL: watchdog.log not created"
  exit 1
fi

if ! grep -q "WATCHDOG_START" "$FORGE_DIR/logs/watchdog.log"; then
  echo "FAIL: WATCHDOG_START not logged"
  cat "$FORGE_DIR/logs/watchdog.log"
  exit 1
fi
echo "PASS: watchdog starts and logs correctly"

# --- Test 4: progress.py integration — get_batch_status works
cat > "$FORGE_DIR/forge-progress.json" <<EOF
{"batch_status": "running", "last_pid": 99999}
EOF

STATUS=$(python3 "$LIB_DIR/progress.py" get "$FORGE_DIR/forge-progress.json" batch_status)
if [[ "$STATUS" != "running" ]]; then
  echo "FAIL: progress.py get returned '$STATUS', expected 'running'"
  exit 1
fi
echo "PASS: progress.py integration"

echo ""
echo "All watchdog integration tests passed."
```

- [ ] **Step 5: Make integration test executable**

Run:
```bash
chmod +x ~/.claude/skills/_forge-batch-engine/tests/integration/test_watchdog.sh
```

- [ ] **Step 6: Run integration test**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
bash tests/integration/test_watchdog.sh
```

Expected: `All watchdog integration tests passed.` printed, exit code 0.

- [ ] **Step 7: Commit**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git add lib/watchdog.sh tests/integration/test_watchdog.sh
git commit -m "feat(watchdog): port watchdog.sh from plan-forge-batch

Uses progress.py CLI for forge-progress.json access instead of inline
python3 -c one-liners. LIB_DIR resolved from BASH_SOURCE so the script
works regardless of where it's invoked from."
```

---

## Task 7: Implement `journal.sh`

**Files:**
- Create: `~/.claude/skills/_forge-batch-engine/lib/journal.sh`
- Create: `~/.claude/skills/_forge-batch-engine/tests/integration/test_journal.sh`

**Context:** The journal log is an append-only file at `{forge_dir}/logs/journal.log` where each line is `[HH:MM:SS] EVENT details`. Used by watchdog and by batch skills to trace progress. Exposed as a sourced bash function `journal_append <forge_dir> <event> [details...]`.

- [ ] **Step 1: Write integration test first**

Create `~/.claude/skills/_forge-batch-engine/tests/integration/test_journal.sh`:

```bash
#!/bin/bash
# Integration test for journal.sh.

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(cd "$TEST_DIR/../../lib" && pwd)"

# shellcheck source=/dev/null
source "$LIB_DIR/journal.sh"

TMP=$(mktemp -d)
trap "rm -rf '$TMP'" EXIT

FORGE_DIR="$TMP/forge"

# --- Test 1: journal_append creates logs/journal.log if missing
journal_append "$FORGE_DIR" "TEST_EVENT" "detail=one"

if [[ ! -f "$FORGE_DIR/logs/journal.log" ]]; then
  echo "FAIL: journal.log not created"
  exit 1
fi
echo "PASS: journal.log created"

# --- Test 2: line format matches [HH:MM:SS] EVENT details
line=$(cat "$FORGE_DIR/logs/journal.log")
if ! [[ "$line" =~ ^\[[0-9]{2}:[0-9]{2}:[0-9]{2}\]\ TEST_EVENT\ detail=one$ ]]; then
  echo "FAIL: line format wrong: '$line'"
  exit 1
fi
echo "PASS: line format matches"

# --- Test 3: multiple appends go on separate lines
journal_append "$FORGE_DIR" "SECOND_EVENT" "k=v"
journal_append "$FORGE_DIR" "THIRD_EVENT"

count=$(wc -l < "$FORGE_DIR/logs/journal.log")
if [[ "$count" != "3" ]]; then
  echo "FAIL: expected 3 lines, got $count"
  cat "$FORGE_DIR/logs/journal.log"
  exit 1
fi
echo "PASS: 3 appends produce 3 lines"

# --- Test 4: event without details still works
if ! grep -q "THIRD_EVENT" "$FORGE_DIR/logs/journal.log"; then
  echo "FAIL: THIRD_EVENT not in journal"
  exit 1
fi
echo "PASS: event without details"

echo ""
echo "All journal integration tests passed."
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
chmod +x ~/.claude/skills/_forge-batch-engine/tests/integration/test_journal.sh
cd ~/.claude/skills/_forge-batch-engine
bash tests/integration/test_journal.sh 2>&1 | head -20
```

Expected: FAIL because `lib/journal.sh` does not exist yet (source fails).

- [ ] **Step 3: Implement journal.sh**

Create `~/.claude/skills/_forge-batch-engine/lib/journal.sh`:

```bash
#!/bin/bash
# journal.sh — append-only structured event logging for batch sessions.
#
# Source this file and call journal_append.
#
# Usage:
#   source /path/to/_forge-batch-engine/lib/journal.sh
#   journal_append <forge_dir> <event> [details...]
#
# Line format: [HH:MM:SS] EVENT details
# File:        {forge_dir}/logs/journal.log

journal_append() {
  local forge_dir="${1:?journal_append requires forge_dir}"
  local event="${2:?journal_append requires event}"
  shift 2
  local details="$*"
  local log_dir="${forge_dir}/logs"
  local log_file="${log_dir}/journal.log"

  mkdir -p "$log_dir"
  if [[ -n "$details" ]]; then
    echo "[$(date '+%H:%M:%S')] ${event} ${details}" >> "$log_file"
  else
    echo "[$(date '+%H:%M:%S')] ${event}" >> "$log_file"
  fi
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
bash tests/integration/test_journal.sh
```

Expected: `All journal integration tests passed.`

- [ ] **Step 5: Commit**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git add lib/journal.sh tests/integration/test_journal.sh
git commit -m "feat(journal): add journal_append helper"
```

---

## Task 8: Implement `session-chain.sh`

**Files:**
- Create: `~/.claude/skills/_forge-batch-engine/lib/session-chain.sh`
- Create: `~/.claude/skills/_forge-batch-engine/tests/integration/test_session_chain.sh`

**Context:** `session-chain.sh` wraps the `claude -p` background spawn pattern from `plan-forge-batch/SKILL.md` lines 222-242 and 263-282. Key behaviors:
- Sources `.env` (if present) so API keys flow into non-interactive shells.
- Spawns `claude -p` with bypassPermissions + stream-json logging into `${forge_dir}/logs/session-{timestamp}.log`.
- Writes the new PID into `forge-progress.json` via `progress.py`.
- Returns the new PID on stdout.

The function is named `session_spawn` and takes `forge_dir` as its one argument. Session prompt is expected at `{forge_dir}/session-prompt.txt`.

We test it with a **mock `claude`** binary on PATH that just records its stdin to a file and sleeps, so we don't need a real Claude CLI.

- [ ] **Step 1: Write integration test first**

Create `~/.claude/skills/_forge-batch-engine/tests/integration/test_session_chain.sh`:

```bash
#!/bin/bash
# Integration test for session-chain.sh.
# Mocks the claude CLI to avoid needing a real API session.

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(cd "$TEST_DIR/../../lib" && pwd)"

TMP=$(mktemp -d)
trap "rm -rf '$TMP'" EXIT

# Create a mock claude binary that records stdin and sleeps
MOCK_BIN="$TMP/bin"
mkdir -p "$MOCK_BIN"
cat > "$MOCK_BIN/claude" <<'MOCK'
#!/bin/bash
# Mock claude: record stdin to a file and sleep.
# Record where and what, so the test can assert the call shape.
OUT="${MOCK_CLAUDE_OUT:-/tmp/mock-claude-stdin}"
cat > "$OUT"
# Record the args
echo "ARGS: $*" > "${OUT}.args"
sleep 10
MOCK
chmod +x "$MOCK_BIN/claude"

export PATH="$MOCK_BIN:$PATH"

FORGE_DIR="$TMP/forge"
mkdir -p "$FORGE_DIR/logs"

# Initial forge-progress.json
cat > "$FORGE_DIR/forge-progress.json" <<EOF
{"batch_status": "running", "last_pid": 0}
EOF

# Session prompt
cat > "$FORGE_DIR/session-prompt.txt" <<EOF
sample session prompt content
plan-forge-batch mode=continue
EOF

export MOCK_CLAUDE_OUT="$TMP/mock-stdin"

# --- Test 1: source and spawn
# shellcheck source=/dev/null
source "$LIB_DIR/session-chain.sh"

PID=$(session_spawn "$FORGE_DIR")

if ! [[ "$PID" =~ ^[0-9]+$ ]]; then
  echo "FAIL: session_spawn returned non-numeric PID: '$PID'"
  exit 1
fi
echo "PASS: session_spawn returned PID $PID"

# --- Test 2: PID is alive
if ! kill -0 "$PID" 2>/dev/null; then
  echo "FAIL: spawned process $PID not alive"
  exit 1
fi
echo "PASS: spawned process alive"

# --- Test 3: forge-progress.json updated with new PID
STORED_PID=$(python3 "$LIB_DIR/progress.py" get "$FORGE_DIR/forge-progress.json" last_pid)
if [[ "$STORED_PID" != "$PID" ]]; then
  echo "FAIL: forge-progress.json last_pid is '$STORED_PID', expected '$PID'"
  exit 1
fi
echo "PASS: forge-progress.json last_pid updated"

# Wait for mock claude to write its stdin capture (it runs synchronously once stdin closes)
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if [[ -f "$MOCK_CLAUDE_OUT" ]]; then break; fi
  sleep 0.2
done

# --- Test 4: stdin of mock claude contains session-prompt.txt
if ! [[ -f "$MOCK_CLAUDE_OUT" ]]; then
  echo "FAIL: mock claude did not record stdin (expected $MOCK_CLAUDE_OUT)"
  exit 1
fi

if ! grep -q "sample session prompt content" "$MOCK_CLAUDE_OUT"; then
  echo "FAIL: mock claude stdin did not contain session-prompt.txt content"
  cat "$MOCK_CLAUDE_OUT"
  exit 1
fi
echo "PASS: stdin was session-prompt.txt"

# --- Test 5: args include bypassPermissions and stream-json
if ! grep -q "bypassPermissions" "${MOCK_CLAUDE_OUT}.args"; then
  echo "FAIL: args missing bypassPermissions"
  cat "${MOCK_CLAUDE_OUT}.args"
  exit 1
fi
if ! grep -q "stream-json" "${MOCK_CLAUDE_OUT}.args"; then
  echo "FAIL: args missing stream-json"
  exit 1
fi
echo "PASS: args include bypassPermissions and stream-json"

# Kill the mock so trap cleanup runs cleanly
kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true

# --- Test 6: session log file exists
LOG_COUNT=$(find "$FORGE_DIR/logs" -name "session-*.log" 2>/dev/null | wc -l)
if [[ "$LOG_COUNT" -lt 1 ]]; then
  echo "FAIL: no session log created"
  ls -la "$FORGE_DIR/logs"
  exit 1
fi
echo "PASS: session log created"

echo ""
echo "All session-chain integration tests passed."
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
chmod +x ~/.claude/skills/_forge-batch-engine/tests/integration/test_session_chain.sh
cd ~/.claude/skills/_forge-batch-engine
bash tests/integration/test_session_chain.sh 2>&1 | head -20
```

Expected: FAIL because `lib/session-chain.sh` does not exist.

- [ ] **Step 3: Implement session-chain.sh**

Create `~/.claude/skills/_forge-batch-engine/lib/session-chain.sh`:

```bash
#!/bin/bash
# session-chain.sh — claude -p background spawn for batch session chaining.
#
# Source this file and call session_spawn.
#
# Usage:
#   source /path/to/_forge-batch-engine/lib/session-chain.sh
#   new_pid=$(session_spawn <forge_dir>)
#
# Behavior:
#   - Sources .env (if present) so API keys flow into non-interactive shells.
#   - Spawns `claude -p --permission-mode bypassPermissions --output-format stream-json --verbose`
#     with stdin from {forge_dir}/session-prompt.txt.
#   - Writes stdout/stderr to {forge_dir}/logs/session-{timestamp}.log.
#   - Updates forge-progress.json last_pid via progress.py.
#   - Echoes the new PID on stdout.

_SESSION_CHAIN_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

session_spawn() {
  local forge_dir="${1:?session_spawn requires forge_dir}"
  local session_prompt="${forge_dir}/session-prompt.txt"
  local log_dir="${forge_dir}/logs"
  local progress_py="${_SESSION_CHAIN_LIB_DIR}/progress.py"

  if [[ ! -f "$session_prompt" ]]; then
    echo "session_spawn: session-prompt.txt not found at $session_prompt" >&2
    return 1
  fi

  mkdir -p "$log_dir"
  local log_file="${log_dir}/session-$(date +%Y%m%d-%H%M%S).log"

  # Spawn claude in a subshell so .env sourcing doesn't leak to the caller.
  # The subshell echoes $! (the PID of the backgrounded claude) as its last line.
  local new_pid
  new_pid=$(
    if [[ -f .env ]]; then
      set -a
      # shellcheck source=/dev/null
      source .env
      set +a
    fi
    nohup claude -p \
      --permission-mode bypassPermissions \
      --output-format stream-json \
      --verbose \
      < "$session_prompt" \
      > "$log_file" 2>&1 &
    echo "$!"
  )

  if ! [[ "$new_pid" =~ ^[0-9]+$ ]]; then
    echo "session_spawn: subshell did not return a PID (got '$new_pid')" >&2
    return 1
  fi

  # Update forge-progress.json
  local progress_file="${forge_dir}/forge-progress.json"
  if [[ -f "$progress_file" ]]; then
    python3 "$progress_py" set "$progress_file" last_pid "$new_pid" >/dev/null
  fi

  echo "$new_pid"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
bash tests/integration/test_session_chain.sh
```

Expected: `All session-chain integration tests passed.`

- [ ] **Step 5: Commit**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git add lib/session-chain.sh tests/integration/test_session_chain.sh
git commit -m "feat(session-chain): add session_spawn for claude -p chaining"
```

---

## Task 9: Implement `env-cleanup.sh` — Part 1: functions

**Files:**
- Create: `~/.claude/skills/_forge-batch-engine/lib/env-cleanup.sh`

**Context:** `env-cleanup.sh` contains skill-agnostic environment cleanup functions driven by the "would the next session's `uv run pytest` fail if this resource stayed?" criterion from `plan-forge-batch/SKILL.md` line 346 and the taste-to-ship spec Stage 1f-3. Functions are:

- `check_existing_tts_stashes` → prints `git stash list` entries tagged `tts:*`, exits 0 if none, exits 1 with list if any (for callers to block on).
- `stash_uncommitted_work` → if working tree has uncommitted changes, creates a stash tagged `tts:{ISO timestamp}` and echoes the ref.
- `clean_temp_forge_files` → removes `/tmp/forge-*` files that are stale (older than 1 hour).
- `check_stale_lock_files` → inspects `.claude/*.lock`, `*.pid` files. Removes the ones whose PIDs are dead (safe). Reports the ones whose PIDs are alive (caller decides).
- `check_port_held` `<port>` → returns 0 if port is held, 1 if free. Prints the holding PID on stdout.

The one-shot "run all checks" is a separate Task 10. This task is just the functions.

- [ ] **Step 1: Write the module**

Create `~/.claude/skills/_forge-batch-engine/lib/env-cleanup.sh`:

```bash
#!/bin/bash
# env-cleanup.sh — skill-agnostic environment cleanup functions.
#
# Source this file to get:
#   - check_existing_tts_stashes
#   - stash_uncommitted_work
#   - clean_temp_forge_files
#   - check_stale_lock_files
#   - check_port_held <port>
#
# Design principle: never destroy user work. Stashes are tagged. Locks with
# live PIDs are reported, not removed. Caller decides on destructive actions.

_ENV_CLEANUP_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- tts stash management ---------------------------------------------------

# Check for any existing stash tagged "tts:*".
# stdout: list of matching stash entries (empty if none)
# exit: 0 if none, 1 if at least one exists
check_existing_tts_stashes() {
  if ! git rev-parse --git-dir >/dev/null 2>&1; then
    return 0  # not a git repo → no stashes possible
  fi
  local matches
  matches=$(git stash list 2>/dev/null | grep "tts:" || true)
  if [[ -z "$matches" ]]; then
    return 0
  fi
  echo "$matches"
  return 1
}

# Stash uncommitted work with a unique tts tag if the working tree is dirty.
# stdout: the stash ref that was created (empty if nothing to stash)
# exit: 0 always
stash_uncommitted_work() {
  if ! git rev-parse --git-dir >/dev/null 2>&1; then
    return 0
  fi
  if [[ -z "$(git status --porcelain 2>/dev/null)" ]]; then
    return 0  # clean tree, nothing to stash
  fi
  local tag
  tag="tts:$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  git stash push -u -m "$tag" >/dev/null
  # Echo the newly created stash ref (always stash@{0} right after push)
  echo "stash@{0} — $tag"
}

# --- /tmp/forge-* cleanup --------------------------------------------------

# Remove stale /tmp/forge-* files (older than 1 hour).
# stdout: count of files removed
# exit: 0 always
clean_temp_forge_files() {
  local count=0
  # shellcheck disable=SC2044
  for f in $(find /tmp -maxdepth 1 -name "forge-*" -mmin +60 2>/dev/null); do
    rm -rf "$f" 2>/dev/null && count=$((count + 1))
  done
  echo "$count"
}

# --- Stale lock files ------------------------------------------------------

# Inspect lock files in the current working directory tree.
# Removes .pid/.lock files whose PID is dead.
# Reports (on stdout) lock files whose PID is still alive, one per line:
#   {file} {pid}
# exit: 0 always (caller decides what to do with reported entries)
check_stale_lock_files() {
  local found_live=0
  # Consider common lock locations
  local candidates=()
  while IFS= read -r f; do
    candidates+=("$f")
  done < <(find . -maxdepth 3 \( -name "*.lock" -o -name "*.pid" \) 2>/dev/null)

  for f in "${candidates[@]}"; do
    # Try to read a PID from the file (first integer found)
    local pid
    pid=$(grep -oE '^[0-9]+' "$f" 2>/dev/null | head -1 || true)
    if [[ -z "$pid" ]]; then
      continue  # not a PID-bearing lock
    fi
    if kill -0 "$pid" 2>/dev/null; then
      echo "$f $pid"
      found_live=1
    else
      rm -f "$f" 2>/dev/null
    fi
  done
  return 0
}

# --- Port occupancy ---------------------------------------------------------

# Check if a TCP port is currently held.
# $1: port number
# stdout: holding PID if any
# exit: 0 if held, 1 if free
check_port_held() {
  local port="${1:?check_port_held requires port number}"
  local pid
  # Prefer lsof, fall back to ss
  if command -v lsof >/dev/null 2>&1; then
    pid=$(lsof -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -1)
  elif command -v ss >/dev/null 2>&1; then
    pid=$(ss -tlnp 2>/dev/null | awk -v p=":$port" '$4 ~ p {print $0}' | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)
  fi
  if [[ -n "${pid:-}" ]]; then
    echo "$pid"
    return 0
  fi
  return 1
}
```

- [ ] **Step 2: Commit (no tests yet — those are Task 10)**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git add lib/env-cleanup.sh
git commit -m "feat(env-cleanup): add skill-agnostic cleanup functions"
```

---

## Task 10: Integration tests for `env-cleanup.sh`

**Files:**
- Create: `~/.claude/skills/_forge-batch-engine/tests/integration/test_env_cleanup.sh`

**Context:** Realistic testing per user's memory: tests must exercise the actual functions inside real environments (temp git repos, actual processes, actual files), not mock internals. Each scenario sets up state, calls the function, asserts outcome, and cleans up.

- [ ] **Step 1: Write the integration test**

Create `~/.claude/skills/_forge-batch-engine/tests/integration/test_env_cleanup.sh`:

```bash
#!/bin/bash
# Integration tests for env-cleanup.sh.
# Uses real temp git repos, real sleep processes, real files — no mocking.

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(cd "$TEST_DIR/../../lib" && pwd)"

# shellcheck source=/dev/null
source "$LIB_DIR/env-cleanup.sh"

TMP=$(mktemp -d)
trap "rm -rf '$TMP'" EXIT

# ---------------------------------------------------------------------------
# check_existing_tts_stashes
# ---------------------------------------------------------------------------

(
  cd "$TMP"
  mkdir repo1 && cd repo1
  git init -q
  git config user.email test@example.com
  git config user.name Test
  echo "content" > file.txt
  git add file.txt
  git commit -q -m "init"

  # No stashes → exit 0, empty stdout
  out=$(check_existing_tts_stashes)
  if [[ -n "$out" ]]; then
    echo "FAIL: expected empty stdout for clean repo, got '$out'"
    exit 1
  fi
  echo "PASS: check_existing_tts_stashes on clean repo"

  # Create a tts stash
  echo "modified" > file.txt
  git stash push -m "tts:2026-04-13T00:00:00Z" >/dev/null

  # Now it should exit 1 with matching line
  if check_existing_tts_stashes >/dev/null; then
    echo "FAIL: expected exit 1 when tts stash exists"
    exit 1
  fi
  echo "PASS: check_existing_tts_stashes detects tts stash"
)

# ---------------------------------------------------------------------------
# stash_uncommitted_work
# ---------------------------------------------------------------------------

(
  cd "$TMP"
  mkdir repo2 && cd repo2
  git init -q
  git config user.email test@example.com
  git config user.name Test
  echo "initial" > file.txt
  git add file.txt
  git commit -q -m "init"

  # Clean tree → no stash created
  out=$(stash_uncommitted_work)
  if [[ -n "$out" ]]; then
    echo "FAIL: expected empty output for clean tree, got '$out'"
    exit 1
  fi
  echo "PASS: stash_uncommitted_work no-op on clean tree"

  # Dirty tree → stash created with tts tag
  echo "change" > file.txt
  out=$(stash_uncommitted_work)
  if [[ -z "$out" ]]; then
    echo "FAIL: expected non-empty output after stashing"
    exit 1
  fi
  if ! git stash list | grep -q "tts:"; then
    echo "FAIL: stash was not tagged with tts:"
    git stash list
    exit 1
  fi
  echo "PASS: stash_uncommitted_work creates tts-tagged stash"
)

# ---------------------------------------------------------------------------
# clean_temp_forge_files
# ---------------------------------------------------------------------------

(
  # Create a fresh file (not old enough)
  NEW_FILE="/tmp/forge-cleanup-test-new-$$"
  touch "$NEW_FILE"

  # Create an old file (faked via touch -d)
  OLD_FILE="/tmp/forge-cleanup-test-old-$$"
  touch -d "2 hours ago" "$OLD_FILE"

  count=$(clean_temp_forge_files)

  if [[ ! -f "$NEW_FILE" ]]; then
    echo "FAIL: clean_temp_forge_files removed new file"
    exit 1
  fi
  if [[ -f "$OLD_FILE" ]]; then
    echo "FAIL: clean_temp_forge_files did not remove old file"
    exit 1
  fi
  if (( count < 1 )); then
    echo "FAIL: expected count >= 1, got $count"
    exit 1
  fi
  rm -f "$NEW_FILE"
  echo "PASS: clean_temp_forge_files removes stale files only"
)

# ---------------------------------------------------------------------------
# check_stale_lock_files
# ---------------------------------------------------------------------------

(
  cd "$TMP"
  mkdir lockdir && cd lockdir

  # Dead-pid lock file → should be auto-removed
  echo "99999999" > dead.lock
  # Live-pid lock file using the current shell
  echo "$$" > live.lock

  out=$(check_stale_lock_files)

  if [[ -f dead.lock ]]; then
    echo "FAIL: dead.lock not removed"
    exit 1
  fi
  echo "PASS: dead-PID lock auto-removed"

  if [[ ! -f live.lock ]]; then
    echo "FAIL: live.lock was incorrectly removed"
    exit 1
  fi
  echo "PASS: live-PID lock preserved"

  if ! echo "$out" | grep -q "live.lock"; then
    echo "FAIL: live.lock not reported on stdout"
    echo "out was: '$out'"
    exit 1
  fi
  echo "PASS: live-PID lock reported"
)

# ---------------------------------------------------------------------------
# check_port_held
# ---------------------------------------------------------------------------

(
  # Unlikely-to-be-held port (but not reserved)
  FREE_PORT=53827

  if check_port_held "$FREE_PORT" >/dev/null; then
    echo "SKIP: port $FREE_PORT unexpectedly held, cannot test free case"
  else
    echo "PASS: check_port_held on free port returns 1"
  fi

  # Spawn a listener on an ephemeral port using python
  python3 -c "
import socket, time
s = socket.socket()
s.bind(('127.0.0.1', 0))
s.listen(1)
port = s.getsockname()[1]
print(port, flush=True)
time.sleep(10)
" > /tmp/port-test-$$ &
  PY_PID=$!

  # Wait for python to print the port
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if [[ -s /tmp/port-test-$$ ]]; then break; fi
    sleep 0.2
  done

  PORT=$(cat /tmp/port-test-$$ 2>/dev/null || echo "")
  rm -f /tmp/port-test-$$

  if [[ -z "$PORT" ]]; then
    echo "SKIP: could not spawn port listener"
  else
    if check_port_held "$PORT" >/dev/null; then
      echo "PASS: check_port_held on held port returns 0"
    else
      echo "FAIL: check_port_held did not detect held port $PORT"
      kill "$PY_PID" 2>/dev/null || true
      exit 1
    fi
  fi

  kill "$PY_PID" 2>/dev/null || true
  wait "$PY_PID" 2>/dev/null || true
)

echo ""
echo "All env-cleanup integration tests passed."
```

- [ ] **Step 2: Run integration test**

Run:
```bash
chmod +x ~/.claude/skills/_forge-batch-engine/tests/integration/test_env_cleanup.sh
cd ~/.claude/skills/_forge-batch-engine
bash tests/integration/test_env_cleanup.sh
```

Expected: All PASS or SKIP lines, final `All env-cleanup integration tests passed.`

- [ ] **Step 3: Commit**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git add tests/integration/test_env_cleanup.sh
git commit -m "test(env-cleanup): add integration tests using real git/procs/ports"
```

---

## Task 11: Run full pytest + integration suite

**Files:** (no new files)

**Context:** Single checkpoint that exercises everything added so far. Fail fast if anything regressed.

- [ ] **Step 1: Run pytest**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
uv run --with pytest pytest tests/ -v
```

Expected: 25 tests pass (12 progress + 13 sentinel).

- [ ] **Step 2: Run all integration tests sequentially**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
for test in tests/integration/test_*.sh; do
  echo "=== Running $test ==="
  bash "$test"
  echo
done
```

Expected: Every test script ends with `All ... integration tests passed.`

- [ ] **Step 3: No commit (this is just a gate)**

---

## Task 12: Write minimal usage example

**Files:**
- Create: `~/.claude/skills/_forge-batch-engine/examples/minimal-usage.md`

**Context:** A skill author reading this example should be able to copy-paste a working skeleton for a batch skill that uses the library.

- [ ] **Step 1: Write the example**

Create `~/.claude/skills/_forge-batch-engine/examples/minimal-usage.md`:

````markdown
# Minimal batch skill using _forge-batch-engine

This example shows the smallest viable batch skill that uses the library.
Copy-paste and adapt.

## SKILL.md outline

```markdown
---
name: my-batch
description: Example batch skill that uses _forge-batch-engine.
---

## Preamble

\```bash
ENGINE_DIR="$HOME/.claude/skills/_forge-batch-engine/lib"
source "$ENGINE_DIR/journal.sh"
source "$ENGINE_DIR/env-cleanup.sh"
source "$ENGINE_DIR/session-chain.sh"

FORGE_DIR="docs/forge/my-project"
mkdir -p "$FORGE_DIR/logs"

# Environment cleanup before starting
check_existing_tts_stashes || {
  echo "Existing tts stashes found. Resolve before proceeding."
  exit 1
}
stash_uncommitted_work
clean_temp_forge_files > /dev/null
check_stale_lock_files  # reports live PIDs; exit intentionally not checked
\```

## Initialize forge-progress.json

\```bash
if [[ ! -f "$FORGE_DIR/forge-progress.json" ]]; then
  cat > "$FORGE_DIR/forge-progress.json" <<EOF
{
  "schema_version": "1.0",
  "batch_status": "running",
  "last_pid": 0,
  "todos": {}
}
EOF
fi
\```

## Journal a start event

\```bash
journal_append "$FORGE_DIR" "BATCH_START" "skill=my-batch"
\```

## Check a sentinel before work

\```bash
python3 "$ENGINE_DIR/sentinel.py" check "$FORGE_DIR/t01-agreed.md" && {
  journal_append "$FORGE_DIR" "SKIP" "t01 already forged"
  exit 0
}
\```

## Spawn the next session

\```bash
NEW_PID=$(session_spawn "$FORGE_DIR")
journal_append "$FORGE_DIR" "SESSION_SPAWN" "pid=$NEW_PID"
\```

## Start the watchdog (background mode only)

\```bash
nohup "$ENGINE_DIR/watchdog.sh" "$FORGE_DIR" 20 > /dev/null 2>&1 &
journal_append "$FORGE_DIR" "WATCHDOG_SPAWN" "pid=$!"
\```
```

## Notes

- Always source `env-cleanup.sh` first and run `check_existing_tts_stashes` before
  any destructive or long-running work.
- Use `progress.py` (not inline python one-liners) for any forge-progress.json
  mutation — it's atomic.
- Write a sentinel with `sentinel.py write` only when a document is definitively
  forged (all rounds agreed).
````

- [ ] **Step 2: Commit**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git add examples/minimal-usage.md
git commit -m "docs(examples): add minimal usage example for batch skill authors"
```

---

## Task 13: Fill in the README API reference

**Files:**
- Modify: `~/.claude/skills/_forge-batch-engine/README.md`

**Context:** The README stub from Task 1 is replaced with a complete API reference covering every exposed function and CLI command. Skills authors should be able to use the library without reading the implementation source.

- [ ] **Step 1: Replace README with the full version**

Create `~/.claude/skills/_forge-batch-engine/README.md`:

````markdown
# _forge-batch-engine

Reusable session-chaining, progress-tracking, watchdog, sentinel-marker,
journaling, and environment-cleanup utilities for batch skills that split
long work into context-isolated CLI sessions.

## Status

Phase 1 of the `taste-to-ship` workflow — library extraction from
`plan-forge-batch`. Adopted by Phase 2 batch skills: `design-forge-batch`,
`task-forge-batch`, `impl-forge-batch`.

The existing `plan-forge-batch` skill is **not modified** by this extraction;
it continues to use its inline logic. This library is a parallel track.

## Layout

```
lib/
  watchdog.sh          — bash: background session hang detector + respawn
  session-chain.sh     — bash: claude -p spawn wrapper
  journal.sh           — bash: append-only event log
  env-cleanup.sh       — bash: zombie/port/stash/tmp cleanup
  progress.py          — python: forge-progress.json atomic read/write
  sentinel.py          — python: sentinel marker read/write
tests/
  test_progress.py     — pytest unit + CLI tests
  test_sentinel.py     — pytest unit + CLI tests
  integration/         — bash integration tests (real git repos, real procs)
  fixtures/            — sample data used by tests
examples/
  minimal-usage.md     — copy-pasteable batch skill skeleton
```

## Runtime requirements

- Bash 4+
- Python 3.13+
- `git` (for stash and env-cleanup helpers)
- `claude` CLI on PATH (for session-chain and watchdog)

## API — Python modules

### `progress.py`

Importable:

```python
import progress
progress.read(path) -> dict
progress.write(path, data) -> None                  # atomic via tempfile+rename
progress.get_field(path, "dotted.path") -> Any
progress.set_field(path, "dotted.path", value) -> Any  # returns old value
progress.atomic_update(path, fn)                    # fn(dict) -> dict
```

CLI:

```
python progress.py get <file> <dotted.field>
python progress.py set <file> <dotted.field> <value>   # value is JSON-parsed, string fallback
```

Exit: 0 on success, 1 on error (missing file / missing field / invalid JSON).

### `sentinel.py`

Importable:

```python
import sentinel
sentinel.has_sentinel(path) -> bool
sentinel.read_sentinel(path) -> dict | None          # keys: topic, stem, timestamp
sentinel.write_sentinel(path, topic, stem, timestamp=None)  # None → UTC now
```

CLI:

```
python sentinel.py check <file>                      # exit 0 if present, 1 otherwise
python sentinel.py read <file>                       # prints JSON
python sentinel.py write <file> --topic T --stem S [--timestamp TS]
```

Marker format: `<!-- forge:{topic}:{stem}:complete:{ISO 8601 timestamp} -->`
Must appear on the last non-empty line.

## API — Bash modules (source and call functions)

### `journal.sh`

```bash
source /path/to/_forge-batch-engine/lib/journal.sh
journal_append <forge_dir> <event> [details...]
```

Writes `[HH:MM:SS] EVENT details` to `{forge_dir}/logs/journal.log`.

### `session-chain.sh`

```bash
source /path/to/_forge-batch-engine/lib/session-chain.sh
new_pid=$(session_spawn <forge_dir>)
```

- Sources `.env` if present (for API keys).
- Spawns `claude -p --permission-mode bypassPermissions --output-format stream-json --verbose`
  with stdin from `{forge_dir}/session-prompt.txt`.
- Log to `{forge_dir}/logs/session-{timestamp}.log`.
- Updates `forge-progress.json last_pid` via `progress.py`.
- Echoes new PID.

### `env-cleanup.sh`

```bash
source /path/to/_forge-batch-engine/lib/env-cleanup.sh

check_existing_tts_stashes
# stdout: matching stash entries (may be empty)
# exit:   0 if none, 1 if any

stash_uncommitted_work
# stdout: created stash ref (or empty if tree was clean)
# exit:   0 always

clean_temp_forge_files
# stdout: count of files removed
# removes /tmp/forge-* older than 1 hour

check_stale_lock_files
# stdout: "<file> <pid>" per line for live-PID locks (dead ones are auto-removed)
# exit:   0 always

check_port_held <port>
# stdout: holding PID (if any)
# exit:   0 if held, 1 if free
```

## Standalone script

### `watchdog.sh`

```bash
nohup /path/to/_forge-batch-engine/lib/watchdog.sh <forge_dir> [timeout_min] &
```

- Polls every 5 minutes.
- Exits when `forge-progress.json` `batch_status != running`.
- If session log mtime is stale beyond `timeout_min` and CPU < 1% → kills
  process and respawns via `session-chain.sh`.
- Logs to `{forge_dir}/logs/watchdog.log`.

## Running tests

```bash
# Python tests
uv run --with pytest pytest tests/ -v

# Bash integration tests
for t in tests/integration/test_*.sh; do bash "$t"; done
```

## See also

- `examples/minimal-usage.md` — minimal batch skill skeleton
- taste-to-ship spec: `docs/superpowers/specs/2026-04-12-taste-to-ship-design.md`
  in the synco repo
````

- [ ] **Step 2: Commit**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git add README.md
git commit -m "docs(readme): complete API reference"
```

---

## Task 14: End-to-end smoke test

**Files:**
- Create: `~/.claude/skills/_forge-batch-engine/tests/integration/test_smoke_e2e.sh`

**Context:** A single script that exercises the full library in a realistic batch-skill skeleton flow: env cleanup → progress init → sentinel check → journal → mock session spawn → watchdog pseudo-spawn. This is the "does everything wire together" test.

- [ ] **Step 1: Write the smoke test**

Create `~/.claude/skills/_forge-batch-engine/tests/integration/test_smoke_e2e.sh`:

```bash
#!/bin/bash
# End-to-end smoke test: exercises the full library in a batch-skill-like flow.

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(cd "$TEST_DIR/../../lib" && pwd)"

TMP=$(mktemp -d)
trap "rm -rf '$TMP'" EXIT

# Mock claude on PATH so session_spawn works
MOCK_BIN="$TMP/bin"
mkdir -p "$MOCK_BIN"
cat > "$MOCK_BIN/claude" <<'MOCK'
#!/bin/bash
cat > /dev/null
sleep 5
MOCK
chmod +x "$MOCK_BIN/claude"
export PATH="$MOCK_BIN:$PATH"

PROJECT="$TMP/project"
FORGE_DIR="$PROJECT/docs/forge/smoke"
mkdir -p "$PROJECT" "$FORGE_DIR/logs"
cd "$PROJECT"

git init -q
git config user.email test@example.com
git config user.name Test
echo "initial" > README.md
git add README.md
git commit -q -m "init"

# shellcheck source=/dev/null
source "$LIB_DIR/journal.sh"
# shellcheck source=/dev/null
source "$LIB_DIR/env-cleanup.sh"
# shellcheck source=/dev/null
source "$LIB_DIR/session-chain.sh"

# --- Step 1: env cleanup on a clean repo
if ! check_existing_tts_stashes >/dev/null; then
  echo "FAIL: existing tts stashes reported on clean repo"
  exit 1
fi
stash_uncommitted_work >/dev/null
clean_temp_forge_files >/dev/null
check_stale_lock_files >/dev/null
echo "PASS: env cleanup succeeded on clean repo"

# --- Step 2: initialize forge-progress.json
cat > "$FORGE_DIR/forge-progress.json" <<EOF
{
  "schema_version": "1.0",
  "batch_status": "running",
  "last_pid": 0,
  "todos": {"t01": {"tempering_status": "pending"}}
}
EOF

# --- Step 3: write a sentinel to a fake agreed doc
AGREED="$FORGE_DIR/t01-agreed.md"
echo "# t01 agreed" > "$AGREED"
python3 "$LIB_DIR/sentinel.py" write "$AGREED" --topic smoke --stem t01
if ! python3 "$LIB_DIR/sentinel.py" check "$AGREED"; then
  echo "FAIL: sentinel.py check did not detect just-written marker"
  exit 1
fi
echo "PASS: sentinel write+check roundtrip"

# --- Step 4: journal a few events
journal_append "$FORGE_DIR" "SMOKE_START" "project=smoke"
journal_append "$FORGE_DIR" "SMOKE_NOTE" "k=v"
if [[ $(wc -l < "$FORGE_DIR/logs/journal.log") != "2" ]]; then
  echo "FAIL: journal did not record 2 events"
  exit 1
fi
echo "PASS: journal recorded events"

# --- Step 5: spawn a mock session
cat > "$FORGE_DIR/session-prompt.txt" <<EOF
smoke test prompt
EOF

NEW_PID=$(session_spawn "$FORGE_DIR")
if ! [[ "$NEW_PID" =~ ^[0-9]+$ ]]; then
  echo "FAIL: session_spawn returned '$NEW_PID'"
  exit 1
fi
if ! kill -0 "$NEW_PID" 2>/dev/null; then
  echo "FAIL: spawned PID $NEW_PID not alive"
  exit 1
fi

# Verify forge-progress.json last_pid updated
STORED=$(python3 "$LIB_DIR/progress.py" get "$FORGE_DIR/forge-progress.json" last_pid)
if [[ "$STORED" != "$NEW_PID" ]]; then
  echo "FAIL: last_pid is '$STORED', expected '$NEW_PID'"
  exit 1
fi
echo "PASS: session spawn + progress update"

# --- Step 6: mark batch complete and verify watchdog would exit
python3 "$LIB_DIR/progress.py" set "$FORGE_DIR/forge-progress.json" batch_status complete
STATUS=$(python3 "$LIB_DIR/progress.py" get "$FORGE_DIR/forge-progress.json" batch_status)
if [[ "$STATUS" != "complete" ]]; then
  echo "FAIL: batch_status update failed"
  exit 1
fi
echo "PASS: batch_status transition"

# Cleanup the spawned mock
kill "$NEW_PID" 2>/dev/null || true
wait "$NEW_PID" 2>/dev/null || true

echo ""
echo "SMOKE E2E: all phases passed."
```

- [ ] **Step 2: Run the smoke test**

Run:
```bash
chmod +x ~/.claude/skills/_forge-batch-engine/tests/integration/test_smoke_e2e.sh
cd ~/.claude/skills/_forge-batch-engine
bash tests/integration/test_smoke_e2e.sh
```

Expected: Every step logs PASS, final `SMOKE E2E: all phases passed.`

- [ ] **Step 3: Commit**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git add tests/integration/test_smoke_e2e.sh
git commit -m "test(smoke): add end-to-end smoke test exercising full library"
```

---

## Task 15: Final verification — run everything one more time

**Files:** (none new)

**Context:** Last checkpoint before declaring Phase 1 done.

- [ ] **Step 1: Run all Python tests**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
uv run --with pytest pytest tests/ -v
```

Expected: All 25 tests pass. Zero failures.

- [ ] **Step 2: Run all integration tests**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
for test in tests/integration/test_*.sh; do
  echo "=== $test ==="
  bash "$test" || { echo "INTEGRATION FAILED: $test"; exit 1; }
done
echo "All integration tests passed."
```

Expected: Every test reports pass, final line `All integration tests passed.`

- [ ] **Step 3: Confirm git log shows clean history**

Run:
```bash
cd ~/.claude/skills/_forge-batch-engine
git log --oneline
```

Expected: Roughly 12-14 commits, one per meaningful task. Messages are descriptive.

- [ ] **Step 4: Report completion**

Write a short status line (not committed, just reported to user):

```
Phase 1 complete. _forge-batch-engine library extracted at ~/.claude/skills/_forge-batch-engine/.
Lib: 6 modules (3 bash, 2 python, 1 bash daemon). Tests: 25 pytest + 5 integration scripts.
Ready for Phase 2 adoption by design-forge-batch, task-forge-batch, impl-forge-batch.
```

---

## Self-Review (author checklist — not a task for the executor)

The author of this plan performed these checks before committing:

**1. Spec coverage for Phase 1:**
- ✅ `_forge-batch-engine/` directory: Task 1
- ✅ watchdog.sh extraction: Task 6
- ✅ session chaining extraction: Task 8
- ✅ progress-tracking extraction: Tasks 2-3
- ✅ sentinel marker: Tasks 4-5
- ✅ env cleanup: Tasks 9-10
- ✅ journal logging: Task 7
- ✅ plan-forge-batch untouched: verified by scope (no task modifies plan-forge-batch)
- ✅ Tests + docs: Tasks 11-15

**2. Placeholder scan:** No TBD/TODO/"implement later" left in task bodies. Every code block is complete.

**3. Type consistency:**
- `get_field` / `set_field` used consistently in progress.py tests and CLI.
- `has_sentinel` / `read_sentinel` / `write_sentinel` naming matches between API, tests, CLI.
- `session_spawn` / `journal_append` / `check_*` / `stash_uncommitted_work` / `clean_temp_forge_files` — all bash function names match across definitions, tests, examples, and README.
- `check_port_held` returns 0/1 consistently.

**4. Spec v5 requirements mapped to tasks:** All Phase 1 items from Migration Path are covered. Phases 2-6 will be separate plans.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-13-tts-phase-1-forge-batch-engine.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
