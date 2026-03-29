# Task UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the dashboard task system so tasks show meaningful action summaries (via LLM), classify by date, and expand inline with details on click.

**Architecture:** Embedding model detects task-worthy interactions (existing). LLM extracts action title + due date for detected tasks. Dashboard groups tasks by date. Cards expand inline on click.

**LLM Strategy:** Default = Claude CLI (현재 설정 유지). Fallback chain: Kimi K2.5 (moonshot > opencode > openrouter) > MiniMax M2.7 (openrouter). 옵션만 만들어 두고 나중에 테스트.

**Tech Stack:** Django 5.2, HTMX, Tailwind CDN, Gemini Embedding (existing), LLM via Claude CLI (default) + OpenAI-compatible fallback (openai SDK)

**Spec:** `docs/superpowers/specs/2026-03-30-task-ux-redesign.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `contacts/models.py` | Modify | Add `description`, `status` fields to Task; remove `is_completed` |
| `contacts/migrations/0004_task_status_description.py` | Create | Schema migration + data migration |
| `common/llm.py` | Create | Multi-provider LLM client (Claude CLI, Kimi, MiniMax, OpenRouter) |
| `intelligence/services/_references.py` | Modify | Add `waiting` reference vector |
| `intelligence/services/task_detect.py` | Modify | Add waiting detection + LLM title extraction |
| `intelligence/management/commands/reset_tasks.py` | Create | Delete AI tasks, reset task_checked flags |
| `accounts/views.py` | Modify | Date-based task grouping for dashboard |
| `accounts/templates/accounts/partials/dashboard/section_tasks.html` | Modify | Date groups UI, section title "할 일" |
| `accounts/templates/accounts/partials/dashboard/_task_card.html` | Modify | Inline expand on click |
| `contacts/views.py` | Modify | task_complete/edit/create use status field |
| `contacts/templates/contacts/partials/task_edit_form.html` | Modify | Include description field |
| `main/settings.py` | Modify | Add LLM provider config |
| `conftest.py` | Create | Pytest-django configuration |
| `tests/test_llm.py` | Create | LLM client tests |
| `tests/test_task_detect.py` | Create | Task detection pipeline tests |
| `tests/test_task_views.py` | Create | Task CRUD view tests |

---

### Task 1: Pytest Configuration

**Files:**
- Create: `conftest.py`
- Create: `pyproject.toml` (append pytest section)

- [ ] **Step 1: Add pytest-django config to pyproject.toml**

Add at the end of `pyproject.toml`:

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "main.settings"
pythonpath = ["."]
```

- [ ] **Step 2: Create conftest.py**

```python
import pytest


@pytest.fixture
def user(db):
    from accounts.models import User

    return User.objects.create_user(
        kakao_id="test_user_123",
        role="fc",
    )


@pytest.fixture
def contact(db, user):
    from contacts.models import Contact

    return Contact.objects.create(
        fc=user,
        name="테스트고객",
        company_name="(주)테스트",
        industry="제조업",
    )
```

- [ ] **Step 3: Verify pytest collects**

Run: `uv run pytest --co -q`
Expected: `no tests collected` (but no errors)

- [ ] **Step 4: Commit**

```bash
git add conftest.py pyproject.toml
git commit -m "chore: configure pytest-django"
```

---

### Task 2: Task Model Migration

**Files:**
- Modify: `contacts/models.py:151-187`
- Create: `contacts/migrations/0004_task_status_description.py` (auto-generated)

- [ ] **Step 1: Write the failing test**

Create `tests/test_task_model.py`:

```python
import pytest
from contacts.models import Task


@pytest.mark.django_db
def test_task_has_status_field(user, contact):
    task = Task.objects.create(
        fc=user,
        contact=contact,
        title="팔로업 전화",
        status=Task.Status.PENDING,
    )
    assert task.status == "pending"


@pytest.mark.django_db
def test_task_has_description_field(user, contact):
    task = Task.objects.create(
        fc=user,
        contact=contact,
        title="팔로업 전화",
        description="원래 메모 내용이 여기에 들어갑니다",
    )
    assert task.description == "원래 메모 내용이 여기에 들어갑니다"


@pytest.mark.django_db
def test_task_status_choices(user, contact):
    for status_value in ["pending", "waiting", "done"]:
        task = Task.objects.create(
            fc=user,
            contact=contact,
            title=f"task_{status_value}",
            status=status_value,
        )
        assert task.status == status_value


@pytest.mark.django_db
def test_task_ordering_by_status_and_date(user, contact):
    """pending tasks before done, then by due_date."""
    from datetime import date

    t1 = Task.objects.create(fc=user, contact=contact, title="done task", status="done")
    t2 = Task.objects.create(fc=user, contact=contact, title="pending later", status="pending", due_date=date(2026, 12, 1))
    t3 = Task.objects.create(fc=user, contact=contact, title="pending sooner", status="pending", due_date=date(2026, 4, 1))

    tasks = list(Task.objects.filter(fc=user))
    titles = [t.title for t in tasks]
    # pending tasks first (by due_date asc), then done
    assert titles.index("pending sooner") < titles.index("pending later")
    assert titles.index("pending later") < titles.index("done task")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_task_model.py -v`
