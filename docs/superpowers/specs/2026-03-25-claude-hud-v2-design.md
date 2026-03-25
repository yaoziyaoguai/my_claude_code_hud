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
│  +3 more...                                 │              │
├─────────────────────────────────────────────│ skills:   1  │
│ HISTORY                           (newest↑) │ agents:   2  │
│ 12:03 [OK]   Edit    src/index.py  312ms   │ tools:    8  │
│ 12:02 [ERR]  Bash    npm test    2,103ms   │ errors:   1  │
│       exit 1: ENOENT package.json          │              │
│ 12:01 [OK]   Read    src/foo.py     88ms   │ in:  12,400  │
│ 12:01 [SKILL] brainstorming                │ out:  3,200  │
│ 12:00 [AGENT] code-reviewer                │ ~$0.042      │
└─────────────────────────────────────────────└──────────────┘
```

Error excerpt indentation: 7 spaces (matching v1 behavior).

---

## Architecture

### Component Changes

`EventStreamWidget` is removed and replaced by two focused widgets:

| Widget | Base Class | Purpose |
|--------|-----------|---------|
| `ActiveWidget` | Custom `Widget` | Shows currently pending tools with live elapsed time |
| `HistoryWidget` | `VerticalScroll` (`textual.containers`) | Completed events, newest-on-top, scrollable |
| `SummaryWidget` | `Static` (modified) | Adds cost estimation row |

### Layout Structure

```
Horizontal
├── Vertical (3fr)
│   ├── ActiveWidget   (CSS: height: 7;  — 1 border top + 5 content + 1 border bottom)
│   └── HistoryWidget  (flex, scrollable)
└── SummaryWidget (1fr)
```

### CSS

Replace the existing `CSS` block in `app.py`:

```css
Horizontal {
    height: 100%;
}
Vertical {
    width: 3fr;
}
ActiveWidget {
    height: 7;
    border: solid $accent;
}
HistoryWidget {
    border: solid $primary;
}
SummaryWidget {
    width: 1fr;
    border: solid $secondary;
    padding: 1;
}
```

---

## Component Specifications

### ActiveWidget

Extends `Widget`. Overrides `render()` to return a `Text` object.

**State:**
```python
# key: (session_id, tool_name, pre_ts)  — pre_ts disambiguates parallel same-tool calls
# value: input_summary (str)
_pending: dict[tuple[str, str, float], str]
```

**Methods:**

- `add_pending(event: ToolEvent)` — `phase == "pre"`:
  ```python
  self._pending[(event.session_id, event.tool_name, event.ts)] = event.input_summary
  self.refresh()
  ```

- `remove_pending(event: ToolEvent)` — `phase == "post"`: FIFO removal — pops the entry with the **smallest `pre_ts`** among all entries matching `(session_id, tool_name)`. This is the primary and only removal strategy (no `pre_ts` lookup from the post event, since `ToolEvent` carries no `pre_ts` field):
  ```python
  matches = [(k, v) for k, v in self._pending.items()
             if k[0] == event.session_id and k[1] == event.tool_name]
  if matches:
      oldest_key = min(matches, key=lambda x: x[0][2])[0]
      del self._pending[oldest_key]
  self.refresh()
  ```

- `reset()`: `self._pending.clear(); self.refresh()`

**Rendering:**
- `render()` iterates `_pending.items()` (not `.values()`) to access both `pre_ts` (from key) and `input_summary` (value):
  ```python
  def render(self) -> Text:
      now = time.time()
      lines = []
      items = list(self._pending.items())  # insertion order
      for i, ((sid, tool_name, pre_ts), input_summary) in enumerate(items):
          if i >= 4:
              lines.append(f"[dim]+{len(items) - 4} more...[/dim]")
              break
          elapsed = now - pre_ts
          lines.append(f"[yellow][...][/yellow]  {tool_name}  {input_summary}  {elapsed:.1f}s")
      return Text.from_markup("\n".join(lines))
  ```
- Max 4 tool lines + optional `+N more...` line = max 5 content rows → CSS `height: 7` (1 top border + 5 content + 1 bottom border)
- 1-second refresh timer registered in `on_mount`: `self.set_interval(1.0, self.refresh)`

**Note on parallel same-tool calls:** Using `pre_ts` in the key prevents a second concurrent `Read` from overwriting the first. FIFO removal means the oldest pending entry of that tool name is resolved first — which is the correct assumption in nearly all cases (tools complete roughly in the order they start).

### HistoryWidget

Extends `VerticalScroll` from `textual.containers`. Contains a single inner `Static` child.

**State:**
```python
_lines: deque[str]  # maxlen=500; index 0 = newest
```

**Compose:**
```python
def compose(self):
    yield Static("", id="history-content", markup=True)
