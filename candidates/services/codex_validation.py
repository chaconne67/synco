"""Codex CLI cross-validation for resume extraction results."""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)

CODEX_VALIDATION_PROMPT = """당신은 이력서 추출 결과 검증 전문가입니다.

## 작업
원본 이력서 텍스트와 AI가 추출한 구조화 JSON을 비교하여 누락, 오류, 환각(hallucination)을 찾아내세요.

## 검증 규칙
1. 원본에 있는 정보가 추출 결과에 누락되었는지 확인 (특히 경력 날짜, 회사명, 직책)
2. 추출된 값이 원본과 다른지 확인
3. 원본에 없는 정보가 추출 결과에 추가되었는지 확인 (환각)
4. 파일명 메타데이터와 추출 결과가 일치하는지 확인

## 원인 분류 (root_cause)
- "text_extraction": 원본 텍스트에 해당 정보가 아예 없음 → 텍스트 추출기가 놓침
- "llm_parsing": 원본 텍스트에 정보가 있는데 AI가 놓치거나 틀림
- "ambiguous_source": 원본 자체가 모호하거나 정보 부족

## 출력 JSON 스키마
```json
{
  "verdict": "pass 또는 fail",
  "issues": [
    {
      "field": "필드 경로 (예: careers[0].start_date)",
      "type": "missing | incorrect | hallucinated",
      "evidence": "근거 설명",
      "root_cause": "text_extraction | llm_parsing | ambiguous_source",
      "severity": "critical | warning",
      "suggested_value": "올바른 값 (알 수 있는 경우)"
    }
  ],
  "field_scores": {"name": 0.0-1.0, "careers": 0.0-1.0, ...},
  "overall_score": 0.0-1.0
}
```

verdict 판정:
- critical issue가 0개이고 overall_score >= 0.85 → "pass"
- 그 외 → "fail"

JSON만 출력하세요."""


def _build_codex_prompt(raw_text: str, extracted: dict, filename_meta: dict) -> str:
    return (
        f"## 원본 이력서 텍스트\n```\n{raw_text[:6000]}\n```\n\n"
        f"## AI 추출 결과 JSON\n```json\n{json.dumps(extracted, ensure_ascii=False, indent=2)}\n```\n\n"
        f"## 파일명 메타데이터\n```json\n{json.dumps(filename_meta, ensure_ascii=False)}\n```\n\n"
        "위 정보를 비교하여 검증 결과 JSON을 출력하세요."
    )


def _call_codex_cli(prompt: str, timeout: int = 60) -> str:
    """Call Claude Haiku via claude CLI for cross-validation.

    Uses claude CLI (already authenticated) with haiku model for fast,
    low-cost validation of extraction results.
    """
    full_prompt = CODEX_VALIDATION_PROMPT + "\n\n" + prompt
    result = subprocess.run(
        ["claude", "--print", "--model", "haiku", "--max-turns", "1"],
        input=full_prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude Haiku error: {result.stderr[:500]}")
    return result.stdout.strip()


def _parse_codex_response(response_text: str) -> dict:
    """Extract JSON from Codex response."""
    text = response_text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def validate_with_codex(
    raw_text: str,
    extracted: dict,
    filename_meta: dict,
    timeout: int = 60,
) -> dict:
    """Cross-validate extraction results using Codex CLI.

    Returns dict with: verdict, issues, field_scores, overall_score.
    On Codex failure, returns a fallback error result.
    """
    try:
        prompt = _build_codex_prompt(raw_text, extracted, filename_meta)
        response = _call_codex_cli(prompt, timeout=timeout)
        result = _parse_codex_response(response)

        result.setdefault("verdict", "fail")
        result.setdefault("issues", [])
        result.setdefault("field_scores", {})
        result.setdefault("overall_score", 0.0)

        return result

    except Exception:
        logger.exception("Codex validation failed")
        return {
            "verdict": "error",
            "issues": [],
            "field_scores": {},
            "overall_score": 0.0,
        }