Expected: FAIL — `Task has no attribute 'Status'` or similar

- [ ] **Step 3: Modify Task model**

In `contacts/models.py`, replace the Task class:

```python
class Task(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "할 일"
        WAITING = "waiting", "대기"
        DONE = "done", "완료"

    class Source(models.TextChoices):
        MANUAL = "manual", "직접 입력"
        AI_EXTRACTED = "ai_extracted", "AI 추출"

    fc = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    contact = models.ForeignKey(
        "Contact",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tasks",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    source = models.CharField(
        max_length=15,
        choices=Source.choices,
        default=Source.MANUAL,
    )
    source_interactions = models.ManyToManyField(
        "Interaction",
        blank=True,
        related_name="detected_tasks",
    )

    class Meta:
        db_table = "tasks"
        ordering = ["status", "due_date", "-created_at"]

    def __str__(self):
        return self.title
```

- [ ] **Step 4: Generate and apply migration**

```bash
uv run python manage.py makemigrations contacts --name task_status_description
```

Edit the generated migration to add a `RunPython` data migration that converts `is_completed`:

```python
from django.db import migrations, models


def migrate_is_completed_to_status(apps, schema_editor):
    Task = apps.get_model("contacts", "Task")
    Task.objects.filter(is_completed=True).update(status="done")
    Task.objects.filter(is_completed=False).update(status="pending")


def reverse_status_to_is_completed(apps, schema_editor):
    Task = apps.get_model("contacts", "Task")
    Task.objects.filter(status="done").update(is_completed=True)
    Task.objects.filter(status__in=["pending", "waiting"]).update(is_completed=False)


class Migration(migrations.Migration):
    dependencies = [
        ("contacts", "0003_contact_business_urgency_score_and_more"),
    ]

    operations = [
        # Add new fields
        migrations.AddField(
            model_name="task",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="task",
            name="status",
            field=models.CharField(
                choices=[("pending", "할 일"), ("waiting", "대기"), ("done", "완료")],
                default="pending",
                max_length=10,
            ),
        ),
        # Migrate data
        migrations.RunPython(migrate_is_completed_to_status, reverse_status_to_is_completed),
        # Remove old field
        migrations.RemoveField(
            model_name="task",
            name="is_completed",
        ),
        # Update ordering
        migrations.AlterModelOptions(
            name="task",
            options={"ordering": ["status", "due_date", "-created_at"]},
        ),
    ]
```

Apply:
```bash
uv run python manage.py migrate
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_task_model.py -v`
Expected: all 4 PASS

- [ ] **Step 6: Commit**

```bash
git add contacts/models.py contacts/migrations/ tests/test_task_model.py
git commit -m "feat: add status and description fields to Task model"
```

---

### Task 3: Multi-Provider LLM Client

**Files:**
- Create: `common/llm.py`
- Create: `tests/test_llm.py`
- Modify: `main/settings.py`

- [ ] **Step 1: Add LLM settings**

Append to `main/settings.py`:

```python
# LLM Provider Configuration
# Default: claude_cli (uses Claude Code subscription, no API key needed)
# Fallback chain: kimi > minimax (configured but not active until tested)
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "claude_cli")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

# Provider-specific configs (options ready for future testing)
LLM_PROVIDERS = {
    "claude_cli": {
        # Uses `claude --print` subprocess, no API key needed
        "model": "",
    },
    "kimi": {
        # Kimi K2.5 via Moonshot AI direct API
        "base_url": os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1"),
        "model": os.environ.get("LLM_MODEL", "kimi-k2.5"),
    },
    "minimax": {
        # MiniMax M2.7 via OpenRouter
        "base_url": "https://openrouter.ai/api/v1",
        "model": os.environ.get("LLM_MODEL", "minimax/minimax-m2.7"),
    },
    "openrouter": {
        # Any model via OpenRouter
        "base_url": "https://openrouter.ai/api/v1",
        "model": os.environ.get("LLM_MODEL", "anthropic/claude-sonnet-4"),
    },
}
```

**.env example (for future fallback testing):**
```bash
# Default (current)
LLM_PROVIDER=claude_cli

# Kimi K2.5 via Moonshot
# LLM_PROVIDER=kimi
# LLM_API_KEY=sk-...
# KIMI_BASE_URL=https://api.moonshot.cn/v1  (or opencode/openrouter URL)

# MiniMax M2.7 via OpenRouter
# LLM_PROVIDER=minimax
# LLM_API_KEY=sk-or-...
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_llm.py`:

