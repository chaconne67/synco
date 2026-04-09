"""Inline Keyboard builders for Telegram bot.

All callback_data values MUST be under 64 bytes (Telegram API limit).
Format: "n:{notification_short_id}:{action}"
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _cb(short_id: str, action: str) -> str:
    """Build callback_data string. Asserts 64-byte limit."""
    data = f"n:{short_id}:{action}"
    assert len(data.encode("utf-8")) <= 64, (
        f"callback_data too long: {len(data.encode('utf-8'))} bytes"
    )
    return data


def parse_callback_data(data: str) -> dict | None:
    """Parse callback_data string into components.

    Returns {"notification_short_id": str, "action": str} or None if invalid.
    """
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "n":
        return None
    return {"notification_short_id": parts[1], "action": parts[2]}


def build_approval_keyboard(short_id: str) -> InlineKeyboardMarkup:
    """Build approval request keyboard with 4 action buttons."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ 승인", callback_data=_cb(short_id, "approve")),
                InlineKeyboardButton("🔗 합류", callback_data=_cb(short_id, "join")),
            ],
            [
                InlineKeyboardButton(
                    "💬 메시지", callback_data=_cb(short_id, "message")
                ),
                InlineKeyboardButton("❌ 반려", callback_data=_cb(short_id, "reject")),
            ],
        ]
    )


def build_contact_channel_keyboard(short_id: str) -> InlineKeyboardMarkup:
    """Build contact channel selection keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📞 전화", callback_data=_cb(short_id, "ch_phone")
                ),
                InlineKeyboardButton(
                    "💬 카톡", callback_data=_cb(short_id, "ch_kakao")
                ),
                InlineKeyboardButton(
                    "📧 이메일", callback_data=_cb(short_id, "ch_email")
                ),
            ],
        ]
    )


def build_contact_result_keyboard(short_id: str) -> InlineKeyboardMarkup:
    """Build contact result selection keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "😊 관심있음", callback_data=_cb(short_id, "rs_interest")
                ),
                InlineKeyboardButton(
                    "😐 미응답", callback_data=_cb(short_id, "rs_noresp")
                ),
            ],
            [
                InlineKeyboardButton("🤔 보류", callback_data=_cb(short_id, "rs_hold")),
                InlineKeyboardButton(
                    "❌ 거절", callback_data=_cb(short_id, "rs_reject")
                ),
            ],
        ]
    )


def build_contact_save_keyboard(short_id: str) -> InlineKeyboardMarkup:
    """Build contact save (skip memo) keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💾 저장 — 메모 없이", callback_data=_cb(short_id, "save")
                )
            ],
        ]
    )


def build_disambiguation_keyboard(
    short_id: str, candidates: list[dict]
) -> InlineKeyboardMarkup:
    """Build candidate disambiguation keyboard.

    Each candidate dict: {"id": str, "name": str, "detail": str}
    """
    buttons = []
    for i, c in enumerate(candidates[:5]):
        label = f"{i + 1}. {c['name']} - {c['detail']}"
        if len(label) > 40:
            label = label[:37] + "..."
        buttons.append(
            [InlineKeyboardButton(label, callback_data=_cb(short_id, f"sel_{i}"))]
        )
    return InlineKeyboardMarkup(buttons)
