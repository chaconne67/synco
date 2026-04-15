# P14 Voice Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing Whisper voice search into a conversational voice agent that handles headhunting tasks via voice/text across all screens, plus meeting recording upload with LLM-powered insight extraction.

**Architecture:** Django views serve a `/voice/` URL namespace with 9 endpoints. A 7-service backend pipeline (transcriber, intent_parser, entity_resolver, action_executor, context_resolver, conversation, meeting_analyzer) processes voice input through STT -> intent parsing -> entity resolution -> preview -> confirm flow. Frontend is a floating button + modal on every page using MediaRecorder API and HTMX. Meeting recordings use async processing with status polling.

**Tech Stack:** Django 5.2, HTMX, Tailwind CSS, OpenAI Whisper (gpt-4o-transcribe), Gemini API (google-genai), MediaRecorder API, Django sessions.

---

## File Structure

### New Files to Create

| File | Responsibility |
|------|---------------|
| `projects/services/voice/__init__.py` | Package init |
| `projects/services/voice/transcriber.py` | Whisper STT with mode-based prompt/filter switching (command/meeting/search) |
| `projects/services/voice/intent_parser.py` | Gemini API intent parsing + entity extraction |
| `projects/services/voice/entity_resolver.py` | Name -> UUID resolution with disambiguation |
| `projects/services/voice/action_executor.py` | Intent-specific preview + confirm (delegates to existing service layer) |
| `projects/services/voice/context_resolver.py` | Screen context -> parsing hints + server-side permission check |
| `projects/services/voice/conversation.py` | Multi-turn session state management |
| `projects/services/voice/meeting_analyzer.py` | Meeting recording async pipeline (STT + LLM analysis) |
| `projects/urls_voice.py` | Voice URL patterns (9 endpoints) |
| `projects/views_voice.py` | Voice endpoint view functions |
| `projects/templates/projects/partials/voice_modal.html` | Conversation modal template |
| `projects/templates/projects/partials/voice_button.html` | Floating mic button template |
| `projects/templates/projects/partials/meeting_upload.html` | Meeting upload form template |
| `projects/templates/projects/partials/meeting_status.html` | Meeting analysis status/results template |
| `static/js/voice-agent.js` | MediaRecorder, conversation UI, meeting upload |
| `projects/management/commands/process_meetings.py` | Management command for async meeting processing |
| `tests/test_p14_voice_transcriber.py` | Transcriber service tests |
| `tests/test_p14_voice_intent_parser.py` | Intent parser tests |
| `tests/test_p14_voice_entity_resolver.py` | Entity resolver tests |
| `tests/test_p14_voice_action_executor.py` | Action executor tests |
| `tests/test_p14_voice_context_resolver.py` | Context resolver tests |
| `tests/test_p14_voice_conversation.py` | Conversation session tests |
| `tests/test_p14_voice_meeting.py` | Meeting model + analyzer tests |
| `tests/test_p14_voice_views.py` | Voice endpoint integration tests |

### Files to Modify

| File | Change |
|------|--------|
| `main/urls.py` | Add `path("voice/", include("projects.urls_voice"))` |
| `projects/models.py` | Add `MeetingRecord` model |
| `templates/common/base.html` | Replace chatbot_fab.html include with voice_button.html |

---

### Task 1: MeetingRecord Model + Migration

**Files:**
- Modify: `projects/models.py`
- Create: `tests/test_p14_voice_meeting.py`

- [ ] **Step 1: Write the failing test for MeetingRecord model**

```python
# tests/test_p14_voice_meeting.py
"""P14: MeetingRecord model tests."""
import pytest

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import MeetingRecord, Project


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="voice_tester", password="test1234")
    Membership.objects.create(user=u, organization=org)
    return u


@pytest.fixture
def client_obj(db, org):
    return Client.objects.create(name="Test Client", organization=org)


@pytest.fixture
def project(db, org, client_obj, user):
    return Project.objects.create(
        client=client_obj,
        organization=org,
        title="Voice Agent Test Project",
        created_by=user,
    )


@pytest.fixture
def candidate(db, org):
    return Candidate.objects.create(name="홍길동", owned_by=org)


def test_meeting_record_creation(project, candidate, user):
    record = MeetingRecord.objects.create(
        project=project,
        candidate=candidate,
        audio_file="meetings/audio/test.webm",
        created_by=user,
    )
    assert record.status == MeetingRecord.Status.UPLOADED
    assert record.transcript == ""
    assert record.analysis_json == {}
    assert record.edited_json == {}
    assert record.error_message == ""
    assert record.applied_at is None
    assert record.applied_by is None


def test_meeting_record_status_transitions(project, candidate, user):
    record = MeetingRecord.objects.create(
        project=project,
        candidate=candidate,
        audio_file="meetings/audio/test.webm",
        created_by=user,
    )
    # Simulate status progression
    for status in ["transcribing", "analyzing", "ready"]:
        record.status = status
        record.save()
        record.refresh_from_db()
        assert record.status == status
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p14_voice_meeting.py -v`
Expected: FAIL with `ImportError: cannot import name 'MeetingRecord' from 'projects.models'`

- [ ] **Step 3: Add MeetingRecord model to projects/models.py**

Add at end of `projects/models.py`, before any existing code that doesn't define models:

```python
class MeetingRecord(BaseModel):
    """미팅 녹음 분석 레코드."""

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "업로드됨"
        TRANSCRIBING = "transcribing", "전사 중"
        ANALYZING = "analyzing", "분석 중"
        READY = "ready", "분석 완료"
        APPLIED = "applied", "반영 완료"
        FAILED = "failed", "실패"

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="meeting_records",
    )
    candidate = models.ForeignKey(
        "candidates.Candidate",
        on_delete=models.CASCADE,
        related_name="meeting_records",
    )
    audio_file = models.FileField(upload_to="meetings/audio/")
    transcript = models.TextField(blank=True)
    analysis_json = models.JSONField(default=dict, blank=True)
    edited_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
    )
    error_message = models.TextField(blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applied_meeting_records",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_meeting_records",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Meeting: {self.candidate} ({self.status})"
```

- [ ] **Step 4: Generate and apply migration**

Run: `uv run python manage.py makemigrations projects && uv run python manage.py migrate`
Expected: Migration created and applied successfully.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_p14_voice_meeting.py -v`
Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add projects/models.py projects/migrations/ tests/test_p14_voice_meeting.py
git commit -m "feat(p14): add MeetingRecord model for voice meeting analysis"
```

---

### Task 2: Transcriber Service (mode-based STT)

**Files:**
- Create: `projects/services/voice/__init__.py`
- Create: `projects/services/voice/transcriber.py`
- Create: `tests/test_p14_voice_transcriber.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_p14_voice_transcriber.py
"""P14: Voice transcriber service tests."""
import io
from unittest.mock import MagicMock, patch

import pytest

from projects.services.voice.transcriber import transcribe, TranscribeMode


@patch("projects.services.voice.transcriber._get_openai_client")
def test_transcribe_command_mode(mock_client_fn):
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = MagicMock(
        text="홍길동 전화했는데 관심 있대"
    )
    mock_client_fn.return_value = mock_client

    audio = io.BytesIO(b"fake audio")
    audio.name = "voice.webm"
    result = transcribe(audio, mode=TranscribeMode.COMMAND)

    assert result == "홍길동 전화했는데 관심 있대"
    call_kwargs = mock_client.audio.transcriptions.create.call_args
    # Prompt should contain business terms, not search terms
    assert "헤드헌팅 업무" in call_kwargs.kwargs.get("prompt", call_kwargs[1].get("prompt", ""))


@patch("projects.services.voice.transcriber._get_openai_client")
def test_transcribe_meeting_mode(mock_client_fn):
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = MagicMock(
        text="현재 연봉은 8천만원이고 희망 연봉은 1억입니다"
    )
    mock_client_fn.return_value = mock_client

    audio = io.BytesIO(b"fake audio")
    audio.name = "meeting.webm"
    result = transcribe(audio, mode=TranscribeMode.MEETING)

    assert result == "현재 연봉은 8천만원이고 희망 연봉은 1억입니다"
    call_kwargs = mock_client.audio.transcriptions.create.call_args
    assert "미팅 녹음" in call_kwargs.kwargs.get("prompt", call_kwargs[1].get("prompt", ""))


@patch("projects.services.voice.transcriber._get_openai_client")
def test_transcribe_hallucination_filtered(mock_client_fn):
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = MagicMock(
        text="시청해 주셔서 감사합니다"
    )
    mock_client_fn.return_value = mock_client

    audio = io.BytesIO(b"fake audio")
    audio.name = "voice.webm"
    result = transcribe(audio, mode=TranscribeMode.COMMAND)

    assert result == ""


@patch("projects.services.voice.transcriber._get_openai_client")
def test_transcribe_empty_audio(mock_client_fn):
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = MagicMock(text="")
    mock_client_fn.return_value = mock_client

    audio = io.BytesIO(b"fake audio")
    audio.name = "voice.webm"
    result = transcribe(audio, mode=TranscribeMode.COMMAND)

    assert result == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p14_voice_transcriber.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'projects.services.voice'`

- [ ] **Step 3: Create the transcriber service**

```python
# projects/services/voice/__init__.py
```

