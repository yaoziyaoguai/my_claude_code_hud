# Claude HUD v2 — Optimization Design Spec

**Date**: 2026-03-25
**Status**: Draft
**Supersedes**: 2026-03-24-claude-hud-design.md (v1)

---

## Overview

This spec describes targeted improvements to Claude HUD v1 addressing three areas:
1. **Visual polish** — split event stream into Active + History panels, newest-on-top ordering
2. **Feature additions** — cost estimation, real-time pending tool elapsed time
3. **UX fixes** — pending state no longer mixed with completed history

---

## Goals

- Newest events appear at the top of the history panel (not the bottom)
- Pending tools have a dedicated Active panel showing elapsed time in real-time
- Summary panel shows estimated API cost
- Both `[...]` (pre) and `[OK]`/`[ERR]` (post) lines are preserved, but in separate panels

---

## Layout

```
┌─────────────────────────────────────────────┬──────────────┐
│ ACTIVE                                       │   SUMMARY    │
│  [...]  Read    src/foo.py          0.1s    │              │
│  [...]  Bash    npm test            1.2s    │ session: a1b2 │
├─────────────────────────────────────────────│              │
│ HISTORY                           (newest↑) │ skills:   1  │
│ 12:03 [OK]   Edit    src/index.py  312ms   │ agents:   2  │
│ 12:02 [ERR]  Bash    npm test    2,103ms   │ tools:    8  │
│       exit 1: ENOENT package.json          │ errors:   1  │
│ 12:01 [OK]   Read    src/foo.py     88ms   │              │
│ 12:01 [SKILL] brainstorming                │ in:  12,400  │
│ 12:00 [AGENT] code-reviewer                │ out:  3,200  │
└─────────────────────────────────────────────│ ~$0.042      │
                                              └──────────────┘
```

---

## Architecture

### Component Changes

`EventStreamWidget` is removed and replaced by two focused widgets:

| Widget | Type | Purpose |
|--------|------|---------|
| `ActiveWidget` | `Static` | Shows currently pending tools with live elapsed time |
| `HistoryWidget` | Custom `Widget` | Completed events, newest-on-top, scrollable |
| `SummaryWidget` | `Static` (modified) | Adds cost estimation row |

### Layout Structure

```
Horizontal
├── Vertical (3fr)
│   ├── ActiveWidget   (fixed height: 4 lines)
│   └── HistoryWidget  (flex, scrollable)
└── SummaryWidget (1fr)
```

---

## Component Specifications

### ActiveWidget

- Stores `_pending: dict[tuple[str, str], tuple[str, float]]`
  - key: `(session_id, tool_name)`
  - value: `(input_summary, pre_ts)`
- Renders one line per pending tool: `[...]  ToolName  summary  Xs`
- Registers a 1-second timer via `set_interval(1.0, self.refresh)` to update elapsed time
- On `add_pending(event: ToolEvent)`: inserts into `_pending`
- On `remove_pending(event: ToolEvent)`: removes from `_pending`, triggers refresh
- On `reset()`: clears `_pending`
- Fixed height: `4` lines (enough for typical parallel tool calls; overflow clips)

### HistoryWidget

- Stores `_lines: deque[str]` with `maxlen=500`
- New events: `_lines.appendleft(formatted_line)` → newest at index 0
- `render()` returns `Text` built by joining `_lines` with newlines
- Handles all completed event types: `ToolEvent(phase=post)`, `AgentEvent`, `SkillEvent`, `StopEvent`
- On `reset(session_id)`: clears deque, prepends `[dim]--- new session: {session_id} ---[/dim]`
- Scrollable via Textual's built-in scroll

### SummaryWidget (modifications)

- New fields: `_cost: float`
- `update_event` accumulates tokens as before, also updates `_cost`
- `render()` adds cost row: `~${self._cost:.3f}` (shown as `~$0.000` when no tokens yet)

---

## Data Flow

### Event Routing in `app.py`

```
pre event  → active_widget.add_pending(event)
post event → active_widget.remove_pending(event)
             history_widget.add_event(event)
             summary_widget.update_event(event)

skill/agent/stop → history_widget.add_event(event)
                   summary_widget.update_event(event)
```

### Session Switch (`_switch_session`)

```
active_widget.reset()
history_widget.reset(session_id)
summary_widget.reset(session_id)
```

---

## Cost Calculation

Prices stored in `hud/cost.py` (easy to update per model):

```python
PRICE_PER_M_IN  = 3.0   # $/M input tokens  (claude-3-5-sonnet)
PRICE_PER_M_OUT = 15.0  # $/M output tokens

def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * PRICE_PER_M_IN
          + output_tokens / 1_000_000 * PRICE_PER_M_OUT)
```

Displayed with `~` prefix to indicate estimation. Resets to `~$0.000` on new session.

---

## File Changes

### New Files
- `hud/cost.py` — price constants + `estimate_cost()` function
- `hud/widgets/active.py` — `ActiveWidget`
- `hud/widgets/history.py` — `HistoryWidget`
- `tests/test_active_widget.py`
- `tests/test_history_widget.py`
- `tests/test_cost.py`

### Modified Files
- `hud/app.py` — new layout, updated event routing
- `hud/widgets/summary.py` — add cost row
- `tests/test_app.py` — update for new layout

### Deleted Files
- `hud/widgets/event_stream.py` — replaced by active.py + history.py

### Unchanged Files
- `hook.py`, `parser.py`, `models.py`, `watcher.py`, `install.py`

---

## Out of Scope (v2)

- Clickable event detail expansion
- Multi-session tab switching
- Windows support
- Historical session replay
