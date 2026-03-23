# Claude HUD — Design Spec

**Date**: 2026-03-24
**Status**: Draft

---

## Overview

Claude HUD is a real-time monitoring sidebar for Claude Code. It runs as an independent terminal window alongside a normal `claude` session, displaying live events driven by Claude Code's hooks system.

---

## Goals

- Show real-time tool calls, agent hierarchy, skill activations, and token usage as Claude works
- Zero friction: user runs `claude` as normal; hooks push events automatically
- No modification to Claude Code itself; installs via `~/.claude/settings.json`

---

## Architecture

```
User Terminal 1              User Terminal 2
─────────────────            ───────────────────────
$ claude-hud watch           $ claude
   │                              │
   │  Textual TUI                 │  Claude Code
   │  asyncio file watcher        │  (normal interactive use)
   │  watches /tmp/claude-hud/    │
   │                              │
   └──────────────────────────────┘
         File-based event log
    /tmp/claude-hud/{session_id}.jsonl

                    Claude Code Hooks
                    (settings.json)
                         │
                    hook.py (~30 lines)
                    reads stdin JSON
                    appends to event log file
```

### Design Decision: File Log vs Unix Socket

The initial design proposed a Unix socket. After review, **file-based event logging** is preferred:

- `hook.py` appends events to `/tmp/claude-hud/{session_id}.jsonl`
- `claude-hud watch` uses `asyncio` file watching (`watchfiles` library) to tail new events
- Events are durable — HUD can be started after Claude and still see history
- No socket server required; `hook.py` cannot crash the HUD
- Hook.py is simpler and easier to test

The tradeoff is slightly higher latency (~50ms polling interval vs. socket push), which is acceptable for a monitoring tool.

### Data Flow

1. Claude Code fires `PreToolUse` / `PostToolUse` / `Stop` hooks
2. `hook.py` reads the event JSON from stdin, reads `session_id` from `CLAUDE_SESSION_ID` env var, adds `ts` (Unix timestamp) and `hook_type` (from CLI arg), appends to `/tmp/claude-hud/{session_id}.jsonl`
3. `hud/watcher.py` (`watchfiles` async watcher) detects new lines and parses them
4. Parsed events are posted to the Textual app via `app.post_message()`
5. Textual widgets update reactively

---

## Hook Payload Reference

Claude Code delivers the following JSON on hook stdin. `session_id` is **not** in the JSON — it is available only via the `CLAUDE_SESSION_ID` environment variable. Hook type is determined by the settings.json key, not a payload field.

**PreToolUse:**
```json
{
  "tool_name": "Read",
  "tool_input": { "file_path": "src/index.ts" }
}
```

**PostToolUse:**
```json
{
  "tool_name": "Read",
  "tool_input": { "file_path": "src/index.ts" },
  "tool_output": { "output": "..." },
  "usage": { "input_tokens": 1200, "output_tokens": 340 }
}
```

Note: `tool_output` (not `tool_response`). Token usage may appear as `usage` or `token_usage` with `input_tokens`/`output_tokens` or `prompt_tokens`/`completion_tokens`.

**Stop:**
```json
{
  "transcript_path": "/path/to/session/transcript.jsonl"
}
```

`hook.py` adds these fields before writing to JSONL:
- `ts`: `time.time()` (Unix float timestamp)
- `session_id`: read from `os.environ["CLAUDE_SESSION_ID"]`
- `hook_type`: `"pre"` / `"post"` / `"stop"` (passed as CLI argument, since payload has no type indicator)

---

## Duration Correlation

Pre 和 Post 是两次独立的脚本调用，无法共享 `call_id`。Duration 在 `parser.py` 中用近似匹配计算：

- `parser.py` maintains an in-memory `dict[(session_id, tool_name) → pre_ts]`
- On a `post` event, it looks up the most recent `pre` event with matching `(session_id, tool_name)`, computes `duration_ms = (post_ts - pre_ts) * 1000`, and removes the entry
- If no matching `pre` event exists, `duration_ms` is `null`
- For parallel tool calls of the same type, duration may be approximate (acceptable for monitoring)

---

## `hook.py` Exit Code Contract

`hook.py` **must always exit with code 0**. A non-zero exit code can block or abort Claude Code operations depending on hook type.

Rules:
- All exceptions are caught at the top level with a bare `except Exception`
- On any error, the script logs a single line to `/tmp/claude-hud/hook-errors.log` and exits 0
- File writes use a short timeout (open with `O_NONBLOCK` not applicable for files; use try/except on write)
- The script never blocks longer than 200ms total

---

## Display

**Layout: Event Stream + Right Summary**

```
┌──────────────────────────────┬────────────┐
│ EVENT STREAM                 │  SUMMARY   │
│                              │            │
│ 12:01 [SKILL] brainstorming  │ skills:  1 │
│ 12:01 [OK]   Read  src/...   │ agents:  2 │
│ 12:02 [AGENT] reviewer       │ tools:   8 │
│ 12:02 [ERR]  Bash  npm test  │ errors:  1 │
│        exit 1: ...           │            │
│ 12:03 [...]  Edit  src/...   │  $0.042    │
│ 12:03 [STOP] session ended   │            │
└──────────────────────────────┴────────────┘
```