```python
# projects/services/voice/transcriber.py
"""Voice transcriber with mode-based prompt/filter switching."""

import enum
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

_client = None


class TranscribeMode(str, enum.Enum):
    COMMAND = "command"
    MEETING = "meeting"


# Prompts per mode
PROMPTS = {
    TranscribeMode.COMMAND: (
        "헤드헌팅 업무 음성 명령입니다. "
        "프로젝트, 컨택, 면접, 오퍼, 추천, 후보자, 이력서, 연봉, 채용, 헤드헌터. "
        "전화, 문자, 카톡, 이메일, LinkedIn. "
        "관심, 거절, 미응답, 응답, 보류, 예정."
    ),
    TranscribeMode.MEETING: (
        "헤드헌팅 미팅 녹음입니다. "
        "후보자 면담, 연봉 협상, 경력 상담, 이직 의향, 포지션, 채용 프로세스. "
        "현재 연봉, 희망 연봉, 이직 가능 시기, 경력 하이라이트, 우려 사항."
    ),
}

# Timeouts per mode (seconds)
TIMEOUTS = {
    TranscribeMode.COMMAND: 30.0,
    TranscribeMode.MEETING: 300.0,
}

# Hallucination patterns common across modes
COMMON_HALLUCINATIONS = [
    "시청해 주셔서 감사합니다",
    "시청해주셔서 감사합니다",
    "구독과 좋아요",
    "구독 부탁드립니다",
    "자막 제공",
    "자막을 제공",
    "다음 영상에서 만나요",
    "영상이 도움이 되셨다면",
    "좋아요와 구독",
    "MBC 뉴스",
    "KBS 뉴스",
    "SBS 뉴스",
]

# Additional hallucinations per mode
MODE_HALLUCINATIONS = {
    TranscribeMode.COMMAND: [
        "헤드헌팅 업무 음성 명령입니다",
    ],
    TranscribeMode.MEETING: [
        "헤드헌팅 미팅 녹음입니다",
    ],
}


def _get_openai_client():
    global _client
    if _client is None:
        from openai import OpenAI

        api_key = settings.OPENAI_API_KEY
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY가 설정되지 않았습니다. 환경변수를 확인해주세요."
            )
        _client = OpenAI(api_key=api_key, timeout=httpx.Timeout(300.0))
    return _client


def _is_hallucination(text: str, mode: TranscribeMode) -> bool:
    if not text:
        return True
    text_lower = text.strip().lower()
    all_patterns = COMMON_HALLUCINATIONS + MODE_HALLUCINATIONS.get(mode, [])
    if any(p in text_lower for p in all_patterns):
        return True
    prompt_lower = PROMPTS[mode].lower()
    if len(text_lower) > 20 and text_lower in prompt_lower:
        return True
    return False


def transcribe(audio_file, *, mode: TranscribeMode = TranscribeMode.COMMAND) -> str:
    """Transcribe audio file using Whisper with mode-specific prompt/filter.

    Args:
        audio_file: File-like object with .name attribute.
        mode: TranscribeMode.COMMAND or TranscribeMode.MEETING.

    Returns:
        Transcribed text, or empty string if no speech detected.

    Raises:
        RuntimeError on API failure.
    """
    try:
        client = _get_openai_client()
        file_tuple = (
            getattr(audio_file, "name", "voice.webm"),
            audio_file.read(),
            getattr(audio_file, "content_type", "audio/webm"),
        )
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",
            file=file_tuple,
            language="ko",
            prompt=PROMPTS[mode],
        )
        text = transcript.text.strip()

        if not text:
            return ""

        if _is_hallucination(text, mode):
            logger.info("Voice agent hallucination filtered (%s): %s", mode.value, text)
            return ""

        return text
    except Exception as e:
        logger.exception("Voice transcription failed (mode=%s)", mode.value)
        raise RuntimeError(f"음성 인식에 실패했습니다: {e}") from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p14_voice_transcriber.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/voice/ tests/test_p14_voice_transcriber.py
git commit -m "feat(p14): add voice transcriber service with mode-based prompts"
```

---

### Task 3: Context Resolver Service

**Files:**
- Create: `projects/services/voice/context_resolver.py`
- Create: `tests/test_p14_voice_context_resolver.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_p14_voice_context_resolver.py
"""P14: Voice context resolver tests."""
import pytest

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Project
from projects.services.voice.context_resolver import resolve_context


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="ctx_tester", password="test1234")
    Membership.objects.create(user=u, organization=org)
    return u


@pytest.fixture
def client_obj(db, org):
    return Client.objects.create(name="Test Client", organization=org)


@pytest.fixture
def project(db, org, client_obj, user):
    return Project.objects.create(
        client=client_obj,
        organization=org,
        title="Context Test Project",
        created_by=user,
    )


def test_resolve_context_dashboard(user, org):
    ctx = resolve_context(
        user=user,
        organization=org,
        context_hint={"page": "dashboard"},
    )
    assert ctx["page"] == "dashboard"
    assert ctx["project_id"] is None
    assert ctx["scope"] == "global"


def test_resolve_context_project_detail(user, org, project):
    ctx = resolve_context(
        user=user,
        organization=org,
        context_hint={"page": "project_detail", "project_id": str(project.pk)},
    )
    assert ctx["page"] == "project_detail"
    assert ctx["project_id"] == project.pk
    assert ctx["scope"] == "project"
    assert ctx["project_title"] == project.title


def test_resolve_context_invalid_project(user, org):
    """Project not in user's org -> project_id is None."""
    ctx = resolve_context(
        user=user,
        organization=org,
        context_hint={"page": "project_detail", "project_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert ctx["project_id"] is None
    assert ctx["scope"] == "global"


def test_resolve_context_missing_hint(user, org):
    ctx = resolve_context(user=user, organization=org, context_hint={})
    assert ctx["page"] == "unknown"
    assert ctx["scope"] == "global"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p14_voice_context_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement context resolver**

```python
# projects/services/voice/context_resolver.py
"""Screen context -> parsing hints with server-side permission check."""

from __future__ import annotations

import logging
import uuid as uuid_mod
from typing import Any

from accounts.models import Organization, User
from projects.models import Project

logger = logging.getLogger(__name__)

# Pages that imply project scope
PROJECT_PAGES = {
    "project_detail",
    "project_tab_search",
    "project_tab_contacts",
    "project_tab_submissions",
    "project_tab_interviews",
    "project_tab_offers",
}


def resolve_context(
    *,
    user: User,
    organization: Organization,
    context_hint: dict[str, Any],
) -> dict[str, Any]:
    """Resolve client context hint to verified server context.

    The client sends page name and optional project_id via data-voice-context.
    This function verifies the project belongs to the user's organization and
    enriches the context with server-side data.

    Returns dict with keys: page, project_id, project_title, scope, tab.
    """
    page = context_hint.get("page", "unknown")
    raw_project_id = context_hint.get("project_id")
    tab = context_hint.get("tab", "")

    project_id = None
    project_title = ""
    scope = "global"

    if raw_project_id and page in PROJECT_PAGES:
        try:
            pid = uuid_mod.UUID(str(raw_project_id))
            project = Project.objects.filter(
                pk=pid,
                organization=organization,
            ).first()
            if project:
                project_id = project.pk
                project_title = project.title
                scope = "project"
        except (ValueError, AttributeError):
            logger.warning("Invalid project_id in voice context: %s", raw_project_id)

    return {
        "page": page,
        "project_id": project_id,
        "project_title": project_title,
        "scope": scope,
        "tab": tab,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p14_voice_context_resolver.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/voice/context_resolver.py tests/test_p14_voice_context_resolver.py
git commit -m "feat(p14): add voice context resolver with server-side permission check"
```

---

### Task 4: Intent Parser Service

**Files:**
- Create: `projects/services/voice/intent_parser.py`
- Create: `tests/test_p14_voice_intent_parser.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_p14_voice_intent_parser.py
"""P14: Voice intent parser tests."""
from unittest.mock import MagicMock, patch

import pytest

from projects.services.voice.intent_parser import parse_intent, IntentResult


@patch("projects.services.voice.intent_parser._get_gemini_client")
def test_parse_contact_record_intent(mock_client_fn):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"intent": "contact_record", "entities": {"candidate_name": "홍길동", "channel": "전화", "result": "관심"}, "confidence": 0.95}'
    mock_client.models.generate_content.return_value = mock_response
    mock_client_fn.return_value = mock_client

    result = parse_intent(
        text="홍길동 전화했는데 관심 있대",
        context={"page": "project_detail", "project_id": "some-uuid", "scope": "project"},
    )

    assert isinstance(result, IntentResult)
    assert result.intent == "contact_record"
    assert result.entities["candidate_name"] == "홍길동"
    assert result.entities["channel"] == "전화"
    assert result.confidence >= 0.9


@patch("projects.services.voice.intent_parser._get_gemini_client")
def test_parse_search_intent(mock_client_fn):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"intent": "search_candidate", "entities": {"keywords": "삼성전자 출신 개발자"}, "confidence": 0.92}'
    mock_client.models.generate_content.return_value = mock_response
    mock_client_fn.return_value = mock_client

    result = parse_intent(
        text="삼성전자 출신 개발자 찾아줘",
        context={"page": "dashboard", "scope": "global"},
    )

    assert result.intent == "search_candidate"
    assert "삼성전자" in result.entities["keywords"]


@patch("projects.services.voice.intent_parser._get_gemini_client")
def test_parse_navigate_intent(mock_client_fn):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"intent": "navigate", "entities": {"target_page": "projects"}, "confidence": 0.88}'
    mock_client.models.generate_content.return_value = mock_response
    mock_client_fn.return_value = mock_client

    result = parse_intent(
        text="프로젝트 목록으로 가줘",
        context={"page": "dashboard", "scope": "global"},
    )

    assert result.intent == "navigate"
    assert result.entities["target_page"] == "projects"


@patch("projects.services.voice.intent_parser._get_gemini_client")
def test_parse_unknown_intent(mock_client_fn):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"intent": "unknown", "entities": {}, "confidence": 0.3}'
    mock_client.models.generate_content.return_value = mock_response
    mock_client_fn.return_value = mock_client

    result = parse_intent(
        text="오늘 날씨 어때",
        context={"page": "dashboard", "scope": "global"},
    )

    assert result.intent == "unknown"
    assert result.confidence < 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p14_voice_intent_parser.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement intent parser**

```python
# projects/services/voice/intent_parser.py
"""Gemini-based intent parsing + entity extraction."""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any

from django.conf import settings

from data_extraction.services.extraction.sanitizers import parse_llm_json

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-preview-05-20"

VALID_INTENTS = {
    "project_create",
    "contact_record",
    "contact_reserve",
    "submission_create",
    "interview_schedule",
    "offer_create",
    "status_query",
    "todo_query",
    "search_candidate",
    "navigate",
    "meeting_navigate",
    "unknown",
}

INTENT_SYSTEM_PROMPT = """\
당신은 헤드헌팅 플랫폼의 음성 명령 의도 파서입니다.
사용자의 음성 입력 텍스트를 분석하여 의도(intent)와 엔티티를 추출합니다.

가능한 intent 목록:
- project_create: 프로젝트 등록. 엔티티: client(str), title(str)
- contact_record: 컨택 결과 기록. 엔티티: candidate_name(str), channel(전화|문자|카톡|이메일|LinkedIn), contacted_at(ISO datetime, 없으면 null), result(응답|미응답|거절|관심|보류), notes(str, optional)
- contact_reserve: 컨택 예정 등록. 엔티티: candidate_names(list[str])
- submission_create: 추천 서류 생성. 엔티티: candidate_name(str), template(str, optional)
- interview_schedule: 면접 일정 등록. 엔티티: candidate_name(str), scheduled_at(ISO datetime), type(대면|화상|전화), location(str, optional)
- offer_create: 오퍼 등록. 엔티티: candidate_name(str), salary(str), position_title(str, optional)
- status_query: 현황 조회. 엔티티: project_name(str, optional)
- todo_query: 오늘 할 일. 엔티티: 없음
- search_candidate: 후보자 검색. 엔티티: keywords(str)
- navigate: 화면 이동. 엔티티: target_page(str)
- meeting_navigate: 미팅 녹음 업로드 화면 열기. 엔티티: candidate_name(str, optional)

규칙:
1. 확실하지 않으면 intent를 "unknown"으로 설정
2. 엔티티에서 이름은 원래 발화 그대로 유지 (UUID 변환하지 않음)
3. channel은 정확히 매칭되는 값 사용 (전화/문자/카톡/이메일/LinkedIn)
4. contacted_at이 명시되지 않으면 null
5. confidence는 0.0~1.0 사이 값

반드시 아래 JSON 형식으로만 응답:
{"intent": "string", "entities": {}, "confidence": 0.0}
"""

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


@dataclasses.dataclass
class IntentResult:
    intent: str
    entities: dict[str, Any]
    confidence: float
    missing_fields: list[str] = dataclasses.field(default_factory=list)


# Required entities per intent (for missing field detection)
REQUIRED_ENTITIES: dict[str, list[str]] = {
    "project_create": ["client", "title"],
    "contact_record": ["candidate_name", "channel", "result"],
    "contact_reserve": ["candidate_names"],
    "submission_create": ["candidate_name"],
    "interview_schedule": ["candidate_name", "scheduled_at", "type"],
    "offer_create": ["candidate_name", "salary"],
    "search_candidate": ["keywords"],
    "navigate": ["target_page"],
}


def parse_intent(
    text: str,
    context: dict[str, Any],
) -> IntentResult:
    """Parse user text into intent + entities using Gemini.

    Args:
        text: Transcribed user speech.
        context: Resolved context from context_resolver.

    Returns:
        IntentResult with intent, entities, confidence, missing_fields.
    """
    user_prompt = f"현재 화면: {context.get('page', 'unknown')}\n"
    if context.get("project_title"):
        user_prompt += f"현재 프로젝트: {context['project_title']}\n"
    user_prompt += f"\n사용자 발화: {text}"

    try:
        client = _get_gemini_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                {"role": "user", "parts": [{"text": INTENT_SYSTEM_PROMPT + "\n\n" + user_prompt}]},
            ],
        )
        raw = response.text.strip()
        parsed = parse_llm_json(raw)

        intent = parsed.get("intent", "unknown")
        if intent not in VALID_INTENTS:
            intent = "unknown"

        entities = parsed.get("entities", {})
        confidence = float(parsed.get("confidence", 0.0))

        # Detect missing required fields
        required = REQUIRED_ENTITIES.get(intent, [])
        missing = [f for f in required if not entities.get(f)]

        return IntentResult(
            intent=intent,
            entities=entities,
            confidence=confidence,
            missing_fields=missing,
        )
    except Exception as e:
        logger.exception("Intent parsing failed for: %s", text)
        return IntentResult(intent="unknown", entities={}, confidence=0.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p14_voice_intent_parser.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/voice/intent_parser.py tests/test_p14_voice_intent_parser.py
git commit -m "feat(p14): add Gemini-based voice intent parser with entity extraction"
```