```python
import json
from unittest.mock import patch, MagicMock

import pytest

from common.llm import call_llm_json


def test_claude_cli_provider():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"title": "팔로업 전화", "due_date": null}'

    with patch("common.llm.subprocess.run", return_value=mock_result) as mock_run:
        with patch("common.llm._get_provider", return_value="claude_cli"):
            result = call_llm_json("test prompt")

    assert result == {"title": "팔로업 전화", "due_date": None}
    mock_run.assert_called_once()


def test_openai_compatible_provider():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"title": "자료 전달", "due_date": "2026-04-01"}'

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("common.llm._get_openai_client", return_value=mock_client):
        with patch("common.llm._get_provider", return_value="kimi"):
            result = call_llm_json("test prompt", system="system prompt")

    assert result == {"title": "자료 전달", "due_date": "2026-04-01"}


def test_json_extraction_from_code_block():
    from common.llm import _extract_json

    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('some text\n```\n{"a": 1}\n```\nmore') == {"a": 1}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'common.llm'`

- [ ] **Step 4: Install openai SDK**

```bash
uv add openai
```

- [ ] **Step 5: Create common/llm.py**

```python
"""Multi-provider LLM client.

Supports: claude_cli (subprocess), kimi (Moonshot API), minimax (OpenRouter),
openrouter (any model). All OpenAI-compatible providers use the openai SDK.
"""

import json
import logging
import subprocess

from django.conf import settings

logger = logging.getLogger(__name__)

_openai_client = None


def _get_provider() -> str:
    return getattr(settings, "LLM_PROVIDER", "claude_cli")


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        provider = _get_provider()
        config = settings.LLM_PROVIDERS.get(provider, {})
        _openai_client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=config.get("base_url"),
        )
    return _openai_client


def _extract_json(text: str) -> dict | list:
    """Extract JSON from raw LLM response, handling ```json blocks."""
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def call_llm(prompt: str, system: str = "", timeout: int = 30) -> str:
    """Call LLM and return raw text response."""
    provider = _get_provider()

    if provider == "claude_cli":
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        result = subprocess.run(
            ["claude", "--print"],
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI error: {result.stderr}")
        return result.stdout.strip()

    # OpenAI-compatible providers (kimi, minimax, openrouter)
    client = _get_openai_client()
    config = settings.LLM_PROVIDERS.get(provider, {})
    model = settings.LLM_MODEL or config.get("model", "")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=500,
    )
    return response.choices[0].message.content.strip()


def call_llm_json(prompt: str, system: str = "", timeout: int = 30) -> dict | list:
    """Call LLM and parse response as JSON."""
    text = call_llm(prompt, system=system, timeout=timeout)
    return _extract_json(text)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_llm.py -v`
Expected: all 3 PASS

- [ ] **Step 7: Commit**

```bash
git add common/llm.py tests/test_llm.py main/settings.py
git commit -m "feat: add multi-provider LLM client (Claude/Kimi/MiniMax/OpenRouter)"
```

---

### Task 4: Task Detection Pipeline Update

**Files:**
- Modify: `intelligence/services/_references.py:28-33`
- Modify: `intelligence/services/task_detect.py`
- Create: `tests/test_task_detect.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_task_detect.py`:

```python
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from intelligence.services.task_detect import detect_task
from intelligence.services._references import TASK_REFS


def test_task_refs_has_waiting():
    assert "waiting" in TASK_REFS


@pytest.mark.django_db
def test_detect_task_creates_with_llm_title(user, contact):
    from contacts.models import Interaction, Task

    interaction = Interaction.objects.create(
        fc=user,
        contact=contact,
        type="memo",
        summary="다음주에 다시 전화해서 견적서 보내기로 했다",
    )

    # Mock embedding to return a vector close to "task" reference
    fake_embedding = [0.1] * 3072

    # Mock reference vectors so task scores high
    fake_refs = {
        "task": np.array([0.1] * 3072),
        "followup": np.array([0.05] * 3072),
        "promise": np.array([0.05] * 3072),
        "waiting": np.array([0.0] * 3072),
        "not_task": np.array([0.0] * 3072),
    }

    llm_result = {"title": "견적서 발송 팔로업", "due_date": "2026-04-07"}

    with patch("intelligence.services.task_detect.get_task_vectors", return_value=fake_refs):
        with patch("intelligence.services.task_detect.call_llm_json", return_value=llm_result):
            task = detect_task(interaction, embedding=fake_embedding)

    assert task is not None
    assert task.title == "견적서 발송 팔로업"
    assert task.description == interaction.summary
    assert task.status == "pending"
    assert str(task.due_date) == "2026-04-07"


@pytest.mark.django_db
def test_detect_task_waiting_status(user, contact):
    from contacts.models import Interaction, Task

    interaction = Interaction.objects.create(
        fc=user,
        contact=contact,
        type="memo",
        summary="좋은 내용이지만 지금은 상황이 안 되고 나중에 연락하겠다",
    )

    fake_embedding = [0.1] * 3072

    # waiting scores highest
    fake_refs = {
        "task": np.array([0.0] * 3072),
        "followup": np.array([0.0] * 3072),
        "promise": np.array([0.0] * 3072),
        "waiting": np.array([0.1] * 3072),
        "not_task": np.array([0.0] * 3072),
    }

    llm_result = {"title": "재연락 대기", "due_date": None}

    with patch("intelligence.services.task_detect.get_task_vectors", return_value=fake_refs):
        with patch("intelligence.services.task_detect.call_llm_json", return_value=llm_result):
            task = detect_task(interaction, embedding=fake_embedding)

    assert task is not None
    assert task.status == "waiting"
    assert task.due_date is None


@pytest.mark.django_db
def test_detect_task_not_task_returns_none(user, contact):
    from contacts.models import Interaction

    interaction = Interaction.objects.create(
        fc=user,
        contact=contact,
        type="memo",
        summary="일반적인 안부 통화",
    )

    fake_embedding = [0.1] * 3072

    # not_task scores highest
    fake_refs = {
        "task": np.array([0.0] * 3072),
        "followup": np.array([0.0] * 3072),
        "promise": np.array([0.0] * 3072),
        "waiting": np.array([0.0] * 3072),
        "not_task": np.array([0.1] * 3072),
    }

    with patch("intelligence.services.task_detect.get_task_vectors", return_value=fake_refs):
        task = detect_task(interaction, embedding=fake_embedding)

    assert task is None
    interaction.refresh_from_db()
    assert interaction.task_checked is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_task_detect.py -v`
Expected: FAIL — imports or assertions fail

- [ ] **Step 3: Add waiting to reference vectors**

In `intelligence/services/_references.py`, change `TASK_REFS`:

```python
TASK_REFS = {
    "task": "견적서를 보내기로 약속했고 다음주까지 회신해야 한다",
    "followup": "다시 연락하기로 했고 자료를 준비해서 전달해야 한다",
    "promise": "보험 상품 비교표를 만들어서 보내주기로 했다",
    "waiting": "좋은 내용이지만 지금은 상황이 안 되고 나중에 연락하겠다고 했다",
    "not_task": "일반적인 안부를 나누었고 특별한 약속은 없었다",
}
```

Delete the cache file so new vectors get generated:
```bash
rm -f .cache/task_refs.json
```

- [ ] **Step 4: Rewrite task_detect.py**

Replace `intelligence/services/task_detect.py`:

```python
import logging
from datetime import date

import numpy as np

from common.embedding import get_embedding, get_embeddings_batch
from common.llm import call_llm_json

from ._references import cosine_similarity, get_task_vectors

logger = logging.getLogger(__name__)

TASK_MARGIN = 0.05

TITLE_SYSTEM_PROMPT = (
    "보험설계사(FC)의 고객 접점 메모에서 FC가 해야 할 다음 액션을 추출합니다. "
    "반드시 아래 JSON 형식으로만 응답하세요."
)

TITLE_USER_TEMPLATE = """메모: {summary}
고객: {contact_name} / {company_name}

