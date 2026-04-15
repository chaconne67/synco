#!/usr/bin/env python3
"""Run a Gemini CLI review and return structured output.

Usage:
    # Prompt from file
    python3 run_gemini_review.py --repo-dir /path/to/repo --prompt-file prompt.md

    # Prompt from stdin
    cat prompt.md | python3 run_gemini_review.py --repo-dir /path/to/repo

Exit codes:
    0  Success — review text written to stdout
    1  Gemini returned empty/broken output or parse failed
    2  gemini binary not found

Stdout: review content only
Stderr: progress, token counts, errors

Gemini stream-json format (verified 2026-04-12):
  {"type":"init", "session_id":"...", "model":"..."}
  {"type":"message", "role":"user", "content":"..."}
  {"type":"message", "role":"assistant", "content":"chunk", "delta":true}
  {"type":"result", "status":"success", "stats":{...}}
"""

import argparse
import json
import shutil
import subprocess
import sys


def parse_args():
    p = argparse.ArgumentParser(
        description="Run gemini CLI review with structured output parsing"
    )
    p.add_argument(
        "--repo-dir", required=True, help="Repository root (gemini runs in this dir)"
    )
    p.add_argument("--prompt-file", help="Path to prompt file (reads stdin if omitted)")
    return p.parse_args()


def read_prompt(prompt_file):
    if prompt_file:
        with open(prompt_file) as f:
            return f.read()
    else:
        if sys.stdin.isatty():
            print(
                "ERROR: No prompt provided. Pipe via stdin or use --prompt-file.",
                file=sys.stderr,
            )
            sys.exit(1)
        return sys.stdin.read()


def run_gemini(prompt, repo_dir):
    if not shutil.which("gemini"):
        print("ERROR: gemini binary not found.", file=sys.stderr)
        sys.exit(2)

    # Pass prompt via stdin to avoid ARG_MAX limits on large prompts.
    # -p "" activates headless mode; stdin content is the actual prompt.
    cmd = [
        "gemini",
        "-p",
        prompt,
        "--approval-mode",
        "plan",  # read-only — no edits
        "-o",
        "stream-json",
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=repo_dir,
    )
    return proc


def parse_stream_json(proc):
    """Parse gemini stream-json output.

    Gemini emits:
      {"type":"message", "role":"assistant", "content":"chunk", "delta":true}
    for streaming content, and:
      {"type":"result", "status":"success", "stats":{...}}
    at the end.
    """
    chunks = []
    saw_result = False
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
                print("ERROR: Too many parse errors, aborting", file=sys.stderr)
                proc.kill()
                return "", False
            continue

        event_type = obj.get("type", "")

        if event_type == "message" and obj.get("role") == "assistant":
            content = obj.get("content", "")
            if content:
                chunks.append(content)

        elif event_type == "result":
            saw_result = True
            stats = obj.get("stats", {})
            total = stats.get("total_tokens", 0)
            input_t = stats.get("input_tokens", 0)
            output_t = stats.get("output_tokens", 0)
            duration = stats.get("duration_ms", 0)
            if total:
                print(
                    f"[tokens] input={input_t} output={output_t} total={total} duration={duration}ms",
                    file=sys.stderr,
                    flush=True,
                )

    proc.wait()
    return "".join(chunks), saw_result


def main():
    args = parse_args()
    prompt = read_prompt(args.prompt_file)

    if not prompt.strip():
        print("ERROR: Empty prompt", file=sys.stderr)
        sys.exit(1)

    proc = run_gemini(prompt, args.repo_dir)
    output, saw_result = parse_stream_json(proc)

    # Capture stderr
    gemini_stderr = proc.stderr.read()
    if gemini_stderr.strip():
        print(f"[gemini stderr] {gemini_stderr.strip()}", file=sys.stderr)

    if proc.returncode != 0:
        print(f"ERROR: gemini exited with code {proc.returncode}", file=sys.stderr)
        sys.exit(1)

    if not saw_result:
        print(
            "ERROR: No result event received — gemini may have crashed", file=sys.stderr
        )
        sys.exit(1)

    if not output.strip():
        print(
            "ERROR: No content received — gemini returned empty review", file=sys.stderr
        )
        sys.exit(1)

    print(output)


if __name__ == "__main__":
    main()