---

### Task 5: Entity Resolver Service

**Files:**
- Create: `projects/services/voice/entity_resolver.py`
- Create: `tests/test_p14_voice_entity_resolver.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_p14_voice_entity_resolver.py
"""P14: Voice entity resolver tests."""
import pytest

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Contact, Project, Submission
from projects.services.voice.entity_resolver import (
    resolve_candidate,
    resolve_submission,
    CandidateResolution,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="er_tester", password="test1234")
    Membership.objects.create(user=u, organization=org)
    return u


@pytest.fixture
def client_obj(db, org):
    return Client.objects.create(name="Test Client", organization=org)


@pytest.fixture
def project(db, org, client_obj, user):
    return Project.objects.create(
        client=client_obj, organization=org, title="ER Project", created_by=user,
    )


@pytest.fixture
def candidate_hong(db, org):
    return Candidate.objects.create(name="홍길동", owned_by=org)


@pytest.fixture
def candidate_hong2(db, org):
    return Candidate.objects.create(name="홍길동", owned_by=org)


@pytest.fixture
def candidate_kim(db, org):
    return Candidate.objects.create(name="김영희", owned_by=org)


def test_resolve_single_match(org, project, candidate_kim):
    result = resolve_candidate(
        name="김영희",
        organization=org,
        project=project,
    )
    assert result.status == "resolved"
    assert result.candidate_id == candidate_kim.pk
    assert len(result.candidates) == 1


def test_resolve_multiple_matches(org, project, candidate_hong, candidate_hong2):
    result = resolve_candidate(
        name="홍길동",
        organization=org,
        project=project,
    )
    assert result.status == "ambiguous"
    assert result.candidate_id is None
    assert len(result.candidates) == 2


def test_resolve_no_match(org, project):
    result = resolve_candidate(
        name="존재하지않는사람",
        organization=org,
        project=project,
    )
    assert result.status == "not_found"
    assert result.candidate_id is None
    assert len(result.candidates) == 0


def test_resolve_submission_auto(org, project, candidate_kim, user):
    contact = Contact.objects.create(
        project=project, candidate=candidate_kim, consultant=user,
        result=Contact.Result.INTERESTED, channel="전화",
    )
    sub = Submission.objects.create(
        project=project, candidate=candidate_kim, consultant=user,
        status=Submission.Status.PASSED,
    )
    result = resolve_submission(
        candidate_id=candidate_kim.pk,
        project=project,
    )
    assert result["status"] == "resolved"
    assert result["submission_id"] == sub.pk


def test_resolve_submission_no_eligible(org, project, candidate_kim, user):
    result = resolve_submission(
        candidate_id=candidate_kim.pk,
        project=project,
    )
    assert result["status"] == "not_found"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p14_voice_entity_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement entity resolver**

```python
# projects/services/voice/entity_resolver.py
"""Name -> UUID entity resolution with disambiguation."""

from __future__ import annotations

import dataclasses
import logging
import uuid as uuid_mod
from typing import Any

from accounts.models import Organization
from candidates.models import Candidate
from projects.models import Contact, Project, Submission

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class CandidateResolution:
    status: str  # "resolved" | "ambiguous" | "not_found"
    candidate_id: uuid_mod.UUID | None
    candidates: list[dict[str, Any]]  # [{id, name, summary}]


def resolve_candidate(
    *,
    name: str,
    organization: Organization,
    project: Project | None = None,
) -> CandidateResolution:
    """Resolve candidate name to UUID within organization scope.

    Search strategy:
    1. Exact name match within organization
    2. If project context exists, prioritize candidates with contacts in this project
    """
    matches = Candidate.objects.filter(
        name__icontains=name.strip(),
        owned_by=organization,
    ).order_by("name", "-created_at")[:20]

    candidate_list = [
        {"id": c.pk, "name": c.name, "email": c.email, "phone": c.phone}
        for c in matches
    ]

    if len(candidate_list) == 0:
        return CandidateResolution(status="not_found", candidate_id=None, candidates=[])

    if len(candidate_list) == 1:
        return CandidateResolution(
            status="resolved",
            candidate_id=candidate_list[0]["id"],
            candidates=candidate_list,
        )

    # Multiple matches: try to narrow by project context
    if project:
        project_candidate_ids = set(
            Contact.objects.filter(project=project)
            .values_list("candidate_id", flat=True)
        )
        in_project = [c for c in candidate_list if c["id"] in project_candidate_ids]
        if len(in_project) == 1:
            return CandidateResolution(
                status="resolved",
                candidate_id=in_project[0]["id"],
                candidates=candidate_list,
            )

    return CandidateResolution(
        status="ambiguous",
        candidate_id=None,
        candidates=candidate_list,
    )


def resolve_submission(
    *,
    candidate_id: uuid_mod.UUID,
    project: Project,
) -> dict[str, Any]:
    """Auto-resolve eligible submission for candidate in project.

    Returns:
        {"status": "resolved"|"ambiguous"|"not_found", "submission_id": uuid|None,
         "submissions": list}
    """
    eligible = Submission.objects.filter(
        project=project,
        candidate_id=candidate_id,
        status=Submission.Status.PASSED,
    ).order_by("-created_at")

    subs = [{"id": s.pk, "status": s.status, "created_at": str(s.created_at)} for s in eligible]

    if len(subs) == 0:
        return {"status": "not_found", "submission_id": None, "submissions": []}
    if len(subs) == 1:
        return {"status": "resolved", "submission_id": subs[0]["id"], "submissions": subs}
    return {"status": "ambiguous", "submission_id": None, "submissions": subs}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p14_voice_entity_resolver.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/voice/entity_resolver.py tests/test_p14_voice_entity_resolver.py
git commit -m "feat(p14): add voice entity resolver for candidate/submission disambiguation"
```

---

### Task 6: Conversation Session Manager

**Files:**
- Create: `projects/services/voice/conversation.py`
- Create: `tests/test_p14_voice_conversation.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_p14_voice_conversation.py
"""P14: Voice conversation session tests."""
import uuid

import pytest

from projects.services.voice.conversation import (
    ConversationManager,
    SESSION_KEY,
)


class FakeSession(dict):
    """Mimics Django session interface."""
    modified = False

    def save(self):
        self.modified = True


@pytest.fixture
def session():
    return FakeSession()


def test_new_conversation(session):
    mgr = ConversationManager(session)
    conv = mgr.get_or_create()

    assert conv["id"] is not None
    assert conv["turns"] == []
    assert conv["pending_intent"] is None
    assert conv["collected_entities"] == {}
    assert conv["missing_fields"] == []
    assert conv["preview_token"] is None
    assert SESSION_KEY in session


def test_add_turn(session):
    mgr = ConversationManager(session)
    mgr.get_or_create()
    mgr.add_turn(role="user", text="홍길동 전화했어")
    mgr.add_turn(role="assistant", text="컨택 결과를 기록할까요?")

    conv = mgr.get_or_create()
    assert len(conv["turns"]) == 2
    assert conv["turns"][0]["role"] == "user"
    assert conv["turns"][1]["role"] == "assistant"


def test_set_pending_intent(session):
    mgr = ConversationManager(session)
    mgr.get_or_create()
    mgr.set_pending(
        intent="contact_record",
        entities={"candidate": "uuid-1", "channel": "전화"},
        missing=["result"],
    )

    conv = mgr.get_or_create()
    assert conv["pending_intent"] == "contact_record"
    assert conv["collected_entities"]["channel"] == "전화"
    assert conv["missing_fields"] == ["result"]


def test_generate_preview_token(session):
    mgr = ConversationManager(session)
    mgr.get_or_create()
    token = mgr.generate_preview_token()

    conv = mgr.get_or_create()
    assert conv["preview_token"] == token
    assert uuid.UUID(token)  # Valid UUID


def test_consume_preview_token(session):
    mgr = ConversationManager(session)
    mgr.get_or_create()
    token = mgr.generate_preview_token()

    assert mgr.consume_preview_token(token) is True
    assert mgr.consume_preview_token(token) is False  # Already consumed
    conv = mgr.get_or_create()
    assert conv["preview_token"] is None


def test_reset(session):
    mgr = ConversationManager(session)
    mgr.get_or_create()
    mgr.add_turn(role="user", text="test")
    mgr.reset()

    assert SESSION_KEY not in session
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p14_voice_conversation.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement conversation manager**

