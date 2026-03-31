"""Few-shot example store: query and format examples for LLM prompt injection."""

from __future__ import annotations

import json

from candidates.models import ParseExample


def get_fewshot_examples(
    category: str, max_count: int = 3
) -> list[ParseExample]:
    """Get active few-shot examples for a category, newest first."""
    return list(
        ParseExample.objects.filter(
            category=category,
            is_active=True,
        ).order_by("-created_at")[:max_count]
    )


def format_fewshot_prompt(examples: list[ParseExample]) -> str:
    """Format few-shot examples as a prompt section. Returns empty string if no examples."""
    if not examples:
        return ""

    lines = ["\n\n## 참고: 유사 이력서 추출 예시\n"]
    for i, ex in enumerate(examples, 1):
        lines.append(f"### 예시 {i} ({ex.resume_pattern})")
        lines.append(f"입력:\n```\n{ex.input_excerpt}\n```")
        lines.append(
            f"올바른 추출:\n```json\n"
            f"{json.dumps(ex.correct_output, ensure_ascii=False, indent=2)}\n```\n"
        )
    return "\n".join(lines)
