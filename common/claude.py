import json
import subprocess


def call_claude(prompt: str, timeout: int = 60) -> str:
    """Call Claude via claude CLI (uses Claude Code subscription auth).

    Args:
        prompt: Text prompt to send.
        timeout: Max seconds to wait (default 60).

    Returns:
        Raw text response from Claude.
    """
    result = subprocess.run(
        ["claude", "--print"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI error: {result.stderr}")
    return result.stdout.strip()


def call_claude_json(prompt: str, timeout: int = 60) -> dict | list:
    """Call Claude and parse response as JSON.

    Handles responses wrapped in ```json ... ``` code blocks.
    """
    response = call_claude(prompt, timeout=timeout)

    text = response
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    return json.loads(text)