```python
# projects/services/voice/conversation.py
"""Multi-turn conversation session manager."""

from __future__ import annotations

import uuid
from typing import Any

SESSION_KEY = "voice_conversation"
MAX_TURNS = 50  # Prevent session bloat


class ConversationManager:
    """Manages voice conversation state in Django session."""

    def __init__(self, session: Any) -> None:
        self._session = session

    def get_or_create(self) -> dict[str, Any]:
        """Get existing conversation or create a new one."""
        if SESSION_KEY not in self._session:
            self._session[SESSION_KEY] = {
                "id": str(uuid.uuid4()),
                "turns": [],
                "pending_intent": None,
                "collected_entities": {},
                "missing_fields": [],
                "preview_token": None,
            }
        return self._session[SESSION_KEY]

    def add_turn(self, *, role: str, text: str) -> None:
        """Add a conversation turn."""
        conv = self.get_or_create()
        conv["turns"].append({"role": role, "text": text})
        # Trim old turns to prevent session bloat
        if len(conv["turns"]) > MAX_TURNS:
            conv["turns"] = conv["turns"][-MAX_TURNS:]
        self._session.modified = True

    def set_pending(
        self,
        *,
        intent: str,
        entities: dict[str, Any],
        missing: list[str],
    ) -> None:
        """Set pending intent with collected entities and missing fields."""
        conv = self.get_or_create()
        conv["pending_intent"] = intent
        conv["collected_entities"].update(entities)
        conv["missing_fields"] = missing
        self._session.modified = True

    def generate_preview_token(self) -> str:
        """Generate idempotent token for confirm step."""
        conv = self.get_or_create()
        token = str(uuid.uuid4())
        conv["preview_token"] = token
        self._session.modified = True
        return token

    def consume_preview_token(self, token: str) -> bool:
        """Consume preview token. Returns True if valid, False if already used."""
        conv = self.get_or_create()
        if conv["preview_token"] == token:
            conv["preview_token"] = None
            self._session.modified = True
            return True
        return False

    def reset(self) -> None:
        """Clear conversation state."""
        if SESSION_KEY in self._session:
            del self._session[SESSION_KEY]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p14_voice_conversation.py -v`
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/voice/conversation.py tests/test_p14_voice_conversation.py
git commit -m "feat(p14): add voice conversation session manager"
```

---

### Task 7: Action Executor Service (Preview + Confirm)

**Files:**
- Create: `projects/services/voice/action_executor.py`
- Create: `tests/test_p14_voice_action_executor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_p14_voice_action_executor.py
"""P14: Voice action executor tests."""
import pytest
from django.utils import timezone

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Contact, Project, Submission
from projects.services.voice.action_executor import preview_action, confirm_action


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="ae_tester", password="test1234")
    Membership.objects.create(user=u, organization=org)
    return u


@pytest.fixture
def client_obj(db, org):
    return Client.objects.create(name="레이언스", organization=org)


@pytest.fixture
def project(db, org, client_obj, user):
    return Project.objects.create(
        client=client_obj, organization=org, title="AE Test", created_by=user,
    )


@pytest.fixture
def candidate(db, org):
    return Candidate.objects.create(name="홍길동", owned_by=org)


def test_preview_contact_record(project, candidate, user, org):
    result = preview_action(
        intent="contact_record",
        entities={
            "candidate_id": str(candidate.pk),
            "channel": "전화",
            "result": "관심",
            "contacted_at": timezone.now().isoformat(),
        },
        project=project,
        user=user,
        organization=org,
    )
    assert result["ok"] is True
    assert result["intent"] == "contact_record"
    assert "홍길동" in result["summary"]
    # No DB change in preview
    assert Contact.objects.filter(project=project, candidate=candidate).count() == 0


def test_confirm_contact_record(project, candidate, user, org):
    now = timezone.now()
    entities = {
        "candidate_id": str(candidate.pk),
        "channel": "전화",
        "result": "관심",
        "contacted_at": now.isoformat(),
    }
    result = confirm_action(
        intent="contact_record",
        entities=entities,
        project=project,
        user=user,
        organization=org,
    )
    assert result["ok"] is True
    assert Contact.objects.filter(project=project, candidate=candidate).count() == 1
    contact = Contact.objects.get(project=project, candidate=candidate)
    assert contact.result == Contact.Result.INTERESTED
    assert contact.channel == Contact.Channel.PHONE


def test_preview_status_query(project, user, org):
    result = preview_action(
        intent="status_query",
        entities={"project_name": project.title},
        project=project,
        user=user,
        organization=org,
    )
    assert result["ok"] is True
    assert result["intent"] == "status_query"


