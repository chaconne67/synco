from unittest.mock import patch, MagicMock


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
    mock_response.choices[
        0
    ].message.content = '{"title": "자료 전달", "due_date": "2026-04-01"}'

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
