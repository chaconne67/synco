"""P14: Voice intent parser tests."""

from unittest.mock import MagicMock, patch

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
        context={
            "page": "project_detail",
            "project_id": "some-uuid",
            "scope": "project",
        },
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