def test_preview_navigate(user, org):
    result = preview_action(
        intent="navigate",
        entities={"target_page": "projects"},
        project=None,
        user=user,
        organization=org,
    )
    assert result["ok"] is True
    assert result["url"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p14_voice_action_executor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement action executor**

```python
# projects/services/voice/action_executor.py
"""Intent-specific preview (dry-run) + confirm (DB commit)."""

from __future__ import annotations

import logging
import uuid as uuid_mod
from datetime import datetime
from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import Organization, User
from candidates.models import Candidate
from projects.models import (
    Contact,
    Interview,
    Offer,
    Project,
    Submission,
    SubmissionTemplate,
)
from projects.services.contact import check_duplicate, reserve_candidates
from projects.services.dashboard import get_today_actions
from projects.services.lifecycle import (
    is_submission_offer_eligible,
    maybe_advance_to_interviewing,
    maybe_advance_to_negotiating,
)

logger = logging.getLogger(__name__)

# Channel name -> model value mapping
CHANNEL_MAP = {
    "전화": Contact.Channel.PHONE,
    "문자": Contact.Channel.SMS,
    "카톡": Contact.Channel.KAKAO,
    "이메일": Contact.Channel.EMAIL,
    "linkedin": Contact.Channel.LINKEDIN,
}

# Result name -> model value mapping
RESULT_MAP = {
    "응답": Contact.Result.RESPONDED,
    "미응답": Contact.Result.NO_RESPONSE,
    "거절": Contact.Result.REJECTED,
    "관심": Contact.Result.INTERESTED,
    "보류": Contact.Result.ON_HOLD,
}

# Navigate targets -> URL names
NAVIGATE_MAP = {
    "projects": "projects:project_list",
    "프로젝트": "projects:project_list",
    "candidates": "candidates:candidate_list",
    "후보자": "candidates:candidate_list",
    "dashboard": "dashboard",
    "대시보드": "dashboard",
}


def _get_candidate(candidate_id: str, organization: Organization) -> Candidate:
    return Candidate.objects.get(pk=uuid_mod.UUID(candidate_id), owned_by=organization)


def preview_action(
    *,
    intent: str,
    entities: dict[str, Any],
    project: Project | None,
    user: User,
    organization: Organization,
) -> dict[str, Any]:
    """Generate a preview of what the action will do. No DB changes."""
    handler = _PREVIEW_HANDLERS.get(intent)
    if handler is None:
        return {"ok": False, "intent": intent, "error": f"지원하지 않는 명령입니다: {intent}"}
    try:
        return handler(entities=entities, project=project, user=user, organization=organization)
    except Exception as e:
        logger.exception("Preview failed for %s", intent)
        return {"ok": False, "intent": intent, "error": str(e)}


def confirm_action(
    *,
    intent: str,
    entities: dict[str, Any],
    project: Project | None,
    user: User,
    organization: Organization,
) -> dict[str, Any]:
    """Execute the action and commit to DB."""
    handler = _CONFIRM_HANDLERS.get(intent)
    if handler is None:
        return {"ok": False, "intent": intent, "error": f"지원하지 않는 명령입니다: {intent}"}
    try:
        return handler(entities=entities, project=project, user=user, organization=organization)
    except Exception as e:
        logger.exception("Confirm failed for %s", intent)
        return {"ok": False, "intent": intent, "error": str(e)}


# --- Preview handlers ---

def _preview_contact_record(*, entities, project, user, organization):
    candidate = _get_candidate(entities["candidate_id"], organization)
    channel = CHANNEL_MAP.get(entities.get("channel", ""), entities.get("channel", ""))
    result = RESULT_MAP.get(entities.get("result", ""), entities.get("result", ""))
    return {
        "ok": True,
        "intent": "contact_record",
        "summary": f"{candidate.name}님에게 {entities.get('channel', '')}로 컨택. 결과: {entities.get('result', '')}",
        "details": {
            "candidate": candidate.name,
            "channel": str(channel),
            "result": str(result),
        },
    }


def _preview_contact_reserve(*, entities, project, user, organization):
    names = entities.get("candidate_names", [])
    return {
        "ok": True,
        "intent": "contact_reserve",
        "summary": f"{len(names)}명 컨택 예정 등록: {', '.join(names)}",
        "details": {"candidate_names": names},
    }


def _preview_status_query(*, entities, project, user, organization):
    if project:
        contact_count = Contact.objects.filter(project=project).exclude(result=Contact.Result.RESERVED).count()
        sub_count = Submission.objects.filter(project=project).count()
        interview_count = Interview.objects.filter(submission__project=project).count()
        return {
            "ok": True,
            "intent": "status_query",
            "summary": f"{project.title}: 컨택 {contact_count}건, 추천 {sub_count}건, 면접 {interview_count}건",
            "details": {
                "project": project.title,
                "status": project.status,
                "contacts": contact_count,
                "submissions": sub_count,
                "interviews": interview_count,
            },
        }
    return {
        "ok": True,
        "intent": "status_query",
        "summary": "전체 현황 조회",
        "details": {},
    }


def _preview_todo_query(*, entities, project, user, organization):
    actions = get_today_actions(user, organization)
    return {
        "ok": True,
        "intent": "todo_query",
        "summary": f"오늘 할 일 {len(actions)}건",
        "details": {"actions": actions[:10]},
    }


def _preview_navigate(*, entities, project, user, organization):
    target = entities.get("target_page", "")
    url_name = NAVIGATE_MAP.get(target, NAVIGATE_MAP.get(target.lower(), ""))
    url = None
    if url_name:
        try:
            url = reverse(url_name)
        except Exception:
            pass
    return {
        "ok": True,
        "intent": "navigate",
        "summary": f"'{target}' 화면으로 이동",
        "url": url,
    }


def _preview_meeting_navigate(*, entities, project, user, organization):
    return {
        "ok": True,
        "intent": "meeting_navigate",
        "summary": "미팅 녹음 업로드 화면을 엽니다",
        "url": reverse("voice_meeting_upload") if project is None else None,
    }


def _preview_search(*, entities, project, user, organization):
    keywords = entities.get("keywords", "")
    return {
        "ok": True,
        "intent": "search_candidate",
        "summary": f"'{keywords}' 후보자 검색",
        "url": f"{reverse('candidates:candidate_list')}?q={keywords}",
    }


# --- Confirm handlers ---

def _confirm_contact_record(*, entities, project, user, organization):
    candidate = _get_candidate(entities["candidate_id"], organization)
    channel = CHANNEL_MAP.get(entities.get("channel", ""), "")
    result_val = RESULT_MAP.get(entities.get("result", ""), "")
    contacted_at_str = entities.get("contacted_at")
    contacted_at = parse_datetime(contacted_at_str) if contacted_at_str else timezone.now()

    contact = Contact.objects.create(
        project=project,
        candidate=candidate,
        consultant=user,
        channel=channel,
        result=result_val,
        contacted_at=contacted_at,
        notes=entities.get("notes", ""),
    )
    return {
        "ok": True,
        "intent": "contact_record",
        "summary": f"{candidate.name}님 컨택 기록이 저장되었습니다.",
        "record_id": str(contact.pk),
    }


def _confirm_contact_reserve(*, entities, project, user, organization):
    candidate_ids = entities.get("candidate_ids", [])
    result = reserve_candidates(project, candidate_ids, user)
    created_names = [c.candidate.name for c in result["created"]] if result["created"] else []
    return {
        "ok": True,
        "intent": "contact_reserve",
        "summary": f"{len(created_names)}명 컨택 예정 등록 완료. 건너뜀: {', '.join(result['skipped']) or '없음'}",
    }


# Read-only intents just return the same as preview
def _confirm_status_query(*, entities, project, user, organization):
    return _preview_status_query(entities=entities, project=project, user=user, organization=organization)


def _confirm_todo_query(*, entities, project, user, organization):
    return _preview_todo_query(entities=entities, project=project, user=user, organization=organization)


def _confirm_navigate(*, entities, project, user, organization):
    return _preview_navigate(entities=entities, project=project, user=user, organization=organization)


def _confirm_search(*, entities, project, user, organization):
    return _preview_search(entities=entities, project=project, user=user, organization=organization)


# Handler registries
_PREVIEW_HANDLERS = {
    "contact_record": _preview_contact_record,
    "contact_reserve": _preview_contact_reserve,
    "status_query": _preview_status_query,
    "todo_query": _preview_todo_query,
    "navigate": _preview_navigate,
    "meeting_navigate": _preview_meeting_navigate,
    "search_candidate": _preview_search,
}

_CONFIRM_HANDLERS = {
    "contact_record": _confirm_contact_record,
    "contact_reserve": _confirm_contact_reserve,
    "status_query": _confirm_status_query,
    "todo_query": _confirm_todo_query,
    "navigate": _confirm_navigate,
    "search_candidate": _confirm_search,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p14_voice_action_executor.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/voice/action_executor.py tests/test_p14_voice_action_executor.py
git commit -m "feat(p14): add voice action executor with preview/confirm pattern"
```

---

### Task 8: Meeting Analyzer Service

**Files:**
- Create: `projects/services/voice/meeting_analyzer.py`
- Extend: `tests/test_p14_voice_meeting.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_p14_voice_meeting.py`:

```python
from unittest.mock import MagicMock, patch

from projects.services.voice.meeting_analyzer import (
    analyze_meeting,
    apply_meeting_insights,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    validate_meeting_file,
)


def test_validate_meeting_file_valid():
    f = MagicMock()
    f.name = "meeting.mp3"
    f.size = 50 * 1024 * 1024  # 50MB
    errors = validate_meeting_file(f)
    assert errors == []


def test_validate_meeting_file_too_large():
    f = MagicMock()
    f.name = "meeting.mp3"
    f.size = 200 * 1024 * 1024  # 200MB
    errors = validate_meeting_file(f)
    assert len(errors) == 1
    assert "크기" in errors[0]


def test_validate_meeting_file_bad_extension():
    f = MagicMock()
    f.name = "meeting.exe"
    f.size = 1024
    errors = validate_meeting_file(f)
    assert len(errors) == 1
    assert "형식" in errors[0]


@patch("projects.services.voice.meeting_analyzer._get_gemini_client")
@patch("projects.services.voice.meeting_analyzer.transcribe")
def test_analyze_meeting(mock_transcribe, mock_gemini_fn, project, candidate, user):
    record = MeetingRecord.objects.create(
        project=project,
        candidate=candidate,
        audio_file="meetings/audio/test.webm",
        created_by=user,
    )

    mock_transcribe.return_value = "현재 연봉은 8천만원이고 이직 의향이 있습니다."

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"interest_level": "높음", "current_salary": "8천만원", "desired_salary": "", "available_date": "", "career_highlights": "", "concerns": "", "action_items": "", "mood": "긍정적", "notes": ""}'
    mock_client.models.generate_content.return_value = mock_response
    mock_gemini_fn.return_value = mock_client

    analyze_meeting(record.pk)

    record.refresh_from_db()
    assert record.status == MeetingRecord.Status.READY
    assert record.transcript != ""
    assert record.analysis_json.get("interest_level") == "높음"


def test_apply_meeting_insights(project, candidate, user):
    record = MeetingRecord.objects.create(
        project=project,
        candidate=candidate,
        audio_file="meetings/audio/test.webm",
        status=MeetingRecord.Status.READY,
        analysis_json={
            "interest_level": "높음",
            "current_salary": "8천만원",
            "desired_salary": "1억",
            "mood": "긍정적",
        },
        created_by=user,
    )

    selected = ["current_salary", "desired_salary"]
    apply_meeting_insights(record=record, selected_fields=selected, user=user)

    record.refresh_from_db()
    assert record.status == MeetingRecord.Status.APPLIED
    assert record.applied_by == user
    assert record.applied_at is not None

    # Check a contact note was created
    contact = Contact.objects.filter(project=project, candidate=candidate).first()
    assert contact is not None
    assert "8천만원" in contact.notes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p14_voice_meeting.py::test_validate_meeting_file_valid -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement meeting analyzer**

```python
# projects/services/voice/meeting_analyzer.py
"""Meeting recording analysis pipeline: async STT + LLM insight extraction."""

from __future__ import annotations

import logging
import os
from typing import Any

from django.conf import settings
from django.utils import timezone

from data_extraction.services.extraction.sanitizers import parse_llm_json
from projects.models import Contact, MeetingRecord

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-preview-05-20"
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {".mp3", ".m4a", ".wav", ".webm"}

MEETING_ANALYSIS_PROMPT = """\
당신은 헤드헌팅 미팅 녹음 분석 전문가입니다.
아래 미팅 녹취록을 분석하여 구조화된 인사이트를 추출하세요.

반드시 아래 JSON 형식으로만 응답:
{
  "interest_level": "높음|보통|낮음|불명확",
  "current_salary": "현재 연봉 (없으면 빈 문자열)",
  "desired_salary": "희망 연봉 (없으면 빈 문자열)",
  "available_date": "이직 가능 시기 (없으면 빈 문자열)",
  "career_highlights": "주요 경력 하이라이트 (없으면 빈 문자열)",
  "concerns": "우려 사항/질문 (없으면 빈 문자열)",
  "action_items": "다음 단계 액션 아이템 (없으면 빈 문자열)",
  "mood": "전반적 미팅 분위기",
  "notes": "특이사항/메모 (없으면 빈 문자열)"
}
"""

# Field label mapping for DB notes
FIELD_LABELS = {
    "interest_level": "관심도/의향",
    "current_salary": "현재 연봉",
    "desired_salary": "희망 연봉",
    "available_date": "이직 가능 시기",
    "career_highlights": "주요 경력 하이라이트",
    "concerns": "우려 사항/질문",
    "action_items": "다음 단계 액션 아이템",
    "mood": "전반적 미팅 분위기",
    "notes": "특이사항/메모",
}

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def validate_meeting_file(f) -> list[str]:
    """Validate meeting file (extension + size). Returns list of error messages."""
    errors = []
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        errors.append(f"허용되지 않는 파일 형식입니다. ({', '.join(ALLOWED_EXTENSIONS)})")
    if f.size > MAX_FILE_SIZE:
        errors.append(
            f"파일 크기가 {MAX_FILE_SIZE // (1024*1024)}MB를 초과합니다. "
            f"(현재: {f.size / (1024*1024):.1f}MB)"
        )
    return errors


def analyze_meeting(meeting_record_id) -> None:
    """Run full meeting analysis pipeline. Updates MeetingRecord in-place.

    Called by management command or background task.
    """
    from projects.services.voice.transcriber import TranscribeMode, transcribe

    record = MeetingRecord.objects.get(pk=meeting_record_id)

    try:
        # Step 1: Transcribe
        record.status = MeetingRecord.Status.TRANSCRIBING
        record.save(update_fields=["status"])

        record.audio_file.open("rb")
        try:
            transcript = transcribe(record.audio_file, mode=TranscribeMode.MEETING)
        finally:
            record.audio_file.close()

        if not transcript:
            record.status = MeetingRecord.Status.FAILED
            record.error_message = "음성 인식 결과가 없습니다."
            record.save(update_fields=["status", "error_message"])
            return

        record.transcript = transcript
        record.save(update_fields=["transcript"])

        # Step 2: LLM analysis
        record.status = MeetingRecord.Status.ANALYZING
        record.save(update_fields=["status"])

        client = _get_gemini_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                {"role": "user", "parts": [{"text": MEETING_ANALYSIS_PROMPT + "\n\n녹취록:\n" + transcript}]},
            ],
        )
        analysis = parse_llm_json(response.text.strip())

        record.analysis_json = analysis
        record.status = MeetingRecord.Status.READY
        record.save(update_fields=["analysis_json", "status"])

    except Exception as e:
        logger.exception("Meeting analysis failed for %s", meeting_record_id)
        record.status = MeetingRecord.Status.FAILED
        record.error_message = str(e)
        record.save(update_fields=["status", "error_message"])