다음 JSON을 반환하세요:
{{"title": "FC가 해야 할 다음 액션 한 줄 요약 (20자 이내)", "due_date": "YYYY-MM-DD 또는 null (메모에 날짜 힌트가 있을 때만)"}}"""


def _extract_title_and_date(interaction) -> dict:
    """Call LLM to extract action title and due date from memo."""
    try:
        result = call_llm_json(
            TITLE_USER_TEMPLATE.format(
                summary=interaction.summary[:500],
                contact_name=interaction.contact.name if interaction.contact else "",
                company_name=interaction.contact.company_name if interaction.contact else "",
            ),
            system=TITLE_SYSTEM_PROMPT,
            timeout=30,
        )
        return {
            "title": str(result.get("title", ""))[:200],
            "due_date": result.get("due_date"),
        }
    except Exception:
        logger.exception("LLM title extraction failed")
        # Fallback: use contact name + generic title
        name = interaction.contact.name if interaction.contact else ""
        return {"title": f"{name} 팔로업", "due_date": None}


def _parse_due_date(date_str: str | None) -> date | None:
    """Parse YYYY-MM-DD string to date, return None on failure."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def detect_task(interaction, embedding: list[float] | None = None):
    """Single interaction -> Task or None.

    Pipeline:
    1. Cosine similarity against reference vectors (task/waiting/not_task)
    2. If task-worthy, call LLM for title + due_date extraction
    3. Create Task with appropriate status
    """
    from contacts.models import Task

    refs = get_task_vectors()
    if refs is None:
        return None

    if embedding is None:
        embedding = get_embedding(interaction.summary)
    if embedding is None:
        return None

    vec = np.array(embedding)
    scores = {label: cosine_similarity(vec, ref_vec) for label, ref_vec in refs.items()}

    task_score = max(scores.get("task", 0), scores.get("followup", 0), scores.get("promise", 0))
    waiting_score = scores.get("waiting", 0)
    not_task_score = scores.get("not_task", 0)

    # Determine status
    status = None
    if waiting_score > task_score and waiting_score - not_task_score > TASK_MARGIN:
        status = Task.Status.WAITING
    elif task_score - not_task_score > TASK_MARGIN:
        status = Task.Status.PENDING

    result = None
    if status is not None:
        extracted = _extract_title_and_date(interaction)
        due_date = _parse_due_date(extracted.get("due_date"))

        task = Task.objects.create(
            fc=interaction.fc,
            contact=interaction.contact,
            title=extracted["title"],
            description=interaction.summary,
            due_date=due_date,
            status=status,
            source=Task.Source.AI_EXTRACTED,
        )
        task.source_interactions.add(interaction)
        result = task

    interaction.task_checked = True
    interaction.save(update_fields=["task_checked"])
    return result


