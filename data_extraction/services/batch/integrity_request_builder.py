from __future__ import annotations

import json

from data_extraction.services.extraction.prompts import (
    CAREER_OUTPUT_SCHEMA,
    CAREER_SYSTEM_PROMPT,
    EDUCATION_OUTPUT_SCHEMA,
    EDUCATION_SYSTEM_PROMPT,
    STEP1_SYSTEM_PROMPT,
    build_step1_prompt,
)


def build_step1_request_line(
    *,
    request_key: str,
    resume_text: str,
    file_name: str | None = None,
) -> str:
    return _build_request_line(
        request_key=request_key,
        system=STEP1_SYSTEM_PROMPT,
        prompt=build_step1_prompt(resume_text, file_name=file_name),
        max_output_tokens=6000,
    )


def build_step2_career_request_line(
    *,
    request_key: str,
    careers: list[dict],
) -> str:
    entries_json = json.dumps(careers, ensure_ascii=False, indent=2)
    prompt = (
        f"아래 {len(careers)}개 경력 항목을 정규화하세요. "
        "같은 회사의 중복 항목은 하나로 통합하세요.\n\n"
        f"## 출력 스키마\n```\n{CAREER_OUTPUT_SCHEMA}\n```\n\n"
        f"## 입력 항목\n```json\n{entries_json}\n```\n\n"
        "JSON만 출력하세요."
    )
    return _build_request_line(
        request_key=request_key,
        system=CAREER_SYSTEM_PROMPT,
        prompt=prompt,
        max_output_tokens=4000,
    )


def build_step2_education_request_line(
    *,
    request_key: str,
    educations: list[dict],
) -> str:
    entries_json = json.dumps(educations, ensure_ascii=False, indent=2)
    prompt = (
        f"아래 {len(educations)}개 학력 항목을 정규화하고 위조 의심을 탐지하세요.\n\n"
        f"## 출력 스키마\n```\n{EDUCATION_OUTPUT_SCHEMA}\n```\n\n"
        f"## 입력 항목\n```json\n{entries_json}\n```\n\n"
        "JSON만 출력하세요."
    )
    return _build_request_line(
        request_key=request_key,
        system=EDUCATION_SYSTEM_PROMPT,
        prompt=prompt,
        max_output_tokens=2000,
    )


def _build_request_line(
    *,
    request_key: str,
    system: str,
    prompt: str,
    max_output_tokens: int,
) -> str:
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
                "parts": [{"text": system}],
            },
            "generation_config": {
                "temperature": 0.2,
                "max_output_tokens": max_output_tokens,
                "response_mime_type": "application/json",
            },
        },
    }
    return json.dumps(payload, ensure_ascii=False)
