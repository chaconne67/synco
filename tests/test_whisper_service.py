import io
from unittest.mock import patch, MagicMock

from candidates.services.whisper import transcribe_audio


@patch("candidates.services.whisper._get_openai_client")
def test_transcribe_audio(mock_client_fn):
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = MagicMock(
        text="회계 경력 10년 이상"
    )
    mock_client_fn.return_value = mock_client

    audio_file = io.BytesIO(b"fake audio data")
    audio_file.name = "test.webm"
    result = transcribe_audio(audio_file)

    assert result == "회계 경력 10년 이상"
    mock_client.audio.transcriptions.create.assert_called_once()
