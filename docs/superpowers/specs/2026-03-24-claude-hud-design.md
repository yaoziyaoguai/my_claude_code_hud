# Claude HUD — Design Spec

**Date**: 2026-03-24
**Status**: Approved

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
   │  asyncio socket server       │  (normal interactive use)
   │                              │
   └──────────────────────────────┘
            Unix socket
     /tmp/claude-hud-{session_id}.sock

                    Claude Code Hooks
                    (settings.json)
                         │
                    hook.py (~20 lines)
                    reads stdin JSON
                    pushes to socket
```

### Data Flow

1. Claude Code fires `PreToolUse` / `PostToolUse` / `Stop` / `SubagentStop` hooks
2. `hook.py` reads the event JSON from stdin and forwards it to the Unix socket
3. `hud/server.py` (asyncio) receives the event and posts a message to the Textual app
4. Textual widgets update reactively

---

## Display

**Layout: Event Stream + Right Summary**

```
┌──────────────────────────────┬────────────┐
│ EVENT STREAM                 │  SUMMARY   │
│                              │            │
│ 12:01 ◈ brainstorming        │ skills:  1 │
│ 12:01 ✓ Read  src/index.ts   │ agents:  2 │
│ 12:02 ◎ Agent: reviewer      │ tools:   8 │
│ 12:02 ✗ Bash  npm test       │ errors:  1 │
│ 12:03 … Edit  src/app.ts     │            │
│                              │  $0.042    │
└──────────────────────────────┴────────────┘
```

**Event color coding:**
- `✓` green — tool succeeded
- `✗` red — tool failed
- `…` yellow — tool in progress
- `◈` purple — skill activated
- `◎` blue — agent spawned

---

## Data Sources

| Module | Source | Notes |
|--------|--------|-------|
| Tool calls | `PostToolUse` hook | Name, input summary, duration (Pre→Post diff), success/fail |
| Skill activations | `PostToolUse` where `tool_name == "Skill"` | `tool_input.skill` field |
| Agent tree | `tool_name == "Agent"` + `session_id` changes | Inferred hierarchy |
| Token stats | `--output-format stream-json` `result` event | Available in headless mode only; shows `--` in interactive mode |

**Token limitation**: Claude Code's interactive mode does not expose token usage via hooks. Token stats are only available when Claude is invoked with `--output-format stream-json` (headless/scripted mode). In interactive mode the token panel shows `--`.

---

## Components

```
claude-hud/
├── hud/
│   ├── __main__.py       # Entry point: python -m hud watch
│   ├── app.py            # Textual App — layout, message routing
│   ├── server.py         # asyncio Unix socket server
│   ├── models.py         # Event dataclasses (ToolEvent, AgentEvent, SkillEvent)
│   └── widgets/
│       ├── event_stream.py   # Scrollable event log (left panel)
│       └── summary.py        # Counters + token stats (right panel)
├── hook.py               # Hook script registered in settings.json
└── install.py            # Writes hook config to ~/.claude/settings.json
```

### `hook.py` (hook script)

Registered for `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStop`. Reads the event JSON from stdin, adds a `ts` (Unix timestamp) field, and forwards to the session socket. If the socket is not available (HUD not running), exits silently — Claude is never blocked.

### `hud/server.py`

An `asyncio` Unix socket server started as a Textual background worker. Listens on `/tmp/claude-hud-{session_id}.sock`. On each connection, reads a single JSON line, parses it into the appropriate event dataclass, and calls `app.post_message()`.

### `install.py`

Reads `~/.claude/settings.json`, merges hook entries for `PreToolUse`, `PostToolUse`, `Stop`, and `SubagentStop`, and writes back. Idempotent (safe to run multiple times).

---

## Event Data Model

```python
@dataclass
class ToolEvent:
    session_id: str
    tool_name: str
    input_summary: str   # truncated repr of tool_input
    ts: float
    phase: Literal["pre", "post"]
    success: bool | None  # None during pre phase
    duration_ms: int | None  # populated on post

@dataclass
class AgentEvent:
    session_id: str       # parent session
    child_description: str
    ts: float

@dataclass
class SkillEvent:
    session_id: str
    skill_name: str
    ts: float
```

---

## Installation & Usage

```bash
# Install
pip install -e .
python -m hud install   # writes hooks to ~/.claude/settings.json

# Usage
# Terminal 1
python -m hud watch

# Terminal 2 (unchanged)
claude
```

---

## Constraints & Known Limitations

1. **Token stats in interactive mode**: Not available via hooks. Shows `--` unless using headless mode with `--output-format stream-json`.
2. **Agent internals**: When Claude spawns a subagent via the `Agent` tool, that subagent's internal tool calls are only visible if hooks are globally configured (which `install.py` does via `~/.claude/settings.json`).
3. **HUD must be started first**: If `claude-hud watch` is not running when hooks fire, events are silently dropped. A future enhancement could buffer events to a file for replay on connect.
4. **Single session per socket**: Each `session_id` gets its own socket path. Running multiple Claude sessions simultaneously is supported; the HUD shows the most recently active session.

---

## Out of Scope

- Automatic terminal splitting (too fragile across terminal emulators)
- Historical session replay (v1 only shows live events)
- Web UI or IDE extension (future versions)
- Windows support (Unix socket; macOS/Linux only for v1)
