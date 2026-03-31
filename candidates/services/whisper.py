"""Whisper API speech-to-text service."""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_client = None


def _get_openai_client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def transcribe_audio(audio_file) -> str:
    """Transcribe audio file to text using Whisper API.

    Args:
        audio_file: File-like object with .name attribute (webm/mp4/ogg).

    Returns:
        Transcribed text string.

    Raises:
        RuntimeError on API failure.
    """
    try:
        client = _get_openai_client()
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="ko",
        )
        return transcript.text
    except Exception as e:
        logger.exception("Whisper transcription failed")
        raise RuntimeError(f"음성 인식에 실패했습니다: {e}") from e
