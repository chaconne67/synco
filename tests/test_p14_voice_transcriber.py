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
