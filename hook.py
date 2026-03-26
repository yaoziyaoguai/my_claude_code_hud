#!/usr/bin/env python3
"""Claude Code hook script — appends events to JSONL log.

Usage: python hook.py <pre|post|stop>

Reads JSON from stdin, enriches with session_id/ts/hook_type,
writes one line to /tmp/claude-hud/{session_id}.jsonl.

EXIT CODE IS ALWAYS 0. Never block Claude Code.
"""
import json
import os
import sys
import time
import uuid


def main() -> None:
    hook_type = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    session_id = os.environ.get("CLAUDE_SESSION_ID")
    base_dir = os.environ.get("CLAUDE_HUD_DIR", "/tmp/claude-hud")

    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    if not session_id:
        transcript_path = data.get("transcript_path")
        if transcript_path:
            session_id = os.path.splitext(os.path.basename(transcript_path))[0]
        else:
            session_id = f"session-{uuid.uuid4().hex[:8]}"
        os.environ["CLAUDE_SESSION_ID"] = session_id

    data["session_id"] = session_id
    data["hook_type"] = hook_type
    data["ts"] = time.time()
    data["cwd"] = os.getcwd()

    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, f"{session_id}.jsonl")

    with open(path, "a") as f:
        f.write(json.dumps(data, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            base_dir = os.environ.get("CLAUDE_HUD_DIR", "/tmp/claude-hud")
            os.makedirs(base_dir, exist_ok=True)
            with open(os.path.join(base_dir, "hook-errors.log"), "a") as f:
                f.write(f"{time.time()} {exc}\n")
        except Exception:
            pass
    sys.exit(0)