def detect_tasks_batch(
    interactions: list,
    embeddings: list[list[float]] | None = None,
) -> list:
    """Batch detect tasks. Calls LLM per detected task (not per interaction)."""
    from contacts.models import Interaction, Task

    if not interactions:
        return []

    refs = get_task_vectors()
    if refs is None:
        return []

    if embeddings is None:
        texts = [i.summary for i in interactions]
        emb_list = get_embeddings_batch(texts)
    else:
        emb_list = list(embeddings)

    tasks = []
    checked_interactions = []

    for interaction, emb in zip(interactions, emb_list):
        if emb is None:
            continue

        vec = np.array(emb)
        scores = {label: cosine_similarity(vec, ref_vec) for label, ref_vec in refs.items()}

        task_score = max(scores.get("task", 0), scores.get("followup", 0), scores.get("promise", 0))
        waiting_score = scores.get("waiting", 0)
        not_task_score = scores.get("not_task", 0)

        status = None
        if waiting_score > task_score and waiting_score - not_task_score > TASK_MARGIN:
            status = Task.Status.WAITING
        elif task_score - not_task_score > TASK_MARGIN:
            status = Task.Status.PENDING

        if status is not None:
            extracted = _extract_title_and_date(interaction)
            due_date = _parse_due_date(extracted.get("due_date"))

            task = Task.objects.create(
                fc=interaction.fc,
                contact=interaction.contact,
                title=extracted["title"],
                description=interaction.summary,
                due_date=due_date,
                status=status,
                source=Task.Source.AI_EXTRACTED,
            )
            task.source_interactions.add(interaction)
            tasks.append(task)

        interaction.task_checked = True
        checked_interactions.append(interaction)

    if checked_interactions:
        Interaction.objects.bulk_update(checked_interactions, ["task_checked"])

    return tasks
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_task_detect.py -v`
Expected: all 4 PASS

- [ ] **Step 6: Commit**

```bash
git add intelligence/services/_references.py intelligence/services/task_detect.py tests/test_task_detect.py
git commit -m "feat: add waiting detection and LLM title extraction to task pipeline"
```

---

### Task 5: Data Cleanup Command

**Files:**
- Create: `intelligence/management/commands/reset_tasks.py`

- [ ] **Step 1: Create management command**

```bash
mkdir -p intelligence/management/commands
touch intelligence/management/__init__.py
touch intelligence/management/commands/__init__.py
```

Create `intelligence/management/commands/reset_tasks.py`:

```python
from django.core.management.base import BaseCommand

from contacts.models import Interaction, Task


class Command(BaseCommand):
    help = "Delete all AI-extracted tasks and reset task_checked flags for re-processing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        ai_tasks = Task.objects.filter(source=Task.Source.AI_EXTRACTED)
        checked = Interaction.objects.filter(task_checked=True)

        task_count = ai_tasks.count()
        interaction_count = checked.count()

        if dry_run:
            self.stdout.write(f"Would delete {task_count} AI-extracted tasks")
            self.stdout.write(f"Would reset {interaction_count} interactions (task_checked → False)")
            return

        ai_tasks.delete()
        checked.update(task_checked=False)

        self.stdout.write(self.style.SUCCESS(
            f"Deleted {task_count} AI tasks, reset {interaction_count} interactions"
        ))
