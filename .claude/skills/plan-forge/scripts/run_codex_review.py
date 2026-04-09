#!/usr/bin/env python3
"""Run a Codex review and return structured output.

Usage:
    # Prompt from stdin
    cat prompt.md | python3 run_codex_review.py --repo-dir /path/to/repo

    # Prompt from file
    python3 run_codex_review.py --repo-dir /path/to/repo --prompt-file prompt.md

Exit codes:
    0  Success — agent_message text written to stdout
    1  Codex returned empty/broken output or JSONL parse failed
    2  codex binary not found

Stdout: agent_message text only (the review content)
Stderr: [codex thinking], [codex ran], token counts, errors
"""

import argparse
import json
import shutil
import subprocess
import sys


def parse_args():
    p = argparse.ArgumentParser(description="Run codex exec with structured JSONL parsing")
    p.add_argument("--repo-dir", required=True, help="Repository root for codex -C flag")
    p.add_argument("--prompt-file", help="Path to prompt file (reads stdin if omitted)")
    p.add_argument(
        "--reasoning-effort",
        default="high",
        choices=["low", "medium", "high"],
        help="Model reasoning effort (default: high)",
    )
    p.add_argument(
        "--web-search",
        action="store_true",
        default=True,
        help="Enable web_search_cached (default: true)",
    )
    return p.parse_args()


def read_prompt(prompt_file):
    if prompt_file:
        with open(prompt_file) as f:
            return f.read()
    else:
        if sys.stdin.isatty():
            print("ERROR: No prompt provided. Pipe via stdin or use --prompt-file.", file=sys.stderr)
            sys.exit(1)
        return sys.stdin.read()


def run_codex(prompt, repo_dir, reasoning_effort, web_search):
    if not shutil.which("codex"):
        print("ERROR: codex binary not found. Install: npm install -g @openai/codex", file=sys.stderr)
        sys.exit(2)

    # Prompt is passed as a direct argv element via subprocess (no shell=True),
    # so quotes, $, backticks, etc. are safe. However, extremely large prompts
    # may hit OS ARG_MAX (~2MB on Linux). Design specs rarely exceed this.
    prompt_bytes = len(prompt.encode("utf-8"))
    if prompt_bytes > 1_500_000:
        print(
            f"WARNING: Prompt is {prompt_bytes:,} bytes, approaching ARG_MAX limit",
            file=sys.stderr,
        )

    cmd = [
        "codex",
        "exec",
        prompt,
        "-C",
        repo_dir,
        "-s",
        "read-only",
        "-c",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--json",
    ]
    if web_search:
        cmd.extend(["--enable", "web_search_cached"])

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc


def parse_jsonl(proc):
    """Parse codex JSONL output. Returns (agent_messages, saw_turn_completed)."""
    agent_messages = []
    saw_turn_completed = False
    parse_errors = 0

    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            parse_errors += 1
            print(f"[parse error] {e}: {line[:200]}", file=sys.stderr)
            if parse_errors > 10:
                print("ERROR: Too many JSONL parse errors, aborting", file=sys.stderr)
                proc.kill()
                return agent_messages, False
            continue

        event_type = obj.get("type", "")

        if event_type == "item.completed" and "item" in obj:
            item = obj["item"]
            item_type = item.get("type", "")
            text = item.get("text", "")

            if item_type == "reasoning" and text:
                print(f"[codex thinking] {text}", file=sys.stderr, flush=True)
            elif item_type == "agent_message" and text:
                agent_messages.append(text)
            elif item_type == "command_execution":
                cmd = item.get("command", "")
                if cmd:
                    print(f"[codex ran] {cmd}", file=sys.stderr, flush=True)

        elif event_type == "turn.completed":
            saw_turn_completed = True
            usage = obj.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            total = input_tokens + output_tokens
            if total:
                print(
                    f"[tokens] input={input_tokens} output={output_tokens} total={total}",
                    file=sys.stderr,
                    flush=True,
                )

    proc.wait()
    return agent_messages, saw_turn_completed


def main():
    args = parse_args()
    prompt = read_prompt(args.prompt_file)

    if not prompt.strip():
        print("ERROR: Empty prompt", file=sys.stderr)
        sys.exit(1)

    proc = run_codex(prompt, args.repo_dir, args.reasoning_effort, args.web_search)
    agent_messages, saw_turn_completed = parse_jsonl(proc)

    # Capture any stderr from codex itself
    codex_stderr = proc.stderr.read()
    if codex_stderr.strip():
        print(f"[codex stderr] {codex_stderr.strip()}", file=sys.stderr)

    # Validate output
    if proc.returncode != 0:
        print(f"ERROR: codex exited with code {proc.returncode}", file=sys.stderr)
        sys.exit(1)

    if not saw_turn_completed:
        print("ERROR: No turn.completed event received — codex may have crashed", file=sys.stderr)
        sys.exit(1)

    if not agent_messages:
        print("ERROR: No agent_message received — codex returned empty review", file=sys.stderr)
        sys.exit(1)

    # Output: join all agent messages
    output = "\n\n".join(agent_messages)
    print(output)


if __name__ == "__main__":
    main()