"""LLM 호출 토큰 사용량 누적기.

이력서 추출 테스트(시간·비용·품질 비교) 용도. extract 명령이 시작 시 reset,
종료 시 snapshot을 JSON으로 저장합니다. 운영 중 일반 사용에는 영향이 없으나
프로세스 단위 누적이므로 동시 실행을 분리해야 정확합니다.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_state: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "calls": 0}


def reset() -> None:
    with _lock:
        _state["input_tokens"] = 0
        _state["output_tokens"] = 0
        _state["calls"] = 0


def add(input_tokens: int, output_tokens: int) -> None:
    """LLM 호출 한 번의 입력/출력 토큰을 누적."""
    if not input_tokens and not output_tokens:
        return
    with _lock:
        _state["input_tokens"] += int(input_tokens or 0)
        _state["output_tokens"] += int(output_tokens or 0)
        _state["calls"] += 1


def snapshot() -> dict[str, int]:
    with _lock:
        return dict(_state)


def add_from_gemini_response(response) -> None:
    """google.genai response 객체에서 토큰 추출해 누적."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return
    add(
        getattr(usage, "prompt_token_count", 0) or 0,
        getattr(usage, "candidates_token_count", 0) or 0,
    )


def add_from_batch_result_line(parsed: dict) -> None:
    """Gemini Batch API result line의 usageMetadata에서 토큰 추출."""
    response = parsed.get("response") or {}
    usage = response.get("usageMetadata") or response.get("usage_metadata") or {}
    add(
        usage.get("promptTokenCount") or usage.get("prompt_token_count") or 0,
        usage.get("candidatesTokenCount") or usage.get("candidates_token_count") or 0,
    )


def add_from_openai_response(response) -> None:
    """OpenAI ChatCompletion response의 usage에서 토큰 추출."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    add(
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
    )