**Event type prefixes** (ASCII-safe, terminal-compatible):
- `[OK]` green — tool succeeded
- `[ERR]` red — tool failed; next line shows truncated error excerpt (first 80 chars)
- `[...]` yellow — tool in progress (replaced by `[OK]` or `[ERR]` on completion)
- `[SKILL]` purple — skill activated
- `[AGENT]` blue — subagent spawned
- `[STOP]` dim — session ended

**Summary panel reset**: Counters reset when a new `session_id` is first seen, replacing the previous session's data. The current `session_id` is shown in the summary panel header.

**Multi-session**: The HUD displays one session at a time — the most recently active (last event received). When a new `session_id` appears, the event stream clears with a separator line (`--- new session: abc123 ---`) and counters reset.

---

## Data Sources

| Module | Source | Notes |
|--------|--------|-------|
| Tool calls | `PostToolUse` hook | Name, input summary, duration via `(session_id, tool_name)` correlation |
| Skill activations | `PostToolUse` where `tool_name == "Skill"` | `tool_input["skill"]` field |
| Agent tree | `PostToolUse` where `tool_name == "Agent"` | `tool_input["description"]` (truncated to 60 chars) |
| Token stats | `PostToolUse` hook `usage` field | `input_tokens` / `output_tokens`, cumulative in HUD |

**Token stats**: PostToolUse hooks include `usage` (or `token_usage`) with `input_tokens`/`output_tokens`. HUD accumulates these per session. Note: not every PostToolUse event may contain usage — HUD should handle missing fields gracefully.

---

## Data Model

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class ToolEvent:
    session_id: str
    tool_name: str
    input_summary: str     # first 60 chars of key fields from tool_input
    ts: float
    phase: Literal["pre", "post"]
    success: bool | None   # None during pre phase
    duration_ms: int | None  # populated on post; None if pre not seen
    error_excerpt: str | None  # first 80 chars of error if failed
    input_tokens: int | None   # from usage field, may be None
    output_tokens: int | None

@dataclass
class AgentEvent:
    session_id: str        # parent session
    child_description: str # tool_input["description"], truncated to 60 chars
    ts: float

@dataclass
class SkillEvent:
    session_id: str
    skill_name: str        # tool_input["skill"]
    ts: float

@dataclass
class StopEvent:
    session_id: str
    transcript_path: str | None  # path to session transcript JSONL
    ts: float
```

**`input_summary` strategy**: For each tool, a fixed set of key fields is extracted:
- `Read` → `file_path`
- `Bash` → first 60 chars of `command`
- `Edit` → `file_path`
- `Grep` → `pattern` + `path`
- `Agent` → first 60 chars of `description`
- Others → `str(tool_input)[:60]`

---

## Components

```
claude-hud/
├── hud/
│   ├── __main__.py        # Entry: python -m hud watch / python -m hud install
│   ├── app.py             # Textual App — layout, message routing
│   ├── watcher.py         # watchfiles async tail of session JSONL
│   ├── models.py          # Event dataclasses
│   ├── parser.py          # Raw JSON line → typed event
│   └── widgets/
│       ├── event_stream.py   # Scrollable event log (left panel)
│       ├── summary.py        # Counters + token stats (right panel)
│       └── tokens.py         # Token accumulator widget
├── hook.py                # Hook script (~30 lines + error handling)
└── install.py             # Writes hook config to ~/.claude/settings.json
```

### `install.py` — settings.json structure

`install.py` merges the following into `~/.claude/settings.json`. It is idempotent: if the command is already present, it is not duplicated.

**Before:**
```json
{
  "hooks": {}
}
```

**After:**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [{ "type": "command", "command": "python /path/to/hook.py pre" }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [{ "type": "command", "command": "python /path/to/hook.py post", "async": true }]
      }
    ],
    "Stop": [
      {
        "hooks": [{ "type": "command", "command": "python /path/to/hook.py stop", "async": true }]
      }
    ]
  }
}
```

Note: `matcher: "*"` matches all tools. PostToolUse and Stop use `"async": true` so they don't block Claude. The CLI arg (`pre`/`post`/`stop`) tells `hook.py` which hook type fired.

---

## Installation & Usage

**Requirements**: Python 3.10+, `textual`, `watchfiles`

```bash
# Install
pip install -e .
python -m hud install   # writes hooks to ~/.claude/settings.json

# Usage
# Terminal 1 — start HUD (can be started before or after claude)
python -m hud watch

# Terminal 2 — normal Claude usage, unchanged
claude
```

---

## Constraints & Known Limitations

1. **Token stats**: Available via PostToolUse `usage` field. Not every event includes usage — HUD accumulates what it receives and shows `--` when no data yet.
2. **Agent internals**: Hooks are globally registered via `~/.claude/settings.json`, so subagent tool calls are captured automatically.
3. **HUD start order**: HUD can be started before or after `claude`. Events are durable (written to file); the HUD replays from the start of the current session's log on connect.
4. **Multi-session**: Multiple simultaneous Claude sessions each write to their own JSONL file. The HUD shows the session with the most recent event.
5. **macOS / Linux only**: Uses file-based IPC in `/tmp/`. No Windows support in v1.
6. **Non-ASCII icons**: The display uses ASCII prefixes (`[OK]`, `[ERR]`, etc.) for terminal compatibility. Unicode icons are optional and gated on terminal capability detection.

---

## Out of Scope (v1)

- Historical session replay beyond current session
- Web UI or IDE extension
- Windows support
- Automatic terminal splitting
- Expandable event detail view