def apply_meeting_insights(
    *,
    record: MeetingRecord,
    selected_fields: list[str],
    user,
) -> None:
    """Apply selected analysis fields to DB.

    Creates a Contact note with provenance tag.
    """
    analysis = record.edited_json if record.edited_json else record.analysis_json

    # Build notes text from selected fields
    note_parts = [f"[미팅녹음분석 {record.pk}]"]
    for field in selected_fields:
        value = analysis.get(field, "")
        if value:
            label = FIELD_LABELS.get(field, field)
            note_parts.append(f"- {label}: {value}")

    if len(note_parts) > 1:  # Has actual content beyond the tag
        notes_text = "\n".join(note_parts)

        # Find or create a contact for this project+candidate
        existing_contact = Contact.objects.filter(
            project=record.project,
            candidate=record.candidate,
        ).exclude(result=Contact.Result.RESERVED).order_by("-contacted_at").first()

        if existing_contact:
            # Append to existing contact notes
            if existing_contact.notes:
                existing_contact.notes += "\n\n" + notes_text
            else:
                existing_contact.notes = notes_text
            existing_contact.save(update_fields=["notes"])
        else:
            # Create new contact record
            Contact.objects.create(
                project=record.project,
                candidate=record.candidate,
                consultant=user,
                channel=Contact.Channel.PHONE,
                result=Contact.Result.RESPONDED,
                contacted_at=timezone.now(),
                notes=notes_text,
            )

    record.status = MeetingRecord.Status.APPLIED
    record.applied_at = timezone.now()
    record.applied_by = user
    record.save(update_fields=["status", "applied_at", "applied_by"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p14_voice_meeting.py -v`
Expected: All tests (7) PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/voice/meeting_analyzer.py tests/test_p14_voice_meeting.py
git commit -m "feat(p14): add meeting recording analyzer with async pipeline and DB apply"
```

---

### Task 9: URL Configuration + View Stubs

**Files:**
- Create: `projects/urls_voice.py`
- Create: `projects/views_voice.py`
- Modify: `main/urls.py`
- Create: `tests/test_p14_voice_views.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_p14_voice_views.py
"""P14: Voice endpoint integration tests."""
import io
import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client as TestClient

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import MeetingRecord, Project


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="view_tester", password="test1234")
    Membership.objects.create(user=u, organization=org)
    return u


@pytest.fixture
def auth_client(user):
    c = TestClient()
    c.login(username="view_tester", password="test1234")
    return c


@pytest.fixture
def client_obj(db, org):
    return Client.objects.create(name="View Client", organization=org)


@pytest.fixture
def project(db, org, client_obj, user):
    return Project.objects.create(
        client=client_obj, organization=org, title="View Test", created_by=user,
    )


@pytest.fixture
def candidate(db, org):
    return Candidate.objects.create(name="홍길동", owned_by=org)


def test_transcribe_endpoint_requires_auth(db):
    c = TestClient()
    resp = c.post("/voice/transcribe/")
    assert resp.status_code in (302, 403)  # Redirect to login or forbidden


@patch("projects.views_voice.transcribe")
def test_transcribe_endpoint(mock_transcribe, auth_client):
    mock_transcribe.return_value = "홍길동 전화했어"
    audio = io.BytesIO(b"fake audio")
    audio.name = "voice.webm"
    resp = auth_client.post(
        "/voice/transcribe/",
        {"audio": audio, "mode": "command"},
        format="multipart",
    )
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["text"] == "홍길동 전화했어"


def test_context_endpoint(auth_client, project):
    resp = auth_client.get(
        "/voice/context/",
        {"page": "project_detail", "project_id": str(project.pk)},
    )
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["project_id"] == str(project.pk)


def test_history_endpoint(auth_client):
    resp = auth_client.get("/voice/history/")
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert "turns" in data


def test_meeting_upload_requires_auth(db):
    c = TestClient()
    resp = c.post("/voice/meeting-upload/")
    assert resp.status_code in (302, 403)


def test_meeting_status_not_found(auth_client):
    resp = auth_client.get("/voice/meeting-status/00000000-0000-0000-0000-000000000000/")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p14_voice_views.py -v`
Expected: FAIL (URL resolution errors)

- [ ] **Step 3: Create URL configuration**

```python
# projects/urls_voice.py
from django.urls import path

from . import views_voice

urlpatterns = [
    path("transcribe/", views_voice.voice_transcribe, name="voice_transcribe"),
    path("intent/", views_voice.voice_intent, name="voice_intent"),
    path("preview/", views_voice.voice_preview, name="voice_preview"),
    path("confirm/", views_voice.voice_confirm, name="voice_confirm"),
    path("context/", views_voice.voice_context, name="voice_context"),
    path("history/", views_voice.voice_history, name="voice_history"),
    path("meeting-upload/", views_voice.voice_meeting_upload, name="voice_meeting_upload"),
    path(
        "meeting-status/<uuid:pk>/",
        views_voice.voice_meeting_status,
        name="voice_meeting_status",
    ),
    path("meeting-apply/", views_voice.voice_meeting_apply, name="voice_meeting_apply"),
]
```

- [ ] **Step 4: Create views**

```python
# projects/views_voice.py
"""P14: Voice agent endpoint views."""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from accounts.models import Membership
from projects.models import MeetingRecord, Project
from projects.services.voice.action_executor import confirm_action, preview_action
from projects.services.voice.context_resolver import resolve_context
from projects.services.voice.conversation import ConversationManager
from projects.services.voice.entity_resolver import resolve_candidate
from projects.services.voice.intent_parser import parse_intent
from projects.services.voice.meeting_analyzer import (
    apply_meeting_insights,
    validate_meeting_file,
)
from projects.services.voice.transcriber import TranscribeMode, transcribe

logger = logging.getLogger(__name__)


def _get_org(user):
    membership = Membership.objects.filter(user=user).select_related("organization").first()
    return membership.organization if membership else None


@login_required
@require_POST
def voice_transcribe(request):
    """POST /voice/transcribe/ — audio file -> text."""
    audio = request.FILES.get("audio")
    if not audio:
        return JsonResponse({"error": "음성 파일이 필요합니다."}, status=400)

    mode_str = request.POST.get("mode", "command")
    mode = TranscribeMode.MEETING if mode_str == "meeting" else TranscribeMode.COMMAND

    try:
        text = transcribe(audio, mode=mode)
    except RuntimeError as e:
        return JsonResponse({"error": str(e)}, status=500)

    # Add to conversation
    mgr = ConversationManager(request.session)
    if text:
        mgr.add_turn(role="user", text=text)

    return JsonResponse({"text": text, "empty": not text})


@login_required
@require_POST
def voice_intent(request):
    """POST /voice/intent/ — text -> intent + entities."""
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "조직 정보가 없습니다."}, status=403)

    body = json.loads(request.body) if request.content_type == "application/json" else request.POST
    text = body.get("text", "")
    context_hint = json.loads(body.get("context", "{}")) if isinstance(body.get("context"), str) else body.get("context", {})

    ctx = resolve_context(user=request.user, organization=org, context_hint=context_hint)
    result = parse_intent(text=text, context=ctx)

    # Entity resolution for candidate names
    if result.entities.get("candidate_name"):
        project = None
        if ctx["project_id"]:
            project = Project.objects.filter(pk=ctx["project_id"]).first()
        resolution = resolve_candidate(
            name=result.entities["candidate_name"],
            organization=org,
            project=project,
        )
        result.entities["_candidate_resolution"] = {
            "status": resolution.status,
            "candidate_id": str(resolution.candidate_id) if resolution.candidate_id else None,
            "candidates": resolution.candidates,
        }
        if resolution.candidate_id:
            result.entities["candidate_id"] = str(resolution.candidate_id)

    mgr = ConversationManager(request.session)
    mgr.set_pending(intent=result.intent, entities=result.entities, missing=result.missing_fields)

    return JsonResponse({
        "intent": result.intent,
        "entities": result.entities,
        "confidence": result.confidence,
        "missing_fields": result.missing_fields,
    })


@login_required
@require_POST
def voice_preview(request):
    """POST /voice/preview/ — intent + entities -> preview (no DB change)."""
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "조직 정보가 없습니다."}, status=403)

    body = json.loads(request.body) if request.content_type == "application/json" else request.POST
    intent = body.get("intent", "")
    entities = json.loads(body.get("entities", "{}")) if isinstance(body.get("entities"), str) else body.get("entities", {})
    project_id = body.get("project_id")

    project = None
    if project_id:
        project = Project.objects.filter(pk=project_id, organization=org).first()

    result = preview_action(
        intent=intent, entities=entities, project=project, user=request.user, organization=org,
    )

    # Generate preview token
    mgr = ConversationManager(request.session)
    token = mgr.generate_preview_token()
    result["preview_token"] = token

    return JsonResponse(result)


@login_required
@require_POST
def voice_confirm(request):
    """POST /voice/confirm/ — confirm preview with idempotent token -> DB commit."""
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "조직 정보가 없습니다."}, status=403)

    body = json.loads(request.body) if request.content_type == "application/json" else request.POST
    token = body.get("preview_token", "")
    intent = body.get("intent", "")
    entities = json.loads(body.get("entities", "{}")) if isinstance(body.get("entities"), str) else body.get("entities", {})
    project_id = body.get("project_id")

    # Validate idempotent token
    mgr = ConversationManager(request.session)
    if not mgr.consume_preview_token(token):
        return JsonResponse({"error": "이미 처리된 요청입니다."}, status=409)

    project = None
    if project_id:
        project = Project.objects.filter(pk=project_id, organization=org).first()

    result = confirm_action(
        intent=intent, entities=entities, project=project, user=request.user, organization=org,
    )

    if result.get("ok"):
        mgr.add_turn(role="assistant", text=result.get("summary", "완료되었습니다."))
        # Reset pending state
        conv = mgr.get_or_create()
        conv["pending_intent"] = None
        conv["collected_entities"] = {}
        conv["missing_fields"] = []
        request.session.modified = True

    return JsonResponse(result)


@login_required
@require_GET
def voice_context(request):
    """GET /voice/context/ — return current verified context."""
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "조직 정보가 없습니다."}, status=403)

    context_hint = {
        "page": request.GET.get("page", "unknown"),
        "project_id": request.GET.get("project_id", ""),
        "tab": request.GET.get("tab", ""),
    }
    ctx = resolve_context(user=request.user, organization=org, context_hint=context_hint)
    # Serialize UUID
    if ctx.get("project_id"):
        ctx["project_id"] = str(ctx["project_id"])
    return JsonResponse(ctx)


@login_required
@require_GET
def voice_history(request):
    """GET /voice/history/ — return conversation turns."""
    mgr = ConversationManager(request.session)
    conv = mgr.get_or_create()
    return JsonResponse({
        "id": conv["id"],
        "turns": conv["turns"],
        "pending_intent": conv["pending_intent"],
        "missing_fields": conv["missing_fields"],
    })


@login_required
@require_POST
def voice_meeting_upload(request):
    """POST /voice/meeting-upload/ — upload meeting recording file."""
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "조직 정보가 없습니다."}, status=403)

    audio = request.FILES.get("audio")
    if not audio:
        return JsonResponse({"error": "파일이 필요합니다."}, status=400)

    errors = validate_meeting_file(audio)
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    project_id = request.POST.get("project_id")
    candidate_id = request.POST.get("candidate_id")

    if not project_id or not candidate_id:
        return JsonResponse({"error": "프로젝트와 후보자를 선택해주세요."}, status=400)

    project = Project.objects.filter(pk=project_id, organization=org).first()
    if not project:
        return JsonResponse({"error": "프로젝트를 찾을 수 없습니다."}, status=404)

    record = MeetingRecord.objects.create(
        project=project,
        candidate_id=candidate_id,
        audio_file=audio,
        created_by=request.user,
    )

    return JsonResponse({
        "ok": True,
        "meeting_id": str(record.pk),
        "status": record.status,
        "message": "업로드 완료. 분석을 시작합니다.",
    })


@login_required
@require_GET
def voice_meeting_status(request, pk):
    """GET /voice/meeting-status/<uuid>/ — poll meeting analysis status."""
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "조직 정보가 없습니다."}, status=403)

    try:
        record = MeetingRecord.objects.get(pk=pk, project__organization=org)
    except MeetingRecord.DoesNotExist:
        return JsonResponse({"error": "미팅 녹음을 찾을 수 없습니다."}, status=404)

    data = {
        "meeting_id": str(record.pk),
        "status": record.status,
        "error_message": record.error_message,
    }
    if record.status == MeetingRecord.Status.READY:
        data["analysis"] = record.analysis_json
        data["transcript_preview"] = record.transcript[:500]
    elif record.status == MeetingRecord.Status.APPLIED:
        data["analysis"] = record.analysis_json
        data["applied_at"] = record.applied_at.isoformat() if record.applied_at else None

    return JsonResponse(data)


@login_required
@require_POST
def voice_meeting_apply(request):
    """POST /voice/meeting-apply/ — apply selected analysis fields to DB."""
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "조직 정보가 없습니다."}, status=403)

    body = json.loads(request.body) if request.content_type == "application/json" else request.POST
    meeting_id = body.get("meeting_id")
    selected_fields = body.get("selected_fields", [])
    if isinstance(selected_fields, str):
        selected_fields = json.loads(selected_fields)
    edited = body.get("edited_json")
    if isinstance(edited, str):
        edited = json.loads(edited)

    try:
        record = MeetingRecord.objects.get(pk=meeting_id, project__organization=org)
    except MeetingRecord.DoesNotExist:
        return JsonResponse({"error": "미팅 녹음을 찾을 수 없습니다."}, status=404)

    if record.status != MeetingRecord.Status.READY:
        return JsonResponse({"error": "분석이 완료된 녹음만 반영할 수 있습니다."}, status=400)

    if edited:
        record.edited_json = edited
        record.save(update_fields=["edited_json"])

    apply_meeting_insights(record=record, selected_fields=selected_fields, user=request.user)

    return JsonResponse({"ok": True, "message": "선택한 항목이 반영되었습니다."})
```

- [ ] **Step 5: Add voice URL include to main/urls.py**

Add this line to `main/urls.py` `urlpatterns`, before the `projects/` include:

```python
path("voice/", include("projects.urls_voice")),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_p14_voice_views.py -v`
Expected: 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add projects/urls_voice.py projects/views_voice.py main/urls.py tests/test_p14_voice_views.py
git commit -m "feat(p14): add voice URL config and view endpoints"
```

---

### Task 10: Meeting Processing Management Command

**Files:**
- Create: `projects/management/commands/process_meetings.py`

- [ ] **Step 1: Create management command**

```python
# projects/management/commands/process_meetings.py
"""Process pending meeting recordings (STT + LLM analysis).

Run via cron or manually:
    python manage.py process_meetings
    python manage.py process_meetings --id <uuid>  # single record
"""

from django.core.management.base import BaseCommand

from projects.models import MeetingRecord
from projects.services.voice.meeting_analyzer import analyze_meeting


class Command(BaseCommand):
    help = "Process pending meeting recordings (STT + LLM analysis)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--id",
            type=str,
            help="Process a specific MeetingRecord by UUID",
        )

    def handle(self, *args, **options):
        record_id = options.get("id")

        if record_id:
            try:
                record = MeetingRecord.objects.get(pk=record_id)
                self.stdout.write(f"Processing meeting {record.pk}...")
                analyze_meeting(record.pk)
                record.refresh_from_db()
                self.stdout.write(self.style.SUCCESS(f"Done: {record.status}"))
            except MeetingRecord.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"MeetingRecord {record_id} not found"))
            return

        pending = MeetingRecord.objects.filter(
            status=MeetingRecord.Status.UPLOADED,
        ).order_by("created_at")

        if not pending.exists():
            self.stdout.write("No pending meetings to process.")
            return

        self.stdout.write(f"Found {pending.count()} pending meeting(s).")
        for record in pending:
            self.stdout.write(f"  Processing {record.pk} ({record.candidate})...")
            try:
                analyze_meeting(record.pk)
                record.refresh_from_db()
                self.stdout.write(f"    -> {record.status}")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"    -> Failed: {e}"))