```

**Methods:**

- `add_event(event)`: only accepts completed events. Guard clause:
  ```python
  if isinstance(event, ToolEvent) and event.phase == "pre":
      return  # pre-phase events must never reach HistoryWidget
  ```
  Formats event to Rich markup string, `_lines.appendleft(formatted)`, updates inner `Static`.

- `reset(session_id)`: clears `_lines`, appends separator `[dim]--- new session: {session_id} ---[/dim]`, updates inner `Static`

**Scroll behavior:** `Static.update()` replaces content in place. This resets the scroll position to the top on every new event — this is **intentional and acceptable in v2** since history is newest-on-top and the top is always the most relevant view. Known limitation: a user scrolled down to read old entries will be bumped back up on each new event.

**Performance:** Full `"\n".join(_lines)` on each event is acceptable for v2 (max ~500 lines). Optimize if lag is observed.

**Border title:** Set in `on_mount`: `self.border_title = "HISTORY"`

### SummaryWidget (modifications)

- New field: `_cost: float = 0.0`
- `update_event`: after accumulating tokens, adds to cost:
  ```python
  if event.input_tokens or event.output_tokens:
      self._cost += estimate_cost(event.input_tokens or 0, event.output_tokens or 0)
  ```
- `render()` adds cost row: `f"~${self._cost:.3f}"`  (displays `~$0.000` when no tokens yet)
- `reset()`: also sets `self._cost = 0.0`

---

## Data Flow

### `_handle_raw` in `app.py`

```python
def _handle_raw(self, raw: dict) -> None:
    event = self._parser.parse(raw)
    try:
        active = self.query_one(ActiveWidget)
        history = self.query_one(HistoryWidget)
        summary = self.query_one(SummaryWidget)
    except NoMatches:
        return

    if isinstance(event, ToolEvent) and event.phase == "pre":
        active.add_pending(event)
    elif isinstance(event, ToolEvent) and event.phase == "post":
        active.remove_pending(event)
        history.add_event(event)
        summary.update_event(event)
    else:  # AgentEvent, SkillEvent, StopEvent
        history.add_event(event)
        summary.update_event(event)
```

### Session Switch (`_switch_session`)

Replaces old `clear_with_separator` call:

```python
def _switch_session(self, session_id: str) -> None:
    self._current_session = session_id
    self._parser = EventParser()
    try:
        self.query_one(ActiveWidget).reset()
        self.query_one(HistoryWidget).reset(session_id)   # writes separator line
        self.query_one(SummaryWidget).reset(session_id)
    except NoMatches:
        pass
```

Migration note: `EventStreamWidget.clear_with_separator(session_id)` is removed. Its separator behavior moves into `HistoryWidget.reset(session_id)`.

---

## Cost Calculation

`hud/cost.py`:

```python
# Pricing for claude-sonnet-4-6 (model in use as of 2026-03-25).
# All tokens are priced at this rate regardless of actual model used.
# The `~` prefix in the display communicates this is an estimate.
# Update these constants when switching models or when pricing changes.
PRICE_PER_M_IN  = 3.0   # $/M input tokens
PRICE_PER_M_OUT = 15.0  # $/M output tokens

def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * PRICE_PER_M_IN
          + output_tokens / 1_000_000 * PRICE_PER_M_OUT)
```

---

## File Changes

### New Files
- `hud/cost.py` — price constants + `estimate_cost()` function
- `hud/widgets/active.py` — `ActiveWidget`
- `hud/widgets/history.py` — `HistoryWidget`
- `tests/test_active_widget.py` — covers: `add_pending`, `remove_pending` (FIFO), parallel same-tool disambiguation, `reset`, overflow indicator (`+N more`)
- `tests/test_history_widget.py` — covers: `add_event` newest-on-top ordering, `reset` with separator, `maxlen=500` truncation
- `tests/test_cost.py` — covers: `estimate_cost` arithmetic, zero-token case

### Modified Files
- `hud/app.py` — new CSS, new layout (`Vertical` + `ActiveWidget` + `HistoryWidget`), updated `_handle_raw` routing, updated `_switch_session`
- `hud/widgets/summary.py` — add `_cost` field, import `estimate_cost`, cost row in `render()`, reset `_cost` in `reset()`
- `tests/test_app.py` — **full rewrite** to match new widget hierarchy; must cover: pre events route to `ActiveWidget` only; post events route to `ActiveWidget` + `HistoryWidget` + `SummaryWidget`; skill/agent/stop route to `HistoryWidget` + `SummaryWidget`; session switch resets all three widgets; **session switch resets cost to zero** (verify `SummaryWidget._cost == 0.0` after `_switch_session`)

### Deleted Files
- `hud/widgets/event_stream.py` — replaced by `active.py` + `history.py`

### Unchanged Files
- `hook.py`, `parser.py`, `models.py`, `watcher.py`, `install.py`

---

## Out of Scope (v2)

- Clickable event detail expansion
- Multi-session tab switching
- Windows support
- Historical session replay
- Per-model cost tracking (single model price used for all)
- Sub-second elapsed time resolution in `ActiveWidget` (1-second timer; `0.0s` shown until first tick)
- Accurate `duration_ms` for parallel same-tool calls: `parser.py` uses `(session_id, tool_name)` as its internal key and will overwrite `pre_ts` when two concurrent `Read` calls arrive before either resolves. The second call's `duration_ms` will be approximate. This is a known v1 limitation carried forward unchanged (`parser.py` is not modified in v2).
