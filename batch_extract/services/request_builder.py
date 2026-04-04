from __future__ import annotations

import json

from candidates.services.gemini_extraction import GEMINI_SYSTEM_PROMPT
from candidates.services.llm_extraction import build_extraction_prompt


def build_request_line(
    *,
    request_key: str,
    resume_text: str,
    file_reference_date: str | None = None,
) -> str:
    prompt = build_extraction_prompt(
        resume_text,
        file_reference_date=file_reference_date,
    )
    payload = {
        "key": request_key,
        "request": {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "system_instruction": {
                "parts": [{"text": GEMINI_SYSTEM_PROMPT}],
            },
            "generation_config": {
                "temperature": 0.3,
                "max_output_tokens": 4000,
            },
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def extract_text_response(parsed_line: dict) -> str:
    response = parsed_line.get("response") or {}
    candidates = response.get("candidates") or []
    if not candidates:
        return ""
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    texts = []
    for part in parts:
        text = part.get("text")
        if text:
            texts.append(text)
    return "\n".join(texts).strip()