```

- [ ] **Step 2: Verify command is discoverable**

Run: `uv run python manage.py process_meetings --help`
Expected: Shows help text with `--id` option.

- [ ] **Step 3: Commit**

```bash
mkdir -p projects/management/commands
git add projects/management/ projects/management/commands/ projects/management/commands/process_meetings.py
git commit -m "feat(p14): add process_meetings management command for async analysis"
```

Note: Ensure `projects/management/__init__.py` and `projects/management/commands/__init__.py` exist.

---

### Task 11: Frontend — Voice Button + Modal Templates

**Files:**
- Create: `projects/templates/projects/partials/voice_button.html`
- Create: `projects/templates/projects/partials/voice_modal.html`
- Create: `projects/templates/projects/partials/meeting_upload.html`
- Create: `projects/templates/projects/partials/meeting_status.html`
- Modify: `templates/common/base.html`

- [ ] **Step 1: Create voice button template**

```html
<!-- projects/templates/projects/partials/voice_button.html -->
{% load static %}
<button
  id="voice-agent-fab"
  type="button"
  class="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 transition-colors"
  data-voice-context='{"page": "{{ voice_page|default:"unknown" }}", "project_id": "{{ voice_project_id|default:"" }}", "tab": "{{ voice_tab|default:"" }}"}'
  aria-label="음성 에이전트"
  onclick="window.VoiceAgent.toggle()"
>
  <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
    <path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z" />
  </svg>
</button>

{% include "projects/partials/voice_modal.html" %}
<script src="{% static 'js/voice-agent.js' %}"></script>
```

- [ ] **Step 2: Create voice modal template**

```html
<!-- projects/templates/projects/partials/voice_modal.html -->
<div id="voice-modal" class="fixed inset-0 z-[60] hidden" role="dialog" aria-modal="true">
  <!-- Backdrop -->
  <div class="absolute inset-0 bg-black/30" onclick="window.VoiceAgent.close()"></div>

  <!-- Panel -->
  <div class="absolute bottom-24 right-6 w-96 max-h-[70vh] flex flex-col rounded-2xl bg-white shadow-2xl overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between border-b px-4 py-3">
      <h3 class="text-sm font-semibold text-gray-900">음성 에이전트</h3>
      <button onclick="window.VoiceAgent.close()" class="text-gray-400 hover:text-gray-600">
        <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
      </button>
    </div>

    <!-- Messages -->
    <div id="voice-messages" class="flex-1 overflow-y-auto p-4 space-y-3">
      <div class="text-sm text-gray-500 text-center">무엇을 도와드릴까요?</div>
    </div>

    <!-- Input area -->
    <div class="border-t p-3">
      <div class="flex items-center gap-2">
        <input
          id="voice-text-input"
          type="text"
          class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
          placeholder="텍스트로 입력하거나 마이크를 누르세요"
          onkeydown="if(event.key==='Enter')window.VoiceAgent.sendText()"
        />
        <button
          id="voice-mic-btn"
          type="button"
          class="flex h-10 w-10 items-center justify-center rounded-full bg-gray-100 text-gray-600 hover:bg-indigo-100 hover:text-indigo-600 transition-colors"
          onclick="window.VoiceAgent.toggleRecording()"
          aria-label="음성 녹음"
        >
          <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z"/>
          </svg>
        </button>
        <button
          type="button"
          class="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
          onclick="window.VoiceAgent.sendText()"
          aria-label="전송"
        >
          <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Create meeting upload and status templates**

```html
<!-- projects/templates/projects/partials/meeting_upload.html -->
<div id="meeting-upload-panel" class="p-4">
  <h4 class="text-sm font-medium text-gray-900 mb-3">미팅 녹음 업로드</h4>
  <form id="meeting-upload-form" enctype="multipart/form-data">
    {% csrf_token %}
    <div class="space-y-3">
      <div>
        <label class="block text-xs text-gray-600 mb-1">프로젝트</label>
        <select name="project_id" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" required>
          <option value="">선택</option>
        </select>
      </div>
      <div>
        <label class="block text-xs text-gray-600 mb-1">후보자</label>
        <select name="candidate_id" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" required>
          <option value="">선택</option>
        </select>
      </div>
      <div>
        <label class="block text-xs text-gray-600 mb-1">녹음 파일 (mp3, m4a, wav, webm / 최대 100MB)</label>
        <input type="file" name="audio" accept=".mp3,.m4a,.wav,.webm" class="w-full text-sm" required />
      </div>
      <button type="submit" class="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700">
        업로드 및 분석 시작
      </button>
    </div>
  </form>
</div>
```

```html
<!-- projects/templates/projects/partials/meeting_status.html -->
<div id="meeting-status-panel" class="p-4">
  <h4 class="text-sm font-medium text-gray-900 mb-3">미팅 분석 결과</h4>
  <div id="meeting-analysis-content">
    <!-- Populated by JS -->
  </div>
</div>
```

- [ ] **Step 4: Update base.html to replace chatbot with voice agent**

In `templates/common/base.html`, replace:
```html
  <!-- Global: mic button + chatbot modal -->
  {% include "candidates/partials/chatbot_fab.html" %}
```
with:
```html
  <!-- Global: voice agent button + modal -->
  {% include "projects/partials/voice_button.html" %}
```

- [ ] **Step 5: Verify templates load without error**

Run: `uv run python manage.py check`
Expected: System check identified no issues.

- [ ] **Step 6: Commit**

```bash
git add projects/templates/projects/partials/voice_button.html projects/templates/projects/partials/voice_modal.html projects/templates/projects/partials/meeting_upload.html projects/templates/projects/partials/meeting_status.html templates/common/base.html
git commit -m "feat(p14): add voice agent frontend templates, replace chatbot FAB"
```

---

### Task 12: Frontend — voice-agent.js

**Files:**
- Create: `static/js/voice-agent.js`

- [ ] **Step 1: Create the JavaScript module**

