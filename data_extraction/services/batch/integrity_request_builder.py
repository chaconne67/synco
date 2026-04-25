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
    feedback: str | None = None,
) -> str:
    return _build_request_line(
        request_key=request_key,
        system=STEP1_SYSTEM_PROMPT,
        prompt=build_step1_prompt(resume_text, feedback=feedback, file_name=file_name),
        max_output_tokens=6000,
    )


def build_step2_career_request_line(
    *,
    request_key: str,
    careers: list[dict],
    feedback: str | None = None,
) -> str:
    entries_json = json.dumps(careers, ensure_ascii=False, indent=2)
    count_note = (
        "입력 항목이 0개이면 careers는 빈 배열, flags도 빈 배열로 반환하세요."
        if len(careers) == 0
        else f"입력 항목은 총 {len(careers)}개입니다."
    )
    feedback_block = f"\n## 피드백\n{feedback}\n" if feedback else ""
    prompt = (
        "아래 Step 1 경력 항목들에 대해 시스템 지시(통합·날짜 정규화·"
        "종료일 추정·필드 보존·flag 작성)를 모두 수행하여 결과를 반환하세요.\n"
        f"{count_note}{feedback_block}\n\n"
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
    count_note = (
        "입력 항목이 0개이면 educations는 빈 배열, flags도 빈 배열로 반환하세요."
        if len(educations) == 0
        else f"입력 항목은 총 {len(educations)}개입니다."
    )
    prompt = (
        "아래 Step 1 학력 항목들에 대해 시스템 지시(통합·status 보존·위조 의심 "
        "탐지·flag 작성)를 모두 수행하여 결과를 반환하세요.\n"
        f"{count_note}\n\n"
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
