"""Multi-provider LLM client.

Supports: claude_cli (subprocess), kimi (Moonshot API), minimax (OpenRouter),
openrouter (any model). All OpenAI-compatible providers use the openai SDK.

Default: claude_cli. Switch via LLM_PROVIDER env var.
Fallback chain for future testing: kimi > minimax.
"""

import json
import logging
import subprocess

from django.conf import settings

logger = logging.getLogger(__name__)

_openai_client = None


def _get_provider() -> str:
    return getattr(settings, "LLM_PROVIDER", "claude_cli")


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        provider = _get_provider()
        config = settings.LLM_PROVIDERS.get(provider, {})
        _openai_client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=config.get("base_url"),
        )
    return _openai_client


def _extract_json(text: str) -> dict | list:
    """Extract JSON from raw LLM response, handling ```json blocks."""
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def call_llm(
    prompt: str, system: str = "", timeout: int = 30, max_tokens: int = 500
) -> str:
    """Call LLM and return raw text response."""
    provider = _get_provider()

    if provider == "claude_cli":
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        result = subprocess.run(
            ["claude", "--print", "--model", "sonnet", "--max-turns", "1"],
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI error: {result.stderr}")
        return result.stdout.strip()

    # OpenAI-compatible providers (kimi, minimax, openrouter)
    client = _get_openai_client()
    config = settings.LLM_PROVIDERS.get(provider, {})
    model = settings.LLM_MODEL or config.get("model", "")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def call_llm_json(
    prompt: str, system: str = "", timeout: int = 30, max_tokens: int = 500
) -> dict | list:
    """Call LLM and parse response as JSON."""
    text = call_llm(prompt, system=system, timeout=timeout, max_tokens=max_tokens)
    return _extract_json(text)
