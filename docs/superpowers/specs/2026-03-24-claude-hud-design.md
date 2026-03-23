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

1. Claude Code fires `PreToolUse` / `PostToolUse` / `Stop` / `SubagentStop` hooks
2. `hook.py` reads the event JSON from stdin, adds `ts` (Unix timestamp), appends to `/tmp/claude-hud/{session_id}.jsonl`
3. `hud/watcher.py` (`watchfiles` async watcher) detects new lines and parses them
4. Parsed events are posted to the Textual app via `app.post_message()`
5. Textual widgets update reactively

---

## Hook Payload Reference

Claude Code delivers the following JSON on hook stdin. These are the exact field names.

**PreToolUse:**
```json
{
  "session_id": "abc123",
  "hook_event_name": "PreToolUse",
  "tool_name": "Read",
  "tool_input": { "file_path": "src/index.ts" }
}
```

**PostToolUse:**
```json
{
  "session_id": "abc123",
  "hook_event_name": "PostToolUse",
  "tool_name": "Read",
  "tool_input": { "file_path": "src/index.ts" },
  "tool_response": { "content": "..." }
}
```

**Stop / SubagentStop:**
```json
{
  "session_id": "abc123",
  "hook_event_name": "Stop",
  "stop_reason": "end_turn"
}
```

`hook.py` adds two fields before writing:
- `ts`: `time.time()` (Unix float timestamp)
- `call_id`: UUID4 string, generated once per `PreToolUse` and repeated in the matching `PostToolUse` (see Duration Correlation below)

---

## Duration Correlation

`hook.py` generates a `call_id` (UUID4) on `PreToolUse` and includes it in both the `pre` and `post` events written to the JSONL. Duration is computed in `parser.py` (not in `hook.py`):

- `parser.py` maintains an in-memory `dict[call_id → pre_ts]`
- On a `post` event, it looks up `pre_ts`, computes `duration_ms = (post_ts - pre_ts) * 1000`, and removes the entry
- If no `pre` event was seen (e.g., HUD started mid-session), `duration_ms` is `null`

This keeps `hook.py` simple (append-only) and moves all stateful logic into the HUD process where failures are recoverable.

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
| Tool calls | `PostToolUse` hook | Name, input summary, duration via `call_id` correlation |
| Skill activations | `PostToolUse` where `tool_name == "Skill"` | `tool_input["skill"]` field |
| Agent tree | `PostToolUse` where `tool_name == "Agent"` + `session_id` | `tool_input["description"]` (truncated to 60 chars) |
| Token stats | Interactive mode: always `--`. Headless integration deferred to v2. |

**Token limitation**: Claude Code's interactive mode does not expose token usage via hooks or any other synchronous channel accessible to a monitoring tool without wrapping the `claude` process. Token stats are explicitly out of scope for v1. The token panel will display `-- / -- / --` with a tooltip "available in headless mode (v2)".

---

## Data Model

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class ToolEvent:
    session_id: str
    call_id: str
    tool_name: str
    input_summary: str     # first 60 chars of key fields from tool_input
    ts: float
    phase: Literal["pre", "post"]
    success: bool | None   # None during pre phase
    duration_ms: int | None  # populated on post; None if pre not seen
    error_excerpt: str | None  # first 80 chars of error if failed

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
    stop_reason: str       # "end_turn", "max_turns", etc.
    is_subagent: bool
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
│       └── summary.py        # Counters + token placeholder (right panel)
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
      { "hooks": [{ "type": "command", "command": "python /path/to/hook.py" }] }
    ],
    "PostToolUse": [
      { "hooks": [{ "type": "command", "command": "python /path/to/hook.py" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "python /path/to/hook.py" }] }
    ],
    "SubagentStop": [
      { "hooks": [{ "type": "command", "command": "python /path/to/hook.py" }] }
    ]
  }
}
```

If `hooks` already has entries for these keys, the new command is appended to the existing array.

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

1. **Token stats**: Not available in interactive mode (v1 shows `--`). Headless integration deferred to v2.
2. **Agent internals**: Hooks are globally registered via `~/.claude/settings.json`, so subagent tool calls are captured automatically.
3. **HUD start order**: HUD can be started before or after `claude`. Events are durable (written to file); the HUD replays from the start of the current session's log on connect.
4. **Multi-session**: Multiple simultaneous Claude sessions each write to their own JSONL file. The HUD shows the session with the most recent event.
5. **macOS / Linux only**: Uses file-based IPC in `/tmp/`. No Windows support in v1.
6. **Non-ASCII icons**: The display uses ASCII prefixes (`[OK]`, `[ERR]`, etc.) for terminal compatibility. Unicode icons are optional and gated on terminal capability detection.

---

## Out of Scope (v1)

- Token stats in interactive mode
- Historical session replay beyond current session
- Web UI or IDE extension
- Windows support
- Automatic terminal splitting
- Expandable event detail view