```

- [ ] **Step 2: Test dry-run**

Run: `uv run python manage.py reset_tasks --dry-run`
Expected: `Would delete N AI-extracted tasks` / `Would reset N interactions`

- [ ] **Step 3: Commit**

```bash
git add intelligence/management/
git commit -m "feat: add reset_tasks management command"
```

---

### Task 6: Dashboard View — Date-Based Grouping

**Files:**
- Modify: `accounts/views.py:29-56`
- Create: `tests/test_task_views.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_task_views.py`:

```python
import pytest
from datetime import date, timedelta
from django.test import RequestFactory

from contacts.models import Task


@pytest.mark.django_db
def test_dashboard_groups_tasks_by_date(user, contact):
    today = date.today()

    # Overdue
    Task.objects.create(fc=user, contact=contact, title="밀린 업무", status="pending", due_date=today - timedelta(days=3))
    # Today
    Task.objects.create(fc=user, contact=contact, title="오늘 할 일", status="pending", due_date=today)
    # This week
    Task.objects.create(fc=user, contact=contact, title="이번 주", status="pending", due_date=today + timedelta(days=3))
    # No date
    Task.objects.create(fc=user, contact=contact, title="날짜 미지정", status="pending")
    # Waiting (should not appear)
    Task.objects.create(fc=user, contact=contact, title="대기중", status="waiting")
    # Done (should not appear)
    Task.objects.create(fc=user, contact=contact, title="완료", status="done")

    from accounts.views import _build_task_context
    ctx = _build_task_context(user)

    assert ctx["overdue_tasks"].count() == 1
    assert ctx["today_tasks"].count() == 1
    assert ctx["week_tasks"].count() == 1
    assert ctx["undated_tasks"].count() == 1
    assert ctx["total_pending_count"] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_task_views.py -v`
Expected: FAIL — `_build_task_context` not found

- [ ] **Step 3: Extract task context builder in accounts/views.py**

Add this function before `_fc_dashboard`:

```python
def _build_task_context(user):
    """Build date-grouped task context for dashboard."""
    today = timezone.localdate()
    week_end = today + timedelta(days=(6 - today.weekday()))  # Sunday

    pending = Task.objects.filter(fc=user, status=Task.Status.PENDING).select_related("contact")

    overdue_tasks = pending.filter(due_date__lt=today)
    today_tasks = pending.filter(due_date=today)
    week_tasks = pending.filter(due_date__gt=today, due_date__lte=week_end)
    undated_tasks = pending.filter(due_date__isnull=True)
    total_pending_count = pending.count()

    return {
        "overdue_tasks": overdue_tasks,
        "today_tasks": today_tasks,
        "week_tasks": week_tasks,
        "undated_tasks": undated_tasks,
        "total_pending_count": total_pending_count,
    }
```

Update `_fc_dashboard` to use it — replace the task section (lines ~34-56) with:

```python
    # Section 1: 할 일
    task_ctx = _build_task_context(request.user)
```

And in the context dict passed to `render`, spread `**task_ctx` instead of the old `pending_tasks`/`total_task_count`/`overdue_count` keys.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_task_views.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add accounts/views.py tests/test_task_views.py
git commit -m "feat: date-based task grouping for dashboard"
```

---

### Task 7: Dashboard Template — Date Groups + Inline Expand

**Files:**
- Modify: `accounts/templates/accounts/partials/dashboard/section_tasks.html`
- Modify: `accounts/templates/accounts/partials/dashboard/_task_card.html`

- [ ] **Step 1: Rewrite section_tasks.html**

```html
<section>
  <div class="flex items-center justify-between mb-3">
    <div class="flex items-center gap-2">
      <svg class="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/>
      </svg>
      <h3 class="text-base font-semibold">할 일</h3>
      {% if total_pending_count %}
      <span class="text-xs text-gray-500">{{ total_pending_count }}건</span>
      {% endif %}
    </div>
    <button hx-get="{% url 'contacts:task_create' %}" hx-target="#task-form-slot" hx-swap="innerHTML"
            class="text-primary text-sm font-medium py-2 px-3" aria-label="업무 추가">+ 추가</button>
  </div>

  <div id="task-form-slot"></div>

  <div id="task-list">
    {% if overdue_tasks %}
    <div class="bg-red-50 rounded-2xl border border-red-200 p-3 mb-3">
      <p class="text-xs font-semibold text-red-600 mb-2">밀린 업무 {{ overdue_tasks.count }}건</p>
      <div class="space-y-2">
        {% for task in overdue_tasks %}
        {% include "accounts/partials/dashboard/_task_card.html" %}
        {% endfor %}
      </div>
    </div>
    {% endif %}

    {% if today_tasks %}
    <p class="text-xs font-semibold text-gray-500 mb-2">오늘</p>
    <div class="space-y-2 mb-3">
      {% for task in today_tasks %}
      {% include "accounts/partials/dashboard/_task_card.html" %}
      {% endfor %}
    </div>
    {% endif %}

    {% if week_tasks %}
    <p class="text-xs font-semibold text-gray-500 mb-2">이번 주</p>
    <div class="space-y-2 mb-3">
      {% for task in week_tasks %}
      {% include "accounts/partials/dashboard/_task_card.html" %}
      {% endfor %}
    </div>
    {% endif %}

    {% if undated_tasks %}
    <p class="text-xs font-semibold text-gray-500 mb-2">날짜 미지정</p>
    <div class="space-y-2 mb-3">
      {% for task in undated_tasks %}
      {% include "accounts/partials/dashboard/_task_card.html" %}
      {% endfor %}
    </div>
    {% endif %}

    {% if not overdue_tasks and not today_tasks and not week_tasks and not undated_tasks %}
    <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 text-center">
      <div class="w-10 h-10 mx-auto mb-2 rounded-xl bg-gray-100 flex items-center justify-center">
        <svg class="w-5 h-5 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
        </svg>
      </div>
      <p class="text-sm text-gray-500">할 일이 없습니다</p>
    </div>
    {% endif %}
  </div>
</section>
```

