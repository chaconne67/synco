"""Whisper API speech-to-text service."""

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

_client = None

# Known Whisper hallucination patterns for silent/empty audio (Korean)
HALLUCINATION_PATTERNS = [
    "시청해 주셔서 감사합니다",
    "시청해주셔서 감사합니다",
    "구독과 좋아요",
    "구독 부탁드립니다",
    "자막 제공",
    "자막을 제공",
    "다음 영상에서 만나요",
    "영상이 도움이 되셨다면",
    "좋아요와 구독",
    "MBC 뉴스",
    "KBS 뉴스",
    "SBS 뉴스",
    # Whisper echoes the prompt itself when audio is silent
    "후보자 검색 음성 명령입니다",
    "찾아줘, 검색해줘, 보여줘, 골라줘, 뽑아줘",
]

_whisper_prompt_cache = None
_whisper_prompt_ts = 0


def _build_whisper_prompt() -> str:
    """Build Whisper prompt dynamically from DB data. Cached for 10 minutes."""
    import time

    global _whisper_prompt_cache, _whisper_prompt_ts
    now = time.time()
    if _whisper_prompt_cache and (now - _whisper_prompt_ts) < 600:
        return _whisper_prompt_cache

    from django.db import connection

    parts = ["후보자 검색 음성 명령입니다."]
    parts.append(
        "SKY, 인서울, 서성한, 중경외시, 건동홍숙이, 국숭세단, 과기특, 지거국, 명문대, 이공계명문"
    )

    try:
        with connection.cursor() as cursor:
            # Categories
            cursor.execute("SELECT name FROM categories ORDER BY name LIMIT 30")
            cats = [r[0] for r in cursor.fetchall()]
            if cats:
                parts.append(", ".join(cats))

            # Top companies
            cursor.execute(
                "SELECT DISTINCT company FROM careers "
                "WHERE company != '' ORDER BY company LIMIT 30"
            )
            companies = [r[0] for r in cursor.fetchall()]
            if companies:
                parts.append(", ".join(companies[:20]))

            # Top institutions
            cursor.execute(
                "SELECT DISTINCT institution FROM educations "
                "WHERE institution != '' ORDER BY institution LIMIT 20"
            )
            schools = [r[0] for r in cursor.fetchall()]
            if schools:
                parts.append(", ".join(schools[:15]))
    except Exception:
        logger.warning("Failed to build dynamic Whisper prompt, using fallback")
        parts.append("경력, 학력, 회사, 검색")

    prompt = " ".join(parts)
    _whisper_prompt_cache = prompt
    _whisper_prompt_ts = now
    return prompt


def _get_openai_client():
    global _client
    if _client is None:
        from openai import OpenAI

        api_key = settings.OPENAI_API_KEY
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY가 설정되지 않았습니다. 환경변수를 확인해주세요."
            )
        _client = OpenAI(api_key=api_key, timeout=httpx.Timeout(30.0))
    return _client


def _is_hallucination(text: str) -> bool:
    """Check if transcribed text matches known Whisper hallucination patterns."""
    if not text:
        return True
    text_lower = text.strip().lower()
    # Check known patterns
    if any(pattern in text_lower for pattern in HALLUCINATION_PATTERNS):
        return True
    # Check if Whisper echoed back the prompt itself (>50% overlap)
    prompt_lower = _build_whisper_prompt().lower()
    if len(text_lower) > 20 and text_lower in prompt_lower:
        return True
    return False


def transcribe_audio(audio_file) -> str:
    """Transcribe audio file to text using Whisper API.

    Args:
        audio_file: File-like object with .name attribute (webm/mp4/ogg).

    Returns:
        Transcribed text string, or empty string if no speech detected.

    Raises:
        RuntimeError on API failure.
    """
    try:
        client = _get_openai_client()
        # OpenAI SDK requires (filename, bytes, content_type) tuple for Django uploads
        file_tuple = (
            getattr(audio_file, "name", "voice.webm"),
            audio_file.read(),
            getattr(audio_file, "content_type", "audio/webm"),
        )
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",
            file=file_tuple,
            language="ko",
            prompt=_build_whisper_prompt(),
        )
        text = transcript.text.strip()

        if not text:
            return ""

        if _is_hallucination(text):
            logger.info("Whisper hallucination detected and filtered: %s", text)
            return ""

        return text
    except Exception as e:
        logger.exception("Whisper transcription failed")
        raise RuntimeError(f"음성 인식에 실패했습니다: {e}") from e
