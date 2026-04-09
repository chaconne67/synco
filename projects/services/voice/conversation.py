"""Multi-turn conversation session manager."""

from __future__ import annotations

import time
import uuid
from typing import Any

SESSION_KEY = "voice_conversation"
MAX_TURNS = 50  # Prevent session bloat
INACTIVITY_TIMEOUT = 300  # 5 minutes


class ConversationManager:
    """Manages voice conversation state in Django session."""

    def __init__(self, session: Any) -> None:
        self._session = session

    def get_or_create(self) -> dict[str, Any]:
        """Get existing conversation or create a new one.

        Amendment A4: Auto-resets after 5 minutes of inactivity.
        """
        if SESSION_KEY in self._session:
            conv = self._session[SESSION_KEY]
            last_active = conv.get("last_active", 0)
            if time.time() - last_active > INACTIVITY_TIMEOUT:
                del self._session[SESSION_KEY]
                return self.get_or_create()
            return conv

        self._session[SESSION_KEY] = {
            "id": str(uuid.uuid4()),
            "turns": [],
            "pending_intent": None,
            "collected_entities": {},
            "missing_fields": [],
            "preview_token": None,
            "last_active": time.time(),
        }
        return self._session[SESSION_KEY]

    def add_turn(self, *, role: str, text: str) -> None:
        """Add a conversation turn."""
        conv = self.get_or_create()
        conv["turns"].append({"role": role, "text": text})
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

    def touch(self) -> None:
        """Update last activity timestamp."""
        conv = self.get_or_create()
        conv["last_active"] = time.time()
        self._session.modified = True

    def reset(self) -> None:
        """Clear conversation state."""
        if SESSION_KEY in self._session:
            del self._session[SESSION_KEY]
