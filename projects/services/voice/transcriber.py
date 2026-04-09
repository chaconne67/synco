"""Voice transcriber with mode-based prompt/filter switching."""

import enum
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

_client = None


class TranscribeMode(str, enum.Enum):
    COMMAND = "command"
    MEETING = "meeting"


# Prompts per mode
PROMPTS = {
    TranscribeMode.COMMAND: (
        "헤드헌팅 업무 음성 명령입니다. "
        "프로젝트, 컨택, 면접, 오퍼, 추천, 후보자, 이력서, 연봉, 채용, 헤드헌터. "
        "전화, 문자, 카톡, 이메일, LinkedIn. "
        "관심, 거절, 미응답, 응답, 보류, 예정."
    ),
    TranscribeMode.MEETING: (
        "헤드헌팅 미팅 녹음입니다. "
        "후보자 면담, 연봉 협상, 경력 상담, 이직 의향, 포지션, 채용 프로세스. "
        "현재 연봉, 희망 연봉, 이직 가능 시기, 경력 하이라이트, 우려 사항."
    ),
}

# Timeouts per mode (seconds)
TIMEOUTS = {
    TranscribeMode.COMMAND: 30.0,
    TranscribeMode.MEETING: 300.0,
}

# Hallucination patterns common across modes
COMMON_HALLUCINATIONS = [
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
]

# Additional hallucinations per mode
MODE_HALLUCINATIONS = {
    TranscribeMode.COMMAND: [
        "헤드헌팅 업무 음성 명령입니다",
    ],
    TranscribeMode.MEETING: [
        "헤드헌팅 미팅 녹음입니다",
    ],
}


def _get_openai_client():
    global _client
    if _client is None:
        from openai import OpenAI

        api_key = settings.OPENAI_API_KEY
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY가 설정되지 않았습니다. 환경변수를 확인해주세요."
            )
        _client = OpenAI(api_key=api_key, timeout=httpx.Timeout(300.0))
    return _client


def _is_hallucination(text: str, mode: TranscribeMode) -> bool:
    if not text:
        return True
    text_lower = text.strip().lower()
    all_patterns = COMMON_HALLUCINATIONS + MODE_HALLUCINATIONS.get(mode, [])
    if any(p in text_lower for p in all_patterns):
        return True
    prompt_lower = PROMPTS[mode].lower()
    if len(text_lower) > 20 and text_lower in prompt_lower:
        return True
    return False


def transcribe(audio_file, *, mode: TranscribeMode = TranscribeMode.COMMAND) -> str:
    """Transcribe audio file using Whisper with mode-specific prompt/filter.

    Args:
        audio_file: File-like object with .name attribute.
        mode: TranscribeMode.COMMAND or TranscribeMode.MEETING.

    Returns:
        Transcribed text, or empty string if no speech detected.

    Raises:
        RuntimeError on API failure.
    """
    try:
        client = _get_openai_client()
        file_tuple = (
            getattr(audio_file, "name", "voice.webm"),
            audio_file.read(),
            getattr(audio_file, "content_type", "audio/webm"),
        )
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",
            file=file_tuple,
            language="ko",
            prompt=PROMPTS[mode],
        )
        text = transcript.text.strip()

        if not text:
            return ""

        if _is_hallucination(text, mode):
            logger.info("Voice agent hallucination filtered (%s): %s", mode.value, text)
            return ""

        return text
    except Exception as e:
        logger.exception("Voice transcription failed (mode=%s)", mode.value)
        raise RuntimeError(f"음성 인식에 실패했습니다: {e}") from e