- [ ] **Step 2: Rewrite _task_card.html with inline expand**

```html
<div class="group bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
  <!-- Collapsed row (always visible) -->
  <div class="flex items-center gap-3 p-4 cursor-pointer"
       onclick="var d=this.nextElementSibling;d.classList.toggle('hidden');this.querySelector('[data-chevron]').classList.toggle('rotate-90')">
    <button hx-post="{% url 'contacts:task_complete' task.pk %}" hx-target="closest .group" hx-swap="outerHTML"
            aria-label="완료 처리" title="완료 처리"
            onclick="event.stopPropagation()"
            class="w-7 h-7 rounded-lg border-2 border-gray-300 flex-shrink-0 hover:border-primary hover:bg-primary/10 transition flex items-center justify-center">
      <svg class="w-4 h-4 text-transparent group-hover:text-primary/40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>
      </svg>
    </button>
    <div class="flex-1 min-w-0">
      <p class="text-sm font-medium truncate">{{ task.title }}</p>
      {% if task.contact %}
      <p class="text-xs text-gray-500 mt-0.5">{{ task.contact.name }}{% if task.contact.company_name %} · {{ task.contact.company_name }}{% endif %}</p>
      {% endif %}
    </div>
    {% if task.due_date %}
    <span class="text-xs text-gray-500 flex-shrink-0">{{ task.due_date|date:"n/j" }}</span>
    {% endif %}
    <svg data-chevron class="w-4 h-4 text-gray-400 flex-shrink-0 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
    </svg>
  </div>

  <!-- Expanded detail (hidden by default) -->
  <div class="hidden border-t border-gray-100 px-4 py-3 bg-gray-50/50">
    {% if task.description %}
    <p class="text-sm text-gray-600 leading-relaxed mb-3">{{ task.description }}</p>
    {% endif %}
    <div class="flex items-center gap-2">
      {% if task.contact %}
      <a href="{% url 'contacts:detail' task.contact.pk %}"
         hx-get="{% url 'contacts:detail' task.contact.pk %}" hx-target="#main-content" hx-push-url="true"
         class="text-xs text-primary font-semibold">연락처 보기</a>
      {% endif %}
      <button hx-get="{% url 'contacts:task_edit' task.pk %}" hx-target="closest .group" hx-swap="outerHTML"
              onclick="event.stopPropagation()"
              class="text-xs text-gray-500 hover:text-gray-700" aria-label="수정">수정</button>
      <button hx-post="{% url 'contacts:task_delete' task.pk %}" hx-target="closest .group" hx-swap="outerHTML"
              hx-confirm="이 업무를 삭제하시겠습니까?"
              onclick="event.stopPropagation()"
              class="text-xs text-gray-500 hover:text-red-500" aria-label="삭제">삭제</button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Verify by running dev server and checking dashboard**

Run: `uv run python manage.py runserver 0.0.0.0:8000`
Check: Navigate to http://localhost:8000/ and verify task section renders correctly.

- [ ] **Step 4: Commit**

```bash
git add accounts/templates/accounts/partials/dashboard/section_tasks.html accounts/templates/accounts/partials/dashboard/_task_card.html
git commit -m "feat: date-grouped task UI with inline expand on click"
```

---

### Task 8: Task CRUD Views Update

**Files:**
- Modify: `contacts/views.py:960-1010`
- Modify: `contacts/templates/contacts/partials/task_edit_form.html`

- [ ] **Step 1: Update task_complete to use status**

In `contacts/views.py`, replace `task_complete`:

```python
@login_required
def task_complete(request, pk):
    task = get_object_or_404(Task, pk=pk, fc=request.user)
    task.status = Task.Status.DONE
    task.save(update_fields=["status"])
    return HttpResponse(
        '<div class="flex items-center gap-3 bg-green-50 rounded-2xl border border-green-200 p-4 transition-all duration-500">'
        '<svg class="w-5 h-5 text-green-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
        '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>'
        '<span class="text-sm text-green-700">완료되었습니다</span></div>'
        '<script>setTimeout(function(){var el=document.currentScript.previousElementSibling;'
        'el.style.opacity="0";el.style.maxHeight="0";el.style.padding="0";el.style.margin="0";el.style.overflow="hidden";'
        'setTimeout(function(){el.remove()},300)},1000)</script>'
    )
