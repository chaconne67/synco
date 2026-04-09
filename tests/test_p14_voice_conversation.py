"""P14: Voice conversation session tests."""
import time
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


# Amendment A4 tests
def test_inactivity_auto_reset(session):
    mgr = ConversationManager(session)
    conv = mgr.get_or_create()
    conv["last_active"] = time.time() - 301  # 5 min + 1 sec ago
    session.modified = False

    conv2 = mgr.get_or_create()
    # Should be a fresh conversation (different id)
    assert conv2["turns"] == []
    assert conv2["pending_intent"] is None


def test_touch_updates_last_active(session):
    mgr = ConversationManager(session)
    mgr.get_or_create()
    before = time.time()
    mgr.touch()
    conv = mgr.get_or_create()
    assert conv["last_active"] >= before
