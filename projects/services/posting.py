"""공지 생성 서비스: AI 텍스트 생성 + 파일명 규칙."""

import json
import logging
from datetime import date

from django.conf import settings
from google import genai

from .posting_prompts import POSTING_SYSTEM_PROMPT, POSTING_USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-preview-05-20"


def _get_gemini_client() -> genai.Client:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in settings")
    return genai.Client(api_key=api_key)


def generate_posting(project, max_retries: int = 3) -> str:
    """JD + 고객사 정보를 기반으로 잡포털 공지 텍스트를 생성한다.

    Args:
        project: Project instance (client, jd_raw_text/jd_text, requirements 참조)
        max_retries: Gemini API 재시도 횟수

    Returns:
        생성된 공지 텍스트 (str)

    Raises:
        ValueError: JD 텍스트가 없는 경우
        RuntimeError: Gemini API 호출 실패 (max_retries 초과)
    """
    jd_text = project.jd_raw_text or project.jd_text
    if not jd_text or not jd_text.strip():
        raise ValueError("JD를 먼저 등록해주세요.")

    client = project.client
    requirements_text = ""
    if project.requirements:
        requirements_text = json.dumps(
            project.requirements, ensure_ascii=False, indent=2
        )
    else:
        requirements_text = "(구조화된 요구조건 없음 — JD 원문에서 직접 추출하세요)"

    user_prompt = POSTING_USER_PROMPT_TEMPLATE.format(
        jd_text=jd_text,
        client_name=client.name if client else "",
        client_industry=client.industry if client else "",
        client_size=client.get_size_display() if client and client.size else "",
        client_region=client.region if client else "",
        requirements_text=requirements_text,
    )

    gemini_client = _get_gemini_client()

    for attempt in range(max_retries):
        try:
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=POSTING_SYSTEM_PROMPT,
                    max_output_tokens=4000,
                    temperature=0.3,
                ),
            )

            text = response.text.strip()
            if not text:
                logger.warning(
                    "Posting generation: empty response (attempt %d/%d)",
                    attempt + 1,
                    max_retries,
                )
                continue

            return text

        except Exception:
            logger.warning(
                "Posting generation failed (attempt %d/%d)",
                attempt + 1,
                max_retries,
                exc_info=True,
            )

    raise RuntimeError("공지 생성에 실패했습니다. 잠시 후 다시 시도해주세요.")


def get_posting_filename(project, user) -> str:
    """파일명 규칙: (YYMMDD) 회사명_포지션명_담당자명.txt

    Args:
        project: Project instance
        user: User instance (request.user)

    Returns:
        파일명 문자열
    """
    today = date.today()
    date_str = today.strftime("%y%m%d")

    client_name = project.client.name if project.client else "Unknown"
    position = project.title or "포지션미정"
    consultant_name = user.get_full_name() or user.username

    return f"({date_str}) {client_name}_{position}_{consultant_name}.txt"
