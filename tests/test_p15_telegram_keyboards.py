"""P15: Telegram keyboard and formatter tests."""

import uuid
from projects.telegram.keyboards import (
    build_approval_keyboard,
    build_contact_channel_keyboard,
    build_contact_result_keyboard,
    build_contact_save_keyboard,
    build_disambiguation_keyboard,
    parse_callback_data,
)
from projects.telegram.formatters import (
    format_approval_request,
    format_contact_step,
    format_reminder,
    format_todo_list,
)


class TestCallbackData:
    def test_parse_valid(self):
        result = parse_callback_data("n:abc12345:approve")
        assert result == {"notification_short_id": "abc12345", "action": "approve"}

    def test_parse_invalid_prefix(self):
        result = parse_callback_data("x:abc12345:approve")
        assert result is None

    def test_parse_too_few_parts(self):
        result = parse_callback_data("n:abc12345")
        assert result is None

    def test_callback_data_under_64_bytes(self):
        nid = uuid.uuid4().hex[:8]
        data = f"n:{nid}:approve"
        assert len(data.encode("utf-8")) <= 64


class TestApprovalKeyboard:
    def test_builds_4_buttons(self):
        kb = build_approval_keyboard("abc12345")
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(buttons) == 4
        actions = [parse_callback_data(b.callback_data)["action"] for b in buttons]
        assert "approve" in actions
        assert "reject" in actions
        assert "join" in actions
        assert "message" in actions

    def test_all_callback_data_under_64_bytes(self):
        kb = build_approval_keyboard("abc12345")
        for row in kb.inline_keyboard:
            for btn in row:
                assert len(btn.callback_data.encode("utf-8")) <= 64


class TestContactKeyboards:
    def test_channel_keyboard(self):
        kb = build_contact_channel_keyboard("abc12345")
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(buttons) == 3

    def test_result_keyboard(self):
        kb = build_contact_result_keyboard("abc12345")
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(buttons) == 4

    def test_save_keyboard(self):
        kb = build_contact_save_keyboard("abc12345")
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(buttons) == 1


class TestDisambiguationKeyboard:
    def test_builds_candidate_list(self):
        candidates = [
            {"id": "uuid1", "name": "홍길동", "detail": "Rayence 팀장"},
            {"id": "uuid2", "name": "홍길동", "detail": "Samsung 연구원"},
        ]
        kb = build_disambiguation_keyboard("abc12345", candidates)
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(buttons) == 2


class TestFormatters:
    def test_format_approval_request(self):
        text = format_approval_request(
            requester_name="전병권",
            project_title="Rayence 품질기획팀장",
            conflict_info="김소연의 'Rayence 품질기획파트장' (서칭중)",
            message="인사팀 이부장으로부터 직접 의뢰 받았습니다",
        )
        assert "전병권" in text
        assert "Rayence" in text
        assert "synco" in text.lower() or "[synco]" in text

    def test_format_contact_step_channel(self):
        text = format_contact_step(candidate_name="홍길동", step="channel")
        assert "홍길동" in text
        assert "연락 방법" in text

    def test_format_contact_step_result(self):
        text = format_contact_step(
            candidate_name="홍길동", step="result", channel="전화"
        )
        assert "결과" in text

    def test_format_contact_step_confirm(self):
        text = format_contact_step(
            candidate_name="홍길동",
            step="confirm",
            channel="전화",
            result="관심",
        )
        assert "홍길동" in text
        assert "전화" in text
        assert "관심" in text

    def test_format_reminder(self):
        text = format_reminder(
            reminder_type="recontact", details="홍길동 - Rayence 프로젝트"
        )
        assert "홍길동" in text

    def test_format_todo_list(self):
        actions = [
            {"text": "홍길동 재컨택", "project_title": "Rayence"},
            {"text": "김철수 서류 검토", "project_title": "Samsung"},
        ]
        text = format_todo_list(actions)
        assert "홍길동" in text
        assert "Samsung" in text

    def test_format_todo_list_empty(self):
        text = format_todo_list([])
        assert "없습니다" in text or "없음" in text