```

- [ ] **Step 2: Update task_create to use status**

Replace `task_create`:

```python
@login_required
def task_create(request):
    if request.method == "POST":
        contact_id = request.POST.get("contact_id") or None
        Task.objects.create(
            fc=request.user,
            contact_id=contact_id,
            title=request.POST["title"],
            description=request.POST.get("description", ""),
            due_date=request.POST.get("due_date") or None,
            status=Task.Status.PENDING,
        )
        from accounts.views import _build_task_context
        ctx = _build_task_context(request.user)
        return render(request, "accounts/partials/dashboard/section_tasks_list.html", ctx)

    return render(request, "contacts/partials/task_form.html")
```

- [ ] **Step 3: Update task_edit**

Replace `task_edit`:

```python
@login_required
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk, fc=request.user)

    if request.method == "POST":
        task.title = request.POST["title"]
        task.description = request.POST.get("description", "")
        task.due_date = request.POST.get("due_date") or None
        task.save(update_fields=["title", "description", "due_date"])

        from accounts.views import _build_task_context
        ctx = _build_task_context(request.user)
        return render(request, "accounts/partials/dashboard/section_tasks_list.html", ctx)

    return render(request, "contacts/partials/task_edit_form.html", {"task": task})
```

- [ ] **Step 4: Update task_edit_form.html to include description**

```html
<form hx-post="{% url 'contacts:task_edit' task.pk %}" hx-target="#task-list" hx-swap="innerHTML"
      class="bg-white rounded-2xl border border-primary/30 shadow-sm p-4">
  {% csrf_token %}
  <div class="space-y-2">
    <input type="text" name="title" value="{{ task.title }}"
           class="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary" required autofocus>
    <textarea name="description" rows="2" placeholder="상세 메모 (선택)"
              class="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary resize-none">{{ task.description }}</textarea>
    <div class="flex items-center gap-2">
      <input type="date" name="due_date" value="{{ task.due_date|date:'Y-m-d' }}"
             class="flex-1 text-xs border border-gray-200 rounded-lg px-3 py-2">
      <button type="submit" class="px-4 py-2 bg-primary text-white text-xs font-semibold rounded-lg">저장</button>
      <button type="button" onclick="this.closest('form').remove()"
              class="text-gray-500 hover:text-gray-600 p-2" aria-label="취소">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>
    </div>
  </div>
</form>
```

- [ ] **Step 5: Fix all remaining is_completed references**

Search and replace any remaining `is_completed` references in views/templates:

```bash
grep -rn "is_completed" contacts/ accounts/ intelligence/ --include="*.py" --include="*.html"
```

Replace each with the `status` equivalent:
- `is_completed=False` → `status=Task.Status.PENDING` (or `status__in=[Task.Status.PENDING, Task.Status.WAITING]`)
- `is_completed=True` → `status=Task.Status.DONE`

- [ ] **Step 6: Commit**

```bash
git add contacts/views.py contacts/templates/ accounts/
git commit -m "feat: update task CRUD views to use status field"
```

---

### Task 9: Run Data Cleanup + Full Verification

**Files:** No new files — execution of cleanup + manual verification.

- [ ] **Step 1: Run reset_tasks**

```bash
uv run python manage.py reset_tasks
```

Expected: `Deleted N AI tasks, reset N interactions`

- [ ] **Step 2: Run all tests**

```bash
uv run pytest -v
```

Expected: All tests PASS

- [ ] **Step 3: Run ruff**

```bash
uv run ruff check .
uv run ruff format .
```

- [ ] **Step 4: Run migrations check**

```bash
uv run python manage.py makemigrations --check --dry-run
```

Expected: `No changes detected`

- [ ] **Step 5: Browser verification**

Start server: `uv run python manage.py runserver 0.0.0.0:8000`

Verify:
1. Dashboard shows "할 일" section (empty after reset, or with manual tasks)
2. "+ 추가" creates a new task with title/description/due_date
3. Task card click expands to show description
4. "연락처 보기" navigates to contact detail
5. Checkbox completes with green animation
6. Delete works with confirmation
7. Edit opens inline form with description field

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: cleanup and verify task UX redesign"
```
