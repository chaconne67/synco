"""P14: Voice intent parser tests."""

from unittest.mock import patch

from projects.services.voice.intent_parser import IntentResult, parse_intent
from projects.services.voice.meeting_analyzer import _call_meeting_analysis


@patch("projects.services.voice.intent_parser._call_llm_intent")
def test_removed_contact_record_intent_falls_back_to_unknown(mock_call):
    """contact_record was removed in Phase 3b. LLM returning it should map to unknown."""
    mock_call.return_value = (
        '{"intent": "contact_record", "entities": {"candidate_name": "홍길동", '
        '"channel": "전화", "result": "관심"}, "confidence": 0.95}'
    )

    result = parse_intent(
        text="홍길동 전화했는데 관심 있대",
        context={
            "page": "project_detail",
            "project_id": "some-uuid",
            "scope": "project",
        },
    )

    assert isinstance(result, IntentResult)
    assert result.intent == "unknown"


@patch("projects.services.voice.intent_parser._call_llm_intent")
def test_parse_search_intent(mock_call):
    mock_call.return_value = (
        '{"intent": "search_candidate", "entities": '
        '{"keywords": "삼성전자 출신 개발자"}, "confidence": 0.92}'
    )

    result = parse_intent(
        text="삼성전자 출신 개발자 찾아줘",
        context={"page": "dashboard", "scope": "global"},
    )

    assert result.intent == "search_candidate"
    assert "삼성전자" in result.entities["keywords"]


@patch("projects.services.voice.intent_parser._call_llm_intent")
def test_parse_navigate_intent(mock_call):
    mock_call.return_value = (
        '{"intent": "navigate", "entities": {"target_page": "projects"}, '
        '"confidence": 0.88}'
    )

    result = parse_intent(
        text="프로젝트 목록으로 가줘",
        context={"page": "dashboard", "scope": "global"},
    )

    assert result.intent == "navigate"
    assert result.entities["target_page"] == "projects"


@patch("projects.services.voice.intent_parser._call_llm_intent")
def test_parse_unknown_intent(mock_call):
    mock_call.return_value = '{"intent": "unknown", "entities": {}, "confidence": 0.3}'

    result = parse_intent(
        text="오늘 날씨 어때",
        context={"page": "dashboard", "scope": "global"},
    )

    assert result.intent == "unknown"
    assert result.confidence < 0.5


@patch("projects.services.voice.meeting_analyzer.call_llm")
def test_meeting_analysis_defaults_to_common_llm(mock_call, settings):
    settings.VOICE_MEETING_ANALYSIS_PROVIDER = "llm"
    mock_call.return_value = '{"interest_level": "높음"}'

    result = _call_meeting_analysis("전사 텍스트")

    assert result == '{"interest_level": "높음"}'
    mock_call.assert_called_once()
