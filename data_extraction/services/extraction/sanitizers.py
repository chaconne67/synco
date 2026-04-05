"""Pre-processing and post-processing sanitizers for LLM extraction.

Pre-processing: clean input text before sending to LLM.
Post-processing: recover valid data from malformed LLM responses.
"""

from __future__ import annotations

import json
import re


# ===========================================================================
# Pre-processing: input text → LLM
# ===========================================================================


def sanitize_input_text(text: str) -> str:
    """Clean resume text before sending to LLM.

    Handles encoding artifacts, control characters, and formatting noise
    that can confuse the model or waste tokens.
    """
    if not text:
        return ""

    # 1) BOM removal
    text = text.replace("\ufeff", "")

    # 2) Control characters (keep \n \r \t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # 3) Null-like patterns in extracted tables
    text = re.sub(r"\x00", "", text)

    # 5) Excessive whitespace (but preserve single newlines for structure)
    text = re.sub(r"[ \t]+", " ", text)  # multiple spaces/tabs → single space
    text = re.sub(r"\n{4,}", "\n\n\n", text)  # 4+ newlines → 3
    text = re.sub(r"(\r\n|\r)", "\n", text)  # normalize line endings

    # 6) Strip lines that are only whitespace or pipe/dash table borders
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip pure table border lines: ---|---|--- or ===|===
        if stripped and re.match(r"^[-=|+\s]+$", stripped) and len(stripped) > 3:
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)

    # 7) Truncate extremely long text to avoid token limits
    #    Gemini flash-lite context is ~130K tokens ≈ ~400K chars for Korean
    MAX_CHARS = 200_000
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]

    return text.strip()


# ===========================================================================
# Post-processing: LLM response → valid JSON dict
# ===========================================================================


def parse_llm_json(text: str) -> dict | None:
    """Parse JSON from LLM response, recovering from common malformations.

    Handles:
    - Control characters in JSON string values
    - BOM prefix
    - Markdown code block wrapper (```json ... ```)
    - Extra closing braces/brackets (Gemini duplication)
    - Single-element list wrapper ([{...}])
    - Trailing commas
    - NaN/Infinity literals
    - Truncated JSON (attempts partial recovery)

    Returns parsed dict, or None if unrecoverable.
    """
    if not text or not text.strip():
        return None

    # 1) Strip BOM
    text = text.replace("\ufeff", "")

    # 2) Strip markdown code block wrapper
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    text = re.sub(r"\n?```\s*$", "", text.strip())

    # 3) Remove control characters (keep \n \r \t for readability)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

    # 4) Replace NaN/Infinity (not valid JSON)
    text = re.sub(r"\bNaN\b", "null", text)
    text = re.sub(r"\bInfinity\b", "null", text)
    text = re.sub(r"-Infinity\b", "null", text)

    # 5) Try strict parse first
    try:
        result = json.loads(text)
        return _unwrap_result(result)
    except json.JSONDecodeError:
        pass

    # 6) Try lenient parse (allows control chars in strings)
    try:
        result = json.loads(text, strict=False)
        return _unwrap_result(result)
    except json.JSONDecodeError:
        pass

    # 7) Fix trailing commas: ,} → } and ,] → ]
    fixed = re.sub(r",\s*([}\]])", r"\1", text)
    if fixed != text:
        try:
            result = json.loads(fixed, strict=False)
            return _unwrap_result(result)
        except json.JSONDecodeError:
            pass

    # 8) raw_decode — extract first valid JSON object (handles extra data at end)
    try:
        decoder = json.JSONDecoder(strict=False)
        result, _ = decoder.raw_decode(text.strip())
        return _unwrap_result(result)
    except json.JSONDecodeError:
        pass

    # 9) Truncated JSON — try closing open braces/brackets
    result = _try_close_truncated(text)
    if result is not None:
        return _unwrap_result(result)

    return None


def _unwrap_result(result) -> dict | None:
    """Unwrap common LLM response wrappers."""
    # [{...}] → {...}
    if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict):
        return result[0]
    if isinstance(result, dict):
        return result
    return None


def _try_close_truncated(text: str) -> dict | None:
    """Attempt to recover truncated JSON by closing open braces/brackets.

    This handles cases where max_output_tokens is hit mid-response.
    """
    # Count open/close braces and brackets
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")

    if open_braces <= 0 and open_brackets <= 0:
        return None  # Not a truncation issue

    # Remove trailing comma if present
    text = text.rstrip()
    if text.endswith(","):
        text = text[:-1]

    # Close open structures
    text += "]" * open_brackets + "}" * open_braces

    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        return None