```javascript
// static/js/voice-agent.js
(function () {
  "use strict";

  var VoiceAgent = {
    modal: null,
    messages: null,
    textInput: null,
    micBtn: null,
    recorder: null,
    recording: false,
    inactivityTimer: null,
    INACTIVITY_TIMEOUT: 5 * 60 * 1000, // 5 minutes

    init: function () {
      this.modal = document.getElementById("voice-modal");
      this.messages = document.getElementById("voice-messages");
      this.textInput = document.getElementById("voice-text-input");
      this.micBtn = document.getElementById("voice-mic-btn");
    },

    toggle: function () {
      if (!this.modal) this.init();
      if (this.modal.classList.contains("hidden")) {
        this.open();
      } else {
        this.close();
      }
    },

    open: function () {
      if (!this.modal) this.init();
      this.modal.classList.remove("hidden");
      this.textInput.focus();
      this._resetInactivityTimer();
    },

    close: function () {
      if (!this.modal) return;
      this.modal.classList.add("hidden");
      if (this.recording) this.stopRecording();
      this._clearInactivityTimer();
      // Reset conversation via API
      this._post("/voice/history/", {action: "reset"}).catch(function(){});
    },

    // --- Recording ---
    toggleRecording: function () {
      if (this.recording) {
        this.stopRecording();
      } else {
        this.startRecording();
      }
    },

    startRecording: function () {
      var self = this;
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        this._addMessage("assistant", "이 브라우저에서는 음성 입력을 사용할 수 없습니다.");
        return;
      }
      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then(function (stream) {
          self.recorder = new MediaRecorder(stream, {
            mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
              ? "audio/webm;codecs=opus"
              : "audio/webm",
          });
          var chunks = [];
          self.recorder.ondataavailable = function (e) {
            if (e.data.size > 0) chunks.push(e.data);
          };
          self.recorder.onstop = function () {
            stream.getTracks().forEach(function (t) { t.stop(); });
            var blob = new Blob(chunks, { type: "audio/webm" });
            self._processAudio(blob);
          };
          self.recorder.start();
          self.recording = true;
          self.micBtn.classList.add("bg-red-100", "text-red-600");
          self.micBtn.classList.remove("bg-gray-100", "text-gray-600");
          self._resetInactivityTimer();
        })
        .catch(function (err) {
          self._addMessage("assistant", "마이크 접근 권한이 필요합니다.");
        });
    },

    stopRecording: function () {
      if (this.recorder && this.recorder.state === "recording") {
        this.recorder.stop();
      }
      this.recording = false;
      if (this.micBtn) {
        this.micBtn.classList.remove("bg-red-100", "text-red-600");
        this.micBtn.classList.add("bg-gray-100", "text-gray-600");
      }
    },

    // --- Text input ---
    sendText: function () {
      var text = this.textInput.value.trim();
      if (!text) return;
      this.textInput.value = "";
      this._addMessage("user", text);
      this._processText(text);
      this._resetInactivityTimer();
    },

    // --- Pipeline ---
    _processAudio: function (blob) {
      var self = this;
      this._addMessage("assistant", "음성을 인식하고 있습니다...");
      var formData = new FormData();
      formData.append("audio", blob, "voice.webm");
      formData.append("mode", "command");

      fetch("/voice/transcribe/", {
        method: "POST",
        headers: { "X-CSRFToken": this._getCsrf() },
        body: formData,
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          self._removeLastAssistant();
          if (data.empty || !data.text) {
            self._addMessage("assistant", "음성을 인식하지 못했습니다. 다시 시도해주세요.");
            return;
          }
          self._addMessage("user", data.text);
          self._processText(data.text);
        })
        .catch(function () {
          self._removeLastAssistant();
          self._addMessage("assistant", "음성 인식에 실패했습니다.");
        });
    },

    _processText: function (text) {
      var self = this;
      var context = this._getContext();
      this._addMessage("assistant", "처리 중...");

      this._post("/voice/intent/", { text: text, context: context })
        .then(function (data) {
          self._removeLastAssistant();
          if (data.intent === "unknown") {
            self._addMessage("assistant", "죄송합니다. 명령을 이해하지 못했습니다.");
            return;
          }
          if (data.missing_fields && data.missing_fields.length > 0) {
            self._addMessage("assistant", "추가 정보가 필요합니다: " + data.missing_fields.join(", "));
            return;
          }
          // Handle navigation/search immediately
          if (data.intent === "navigate" || data.intent === "search_candidate" || data.intent === "meeting_navigate") {
            self._executeImmediate(data);
            return;
          }
          // Handle read-only queries
          if (data.intent === "status_query" || data.intent === "todo_query") {
            self._executePreview(data);
            return;
          }
          // Handle candidate disambiguation
          var resolution = data.entities._candidate_resolution;
          if (resolution && resolution.status === "ambiguous") {
            self._showCandidateList(resolution.candidates, data);
            return;
          }
          if (resolution && resolution.status === "not_found") {
            self._addMessage("assistant", "해당 후보자를 찾을 수 없습니다.");
            return;
          }
          // Preview write action
          self._executePreview(data);
        })
        .catch(function () {
          self._removeLastAssistant();
          self._addMessage("assistant", "처리 중 오류가 발생했습니다.");
        });
    },

    _executePreview: function (intentData) {
      var self = this;
      var context = this._getContext();
      this._post("/voice/preview/", {
        intent: intentData.intent,
        entities: intentData.entities,
        project_id: context.project_id || "",
      })
        .then(function (data) {
          if (!data.ok) {
            self._addMessage("assistant", data.error || "미리보기 실패");
            return;
          }
          // For read-only, just show summary
          if (intentData.intent === "status_query" || intentData.intent === "todo_query") {
            self._addMessage("assistant", data.summary);
            return;
          }
          self._addMessage("assistant", data.summary + "\n\n이대로 진행할까요?");
          self._showConfirmButtons(data.preview_token, intentData);
        });
    },

    _executeImmediate: function (intentData) {
      var self = this;
      var context = this._getContext();
      this._post("/voice/preview/", {
        intent: intentData.intent,
        entities: intentData.entities,
        project_id: context.project_id || "",
      })
        .then(function (data) {
          if (data.url) {
            self._addMessage("assistant", data.summary);
            setTimeout(function () { window.location.href = data.url; }, 500);
          } else {
            self._addMessage("assistant", data.summary || "완료");
          }
        });
    },

    _showConfirmButtons: function (token, intentData) {
      var self = this;
      var div = document.createElement("div");
      div.className = "flex gap-2 mt-2";
      var confirmBtn = document.createElement("button");
      confirmBtn.className = "rounded-lg bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700";
      confirmBtn.textContent = "확인";
      confirmBtn.onclick = function () {
        div.remove();
        self._confirmAction(token, intentData);
      };
      var cancelBtn = document.createElement("button");
      cancelBtn.className = "rounded-lg bg-gray-200 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-300";
      cancelBtn.textContent = "취소";
      cancelBtn.onclick = function () {
        div.remove();
        self._addMessage("assistant", "취소되었습니다.");
      };
      div.appendChild(confirmBtn);
      div.appendChild(cancelBtn);
      self.messages.appendChild(div);
      self.messages.scrollTop = self.messages.scrollHeight;
    },

    _confirmAction: function (token, intentData) {
      var self = this;
      var context = this._getContext();
      this._post("/voice/confirm/", {
        preview_token: token,
        intent: intentData.intent,
        entities: intentData.entities,
        project_id: context.project_id || "",
      })
        .then(function (data) {
          if (data.ok) {
            self._addMessage("assistant", data.summary || "완료되었습니다.");
          } else {
            self._addMessage("assistant", data.error || "처리에 실패했습니다.");
          }
        })
        .catch(function () {
          self._addMessage("assistant", "처리 중 오류가 발생했습니다.");
        });
    },

    _showCandidateList: function (candidates, intentData) {
      var self = this;
      self._addMessage("assistant", "동명이인이 있습니다. 선택해주세요:");
      var list = document.createElement("div");
      list.className = "space-y-1 mt-1";
      candidates.forEach(function (c) {
        var btn = document.createElement("button");
        btn.className = "w-full text-left rounded-lg border px-3 py-2 text-sm hover:bg-indigo-50";
        btn.textContent = c.name + (c.email ? " (" + c.email + ")" : "") + (c.phone ? " " + c.phone : "");
        btn.onclick = function () {
          list.remove();
          intentData.entities.candidate_id = c.id;
          delete intentData.entities._candidate_resolution;
          self._executePreview(intentData);
        };
        list.appendChild(btn);
      });
      self.messages.appendChild(list);
      self.messages.scrollTop = self.messages.scrollHeight;
    },

    // --- Helpers ---
    _addMessage: function (role, text) {
      var div = document.createElement("div");
      div.className = role === "user"
        ? "ml-8 rounded-lg bg-indigo-50 px-3 py-2 text-sm text-gray-900"
        : "mr-8 rounded-lg bg-gray-100 px-3 py-2 text-sm text-gray-700";
      div.textContent = text;
      div.dataset.role = role;
      this.messages.appendChild(div);
      this.messages.scrollTop = this.messages.scrollHeight;
    },

    _removeLastAssistant: function () {
      var msgs = this.messages.querySelectorAll('[data-role="assistant"]');
      if (msgs.length > 0) {
        var last = msgs[msgs.length - 1];
        if (last.textContent.includes("...") || last.textContent.includes("인식하고")) {
          last.remove();
        }
      }
    },

    _getContext: function () {
      var fab = document.getElementById("voice-agent-fab");
      if (!fab) return {};
      try {
        return JSON.parse(fab.getAttribute("data-voice-context") || "{}");
      } catch (e) {
        return {};
      }
    },

    _getCsrf: function () {
      var cookie = document.cookie.split(";").find(function (c) {
        return c.trim().startsWith("csrftoken=");
      });
      return cookie ? cookie.split("=")[1] : "";
    },

    _post: function (url, data) {
      return fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": this._getCsrf(),
        },
        body: JSON.stringify(data),
      }).then(function (r) { return r.json(); });
    },

    _resetInactivityTimer: function () {
      var self = this;
      this._clearInactivityTimer();
      this.inactivityTimer = setTimeout(function () {
        self.close();
      }, this.INACTIVITY_TIMEOUT);
    },

    _clearInactivityTimer: function () {
      if (this.inactivityTimer) {
        clearTimeout(this.inactivityTimer);
        this.inactivityTimer = null;
      }
    },
  };

  window.VoiceAgent = VoiceAgent;
})();
```

- [ ] **Step 2: Verify JS loads without syntax error**

Run: `uv run python manage.py collectstatic --noinput 2>&1 | tail -5`
Expected: Static files collected without error.

- [ ] **Step 3: Commit**

```bash
git add static/js/voice-agent.js
git commit -m "feat(p14): add voice-agent.js with MediaRecorder, conversation UI, confirm flow"
```

---

### Task 13: Run Full Test Suite

- [ ] **Step 1: Run all P14 tests**

Run: `uv run pytest tests/test_p14_voice_*.py -v`
Expected: All tests pass.

- [ ] **Step 2: Run full project test suite**

Run: `uv run pytest -v`
Expected: All tests pass including existing tests.

- [ ] **Step 3: Run lint**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: No lint or format errors.

- [ ] **Step 4: Fix any issues found**

If tests fail or lint errors exist, fix them.

- [ ] **Step 5: Final commit if fixes were needed**

```bash
git add -A
git commit -m "fix(p14): resolve test/lint issues from voice agent implementation"
```

---

## Self-Review Checklist

### Spec Coverage
- [x] URL design: `/voice/` prefix via main/urls.py -> Task 9
- [x] 9 endpoints: transcribe, intent, preview, confirm, context, history, meeting-upload, meeting-status, meeting-apply -> Task 9
- [x] Pipeline: STT -> Intent -> Entity Resolution -> Preview -> Confirm -> DB -> Tasks 2-7
- [x] 7 services: transcriber, intent_parser, entity_resolver, action_executor, context_resolver, conversation, meeting_analyzer -> Tasks 2-8
- [x] MeetingRecord model -> Task 1
- [x] Frontend: voice_button, voice_modal, voice-agent.js -> Tasks 11-12
- [x] Base.html chatbot replacement -> Task 11
- [x] Mode-based STT (command/meeting) -> Task 2
- [x] Context resolver with server-side auth -> Task 3
- [x] Entity resolution with disambiguation -> Task 5
- [x] Session management -> Task 6
- [x] Preview/confirm 2-phase pattern -> Task 7
- [x] Meeting async processing -> Task 8, 10
- [x] Meeting file validation -> Task 8
- [x] Meeting insight DB apply with provenance -> Task 8
- [x] 11 intents defined in parser -> Task 4
- [x] Intent entity mapping to real model fields -> Task 4
- [x] Management command for async processing -> Task 10

### Placeholder Scan
- No "TBD", "TODO", "implement later" found
- All code steps have complete code blocks
- All test steps have actual test code

### Type Consistency
- TranscribeMode used consistently across transcriber.py and views_voice.py
- IntentResult used consistently across intent_parser.py and views_voice.py
- CandidateResolution used consistently across entity_resolver.py and views_voice.py
- ConversationManager.SESSION_KEY used consistently
- MeetingRecord.Status choices used consistently across models, views, analyzer
