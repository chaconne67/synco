"""Meeting recording analyzer: transcribe -> LLM analysis -> DB apply."""

from __future__ import annotations

import logging
import subprocess

from django.conf import settings
from django.utils import timezone

from data_extraction.services.extraction.sanitizers import parse_llm_json
from projects.models import MeetingRecord
from projects.services.voice.transcriber import TranscribeMode, transcribe

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {".mp3", ".m4a", ".wav", ".webm"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_DURATION_MINUTES = 120

GEMINI_MODEL = "gemini-2.5-flash"

FIELD_LABELS = {
    "interest_level": "이직 의향",
    "current_salary": "현재 연봉",
    "desired_salary": "희망 연봉",
    "available_date": "이직 가능 시기",
    "career_highlights": "경력 하이라이트",
    "concerns": "우려 사항",
    "action_items": "액션 아이템",
    "mood": "분위기",
    "notes": "기타 메모",
}

# Amendment A11: Interest level -> result mapping
INTEREST_TO_RESULT = {
    "높음": "관심",
    "보통": "응답",
    "낮음": "보류",
}

ANALYSIS_PROMPT = """\
다음은 헤드헌팅 미팅 녹음 전사 텍스트입니다. 분석하여 아래 JSON 형식으로 응답하세요.

전사 텍스트:
{transcript}

응답 형식 (JSON만 반환):
{{
  "interest_level": "높음/보통/낮음 중 하나",
  "current_salary": "현재 연봉 (언급된 경우)",
  "desired_salary": "희망 연봉 (언급된 경우)",
  "available_date": "이직 가능 시기 (언급된 경우)",
  "career_highlights": "주요 경력 하이라이트",
  "concerns": "우려 사항이나 걱정",
  "action_items": "후속 조치 사항",
  "mood": "전반적 분위기 (긍정적/중립/부정적)",
  "notes": "기타 중요 메모"
}}
"""


# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


# ---------------------------------------------------------------------------
# Validation (Amendment A9: duration check)
# ---------------------------------------------------------------------------


def _get_audio_duration(file_path: str) -> float | None:
    """Best-effort duration check via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return None


def validate_meeting_file(f) -> list[str]:
    """Validate uploaded meeting file for extension, size, and duration."""
    errors: list[str] = []

    # Extension check
    name = getattr(f, "name", "")
    ext = ""
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        errors.append(f"지원하지 않는 파일 형식입니다. 허용 형식: {allowed}")

    # Size check
    size = getattr(f, "size", 0)
    if size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        errors.append(f"파일 크기가 {max_mb}MB를 초과합니다.")

    # Duration check (best-effort, Amendment A9)
    if hasattr(f, "temporary_file_path"):
        duration = _get_audio_duration(f.temporary_file_path())
        if duration and duration > MAX_DURATION_MINUTES * 60:
            errors.append(f"녹음 길이가 {MAX_DURATION_MINUTES}분을 초과합니다.")

    return errors


# ---------------------------------------------------------------------------
# Analyze meeting pipeline
# ---------------------------------------------------------------------------


def analyze_meeting(meeting_record_id: int | str) -> None:
    """Full pipeline: transcribe audio -> LLM analysis -> save to MeetingRecord.

    Status transitions: UPLOADED -> TRANSCRIBING -> ANALYZING -> READY (or FAILED).
    """
    record = MeetingRecord.objects.get(pk=meeting_record_id)

    try:
        # Phase 1: Transcribe
        record.status = MeetingRecord.Status.TRANSCRIBING
        record.save(update_fields=["status"])

        transcript_text = transcribe(record.audio_file, mode=TranscribeMode.MEETING)
        if not transcript_text:
            record.status = MeetingRecord.Status.FAILED
            record.error_message = "음성 인식 결과가 없습니다."
            record.save(update_fields=["status", "error_message"])
            return

        record.transcript = transcript_text
        record.save(update_fields=["transcript"])

        # Phase 2: LLM Analysis
        record.status = MeetingRecord.Status.ANALYZING
        record.save(update_fields=["status"])

        client = _get_gemini_client()
        prompt = ANALYSIS_PROMPT.format(transcript=transcript_text)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt],
        )

        analysis = parse_llm_json(response.text)
        if analysis is None:
            record.status = MeetingRecord.Status.FAILED
            record.error_message = "분석 결과를 파싱할 수 없습니다."
            record.save(update_fields=["status", "error_message"])
            return

        record.analysis_json = analysis
        record.status = MeetingRecord.Status.READY
        record.save(update_fields=["analysis_json", "status"])

    except Exception as e:
        logger.exception("Meeting analysis failed for record %s", meeting_record_id)
        record.status = MeetingRecord.Status.FAILED
        record.error_message = str(e)
        record.save(update_fields=["status", "error_message"])


# ---------------------------------------------------------------------------
# Apply insights (Amendment A11: field-specific handling)
# ---------------------------------------------------------------------------


def apply_meeting_insights(
    *, record: MeetingRecord, selected_fields: list[str], user
) -> None:
    """Apply selected analysis fields to the database.

    Updates MeetingRecord status to APPLIED.
    """
    record.status = MeetingRecord.Status.APPLIED
    record.applied_at = timezone.now()
    record.applied_by = user
    record.save(update_fields=["status", "applied_at", "applied_by"])
