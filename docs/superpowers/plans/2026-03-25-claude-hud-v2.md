# Claude HUD v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Claude HUD with a split Active/History panel layout, newest-on-top history, hierarchical indented call tree, and cost estimation.

**Architecture:** Replace `EventStreamWidget` with two widgets (`ActiveWidget` for pending tools, `HistoryWidget` for completed events). Add `depth`/`context_label` fields to models and a context stack to `EventParser` for hierarchy inference. Add `cost.py` for token-based cost estimation.

**Tech Stack:** Python 3.10+, Textual 8.1.1, pytest, Rich (Text/markup)

**Spec:** `docs/superpowers/specs/2026-03-25-claude-hud-v2-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `hud/cost.py` | Price constants + `estimate_cost()` |
| Create | `hud/widgets/active.py` | `ActiveWidget` — pending tools with elapsed time |
| Create | `hud/widgets/history.py` | `HistoryWidget` — completed events, newest-on-top, indented |
| Modify | `hud/models.py` | Add `depth` + `context_label` to `ToolEvent`, `AgentEvent`, `SkillEvent` |
| Modify | `hud/parser.py` | Add `_context_stack`, push/pop on Agent/Skill, propagate depth |
| Modify | `hud/widgets/summary.py` | Add `_cost` field, cost row in render, reset cost |
| Modify | `hud/app.py` | New CSS, new layout, updated `_handle_raw` + `_switch_session` |
| Delete | `hud/widgets/event_stream.py` | Replaced by active.py + history.py |
| Create | `tests/test_cost.py` | Tests for `estimate_cost` |
| Create | `tests/test_active_widget.py` | Tests for `ActiveWidget` |
| Create | `tests/test_history_widget.py` | Tests for `HistoryWidget` |
| Create | `tests/test_parser_hierarchy.py` | Tests for depth/context_stack in parser |
| Rewrite | `tests/test_app.py` | Tests for new routing + session switch |

---

## Task 1: Add `depth` and `context_label` to models

**Files:**
- Modify: `hud/models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py — add to existing file
def test_tool_event_has_depth_and_context_label():
    from hud.models import ToolEvent
    ev = ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                   ts=1.0, phase="pre")
    assert ev.depth == 0
    assert ev.context_label is None

def test_agent_event_has_depth():
    from hud.models import AgentEvent
    ev = AgentEvent(session_id="s", child_description="rev", ts=1.0)
    assert ev.depth == 0

def test_skill_event_has_depth():
    from hud.models import SkillEvent
    ev = SkillEvent(session_id="s", skill_name="tdd", ts=1.0)
    assert ev.depth == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/jinkun.wang/work_space/my_claude_code_hud
pytest tests/test_models.py::test_tool_event_has_depth_and_context_label -v
```
Expected: FAIL — `ToolEvent.__init__() got unexpected keyword argument` or `has no attribute 'depth'`

- [ ] **Step 3: Add fields to models**

In `hud/models.py`, update the three dataclasses:

```python
@dataclass
class ToolEvent:
    session_id: str
    tool_name: str
    input_summary: str
    ts: float
    phase: Literal["pre", "post"]
    success: bool | None = None
    duration_ms: int | None = None
    error_excerpt: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    depth: int = 0
    context_label: str | None = None


@dataclass
class AgentEvent:
    session_id: str
    child_description: str
    ts: float
    depth: int = 0


@dataclass
class SkillEvent:
    session_id: str
    skill_name: str
    ts: float
    depth: int = 0
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_models.py -v
```
Expected: all PASS

- [ ] **Step 5: Run full suite to check no regressions**

```bash
pytest --tb=short -q
```
Expected: all existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add hud/models.py tests/test_models.py
git commit -m "feat: add depth and context_label fields to ToolEvent, AgentEvent, SkillEvent"
```

---

## Task 2: Add context stack to `EventParser`

**Files:**
- Modify: `hud/parser.py`
- Create: `tests/test_parser_hierarchy.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_parser_hierarchy.py`:

```python
from hud.parser import EventParser
from hud.models import ToolEvent, AgentEvent, SkillEvent


def _pre(tool_name, tool_input=None, session_id="s", ts=1.0):
    return {"tool_name": tool_name, "tool_input": tool_input or {},
            "session_id": session_id, "hook_type": "pre", "ts": ts}


def _post(tool_name, tool_input=None, session_id="s", ts=2.0):
    return {"tool_name": tool_name, "tool_input": tool_input or {},
            "tool_output": {}, "session_id": session_id, "hook_type": "post", "ts": ts}


def test_top_level_tool_has_depth_zero():
    p = EventParser()
    ev = p.parse(_pre("Read", {"file_path": "a.py"}))
    assert isinstance(ev, ToolEvent)
    assert ev.depth == 0
    assert ev.context_label is None


def test_tool_inside_agent_has_depth_one():
    p = EventParser()
    # Agent pre — pushes stack
    p.parse(_pre("Agent", {"description": "code-reviewer"}, ts=1.0))
    # Tool inside agent
    ev = p.parse(_pre("Read", {"file_path": "a.py"}, ts=1.1))
    assert isinstance(ev, ToolEvent)
    assert ev.depth == 1
    assert ev.context_label == "agent:code-reviewer"


def test_depth_returns_to_zero_after_agent_post():
    p = EventParser()
    p.parse(_pre("Agent", {"description": "reviewer"}, ts=1.0))
    p.parse(_pre("Read", {"file_path": "a.py"}, ts=1.1))
    p.parse(_post("Read", {"file_path": "a.py"}, ts=1.2))
    # Agent post — pops stack
    p.parse(_post("Agent", {"description": "reviewer"}, ts=2.0))
    # Tool after agent — back to depth 0
    ev = p.parse(_pre("Bash", {"command": "ls"}, ts=2.1))
    assert ev.depth == 0
    assert ev.context_label is None


def test_nested_agent_has_depth_two():
    p = EventParser()
    p.parse(_pre("Agent", {"description": "outer"}, ts=1.0))
    p.parse(_pre("Agent", {"description": "inner"}, ts=1.1))
    ev = p.parse(_pre("Read", {"file_path": "x.py"}, ts=1.2))
    assert ev.depth == 2
    assert ev.context_label == "agent:inner"


def test_skill_increments_depth():
    p = EventParser()
    p.parse(_pre("Skill", {"skill": "tdd"}, ts=1.0))
    ev = p.parse(_pre("Read", {"file_path": "a.py"}, ts=1.1))
    assert ev.depth == 1
    assert ev.context_label == "skill:tdd"


def test_agent_event_itself_has_depth_at_time_of_firing():
    p = EventParser()
    # Agent pre fires at depth 0 → AgentEvent.depth == 0
    ev = p.parse(_pre("Agent", {"description": "reviewer"}, ts=1.0))
    assert isinstance(ev, AgentEvent)
    assert ev.depth == 0


def test_stack_resets_on_new_parser_instance():
    p = EventParser()
    p.parse(_pre("Agent", {"description": "x"}, ts=1.0))
    p2 = EventParser()
    ev = p2.parse(_pre("Read", {"file_path": "a.py"}, ts=1.0))
    assert ev.depth == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_parser_hierarchy.py -v
```
Expected: FAIL — `ToolEvent has no attribute 'depth'` or depth assertions fail

- [ ] **Step 3: Update `EventParser` in `hud/parser.py`**

```python
from __future__ import annotations

from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent

_SUMMARY_KEYS: dict[str, list[str]] = {
    "Read": ["file_path"],
    "Bash": ["command"],
    "Edit": ["file_path"],
    "Write": ["file_path"],
    "Grep": ["pattern", "path"],
    "Glob": ["pattern"],
    "Agent": ["description"],
    "Skill": ["skill"],
}


def _extract_summary(tool_name: str, tool_input: dict) -> str:
    keys = _SUMMARY_KEYS.get(tool_name, [])
    parts = [str(tool_input.get(k, "")) for k in keys if k in tool_input]
    text = " ".join(parts) if parts else str(tool_input)
    return text[:60]


def _extract_tokens(raw: dict) -> tuple[int | None, int | None]:
    usage = raw.get("usage") or raw.get("token_usage") or {}
    inp = usage.get("input_tokens") or usage.get("prompt_tokens")
    out = usage.get("output_tokens") or usage.get("completion_tokens")
    return (int(inp) if inp is not None else None,
            int(out) if out is not None else None)


class EventParser:
    def __init__(self) -> None:
        self._pending: dict[tuple[str, str], float] = {}
        # Each entry: (label, tool_name) — tool_name used to match post for pop
        self._context_stack: list[tuple[str, str]] = []

    def _current_depth(self) -> int:
        return len(self._context_stack)

    def _current_label(self) -> str | None:
        return self._context_stack[-1][0] if self._context_stack else None

    def _pop_context(self, tool_name: str) -> None:
        for i in range(len(self._context_stack) - 1, -1, -1):
            if self._context_stack[i][1] == tool_name:
                self._context_stack.pop(i)
                break

    def parse(self, raw: dict) -> ToolEvent | AgentEvent | SkillEvent | StopEvent:
        hook_type = raw.get("hook_type", "")
        session_id = raw.get("session_id", "")
        ts = raw.get("ts", 0.0)

        if hook_type == "stop":
            return StopEvent(
                session_id=session_id,
                transcript_path=raw.get("transcript_path"),
                ts=ts,
            )

        tool_name = raw.get("tool_name", "")
        tool_input = raw.get("tool_input", {})

        # Agent pre: record in context stack, return AgentEvent at current depth
        if hook_type == "pre" and tool_name == "Agent":
            depth = self._current_depth()
            label = f"agent:{str(tool_input.get('description', ''))[:20]}"
            self._context_stack.append((label, "Agent"))
            return AgentEvent(
                session_id=session_id,
                child_description=str(tool_input.get("description", ""))[:60],
                ts=ts,
                depth=depth,
            )

        # Skill pre: record in context stack, return SkillEvent at current depth
        if hook_type == "pre" and tool_name == "Skill":
            depth = self._current_depth()
            label = f"skill:{str(tool_input.get('skill', ''))}"
            self._context_stack.append((label, "Skill"))
            return SkillEvent(
                session_id=session_id,
                skill_name=str(tool_input.get("skill", "")),
                ts=ts,
                depth=depth,
            )

        # Agent post: pop context stack, return AgentEvent
        if hook_type == "post" and tool_name == "Agent":
            self._pop_context("Agent")
            return AgentEvent(
                session_id=session_id,
                child_description=str(tool_input.get("description", ""))[:60],
                ts=ts,
                depth=self._current_depth(),
            )

        # Skill post: pop context stack, return SkillEvent
        if hook_type == "post" and tool_name == "Skill":
            self._pop_context("Skill")
            return SkillEvent(
                session_id=session_id,
                skill_name=str(tool_input.get("skill", "")),
                ts=ts,
                depth=self._current_depth(),
            )

        key = (session_id, tool_name)
        depth = self._current_depth()
        label = self._current_label()

        if hook_type == "pre":
            self._pending[key] = ts
            return ToolEvent(
                session_id=session_id,
                tool_name=tool_name,
                input_summary=_extract_summary(tool_name, tool_input),
                ts=ts,
                phase="pre",
                depth=depth,
                context_label=label,
            )

        # post
        pre_ts = self._pending.pop(key, None)
        duration_ms = int((ts - pre_ts) * 1000) if pre_ts is not None else None
        tool_output = raw.get("tool_response") or raw.get("tool_output") or {}
        error_text = tool_output.get("error") or tool_output.get("stderr") or ""
        success = not bool(error_text)
        error_excerpt = error_text[:80] if error_text else None
        input_tokens, output_tokens = _extract_tokens(raw)

        return ToolEvent(
            session_id=session_id,
            tool_name=tool_name,
            input_summary=_extract_summary(tool_name, tool_input),
            ts=ts,
            phase="post",
            success=success,
            duration_ms=duration_ms,
            error_excerpt=error_excerpt,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            depth=depth,
            context_label=label,
        )
```

- [ ] **Step 4: Run hierarchy tests**

```bash
pytest tests/test_parser_hierarchy.py -v
```
Expected: all PASS

- [ ] **Step 5: Run full suite**

```bash
pytest --tb=short -q
```
Expected: all PASS (existing parser tests still pass — new fields have defaults)

- [ ] **Step 6: Commit**

```bash
git add hud/parser.py tests/test_parser_hierarchy.py
git commit -m "feat: add context stack to EventParser for hierarchy depth tracking"
```

---

## Task 3: Add `cost.py`

**Files:**
- Create: `hud/cost.py`
- Create: `tests/test_cost.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cost.py`:

```python
from hud.cost import estimate_cost


def test_estimate_cost_zero_tokens():
    assert estimate_cost(0, 0) == 0.0


def test_estimate_cost_input_only():
    # 1M input tokens at $3/M = $3.0
    result = estimate_cost(1_000_000, 0)
    assert abs(result - 3.0) < 0.0001


def test_estimate_cost_output_only():
    # 1M output tokens at $15/M = $15.0
    result = estimate_cost(0, 1_000_000)
    assert abs(result - 15.0) < 0.0001


def test_estimate_cost_combined():
    # 100k input + 50k output
    result = estimate_cost(100_000, 50_000)
    expected = 100_000 / 1_000_000 * 3.0 + 50_000 / 1_000_000 * 15.0
    assert abs(result - expected) < 0.0001
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cost.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'hud.cost'`

- [ ] **Step 3: Create `hud/cost.py`**

```python
# Pricing for claude-sonnet-4-6 (model in use as of 2026-03-25).
# All tokens are priced at this rate regardless of actual model used.
# The `~` prefix in the display communicates this is an estimate.
# Update these constants when switching models or when pricing changes.
PRICE_PER_M_IN = 3.0    # $/M input tokens
PRICE_PER_M_OUT = 15.0  # $/M output tokens


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * PRICE_PER_M_IN
            + output_tokens / 1_000_000 * PRICE_PER_M_OUT)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_cost.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add hud/cost.py tests/test_cost.py
git commit -m "feat: add cost estimation module with claude-sonnet-4-6 pricing"
```

---

## Task 4: Update `SummaryWidget` with cost

**Files:**
- Modify: `hud/widgets/summary.py`
- Modify: `tests/test_app.py` (partial — just summary cost tests)

- [ ] **Step 1: Write the failing tests**

First, update the three existing tests in `tests/test_app.py` to patch `refresh` instead of `_render` (the correct Textual method):

```python
# In test_summary_counts, test_summary_reset, test_summary_token_accumulation:
# Change: patch.object(s, "_render")
# To:     patch.object(s, "refresh")
```

Then add the two new cost tests:

```python
def test_summary_cost_accumulates():
    from hud.widgets.summary import SummaryWidget
    from hud.models import ToolEvent
    from unittest.mock import patch
    s = SummaryWidget()
    with patch.object(s, "refresh"):
        s.update_event(ToolEvent(
            session_id="s", tool_name="Read", input_summary="x",
            ts=1.0, phase="post", success=True,
            input_tokens=1_000_000, output_tokens=0,
        ))
    assert abs(s._cost - 3.0) < 0.001


def test_summary_reset_clears_cost():
    from hud.widgets.summary import SummaryWidget
    from unittest.mock import patch
    s = SummaryWidget()
    s._cost = 5.0
    with patch.object(s, "refresh"):
        s.reset("new-session")
    assert s._cost == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_app.py::test_summary_cost_accumulates tests/test_app.py::test_summary_reset_clears_cost -v
```
Expected: FAIL — `SummaryWidget has no attribute '_cost'`

- [ ] **Step 3: Update `hud/widgets/summary.py`**

```python
from __future__ import annotations

from textual.widgets import Static
from rich.console import RichCast

from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent
from hud.cost import estimate_cost


class SummaryWidget(Static):
    def __init__(self) -> None:
        super().__init__()
        self._tools = 0
        self._agents = 0
        self._skills = 0
        self._errors = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost = 0.0
        self._session_id = ""

    def on_mount(self) -> None:
        self.border_title = "SUMMARY"

    def reset(self, session_id: str) -> None:
        self._tools = 0
        self._agents = 0
        self._skills = 0
        self._errors = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost = 0.0
        self._session_id = session_id
        self.refresh()

    def update_event(self, event: ToolEvent | AgentEvent | SkillEvent | StopEvent) -> None:
        if isinstance(event, ToolEvent) and event.phase == "post":
            self._tools += 1
            if event.success is False:
                self._errors += 1
            new_in = event.input_tokens or 0
            new_out = event.output_tokens or 0
            if new_in or new_out:
                self._input_tokens += new_in
                self._output_tokens += new_out
                self._cost += estimate_cost(new_in, new_out)
        elif isinstance(event, AgentEvent):
            self._agents += 1
        elif isinstance(event, SkillEvent):
            self._skills += 1
        self.refresh()

    def render(self) -> RichCast:
        sid = self._session_id[:8] if self._session_id else "--"
        tok_in = f"{self._input_tokens:,}" if self._input_tokens else "--"
        tok_out = f"{self._output_tokens:,}" if self._output_tokens else "--"
        return (
            f"[dim]{sid}[/dim]\n\n"
            f"skills:  {self._skills}\n"
            f"agents:  {self._agents}\n"
            f"tools:   {self._tools}\n"
            f"[red]errors:  {self._errors}[/red]\n\n"
            f"[dim]in:[/dim]  {tok_in}\n"
            f"[dim]out:[/dim] {tok_out}\n"
            f"~${self._cost:.3f}"
        )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_app.py -v
```
Expected: all PASS including new cost tests

- [ ] **Step 5: Commit**

```bash
git add hud/widgets/summary.py tests/test_app.py
git commit -m "feat: add cost tracking to SummaryWidget"
```

---

## Task 5: Create `ActiveWidget`

**Files:**
- Create: `hud/widgets/active.py`
- Create: `tests/test_active_widget.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_active_widget.py`:

```python
import time
from unittest.mock import patch
from hud.widgets.active import ActiveWidget
from hud.models import ToolEvent


def _pre_event(tool_name, summary="x", session_id="s", ts=None):
    return ToolEvent(
        session_id=session_id, tool_name=tool_name, input_summary=summary,
        ts=ts or time.time(), phase="pre",
    )


def _post_event(tool_name, session_id="s"):
    return ToolEvent(
        session_id=session_id, tool_name=tool_name, input_summary="x",
        ts=time.time(), phase="post", success=True,
    )


def test_add_pending_stores_entry():
    w = ActiveWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", "src/foo.py", ts=1000.0))
    assert len(w._pending) == 1


def test_remove_pending_fifo():
    w = ActiveWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", "a.py", ts=1000.0))
        w.add_pending(_pre_event("Read", "b.py", ts=1001.0))
        w.remove_pending(_post_event("Read"))
    # oldest (ts=1000.0) removed first
    assert len(w._pending) == 1
    remaining_key = list(w._pending.keys())[0]
    assert remaining_key[2] == 1001.0  # pre_ts of b.py


def test_remove_pending_no_match_is_noop():
    w = ActiveWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", ts=1000.0))
        w.remove_pending(_post_event("Bash"))  # different tool — no match
    assert len(w._pending) == 1


def test_reset_clears_pending():
    w = ActiveWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", ts=1000.0))
        w.reset()
    assert len(w._pending) == 0


def test_overflow_indicator_shown_when_more_than_four():
    w = ActiveWidget()
    with patch.object(w, "refresh"):
        for i in range(6):
            w.add_pending(_pre_event("Read", f"file{i}.py", ts=float(1000 + i)))
    from rich.text import Text
    rendered = w.render()
    assert isinstance(rendered, Text)
    plain = rendered.plain
    assert "+2 more" in plain


def test_render_shows_tool_name_and_summary():
    w = ActiveWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", "src/main.py", ts=time.time() - 0.5))
    from rich.text import Text
    rendered = w.render()
    assert isinstance(rendered, Text)
    plain = rendered.plain
    assert "Read" in plain
    assert "src/main.py" in plain
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_active_widget.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'hud.widgets.active'`

- [ ] **Step 3: Create `hud/widgets/active.py`**

```python
from __future__ import annotations

import time

from rich.text import Text
from textual.widget import Widget

from hud.models import ToolEvent


class ActiveWidget(Widget):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # key: (session_id, tool_name, pre_ts) — pre_ts disambiguates parallel same-tool calls
        # value: input_summary
        self._pending: dict[tuple[str, str, float], str] = {}

    def on_mount(self) -> None:
        self.border_title = "ACTIVE"
        self.set_interval(1.0, self.refresh)

    def add_pending(self, event: ToolEvent) -> None:
        """Add a pre-phase ToolEvent to the pending display."""
        self._pending[(event.session_id, event.tool_name, event.ts)] = event.input_summary
        self.refresh()

    def remove_pending(self, event: ToolEvent) -> None:
        """Remove the oldest matching pending entry (FIFO) for a post-phase ToolEvent."""
        matches = [(k, v) for k, v in self._pending.items()
                   if k[0] == event.session_id and k[1] == event.tool_name]
        if matches:
            oldest_key = min(matches, key=lambda x: x[0][2])[0]
            del self._pending[oldest_key]
        self.refresh()

    def reset(self) -> None:
        self._pending.clear()
        self.refresh()

    def render(self) -> Text:
        now = time.time()
        lines = []
        items = list(self._pending.items())
        for i, ((sid, tool_name, pre_ts), input_summary) in enumerate(items):
            if i >= 4:
                lines.append(f"[dim]+{len(items) - 4} more...[/dim]")
                break
            elapsed = now - pre_ts
            lines.append(f"[yellow][...][/yellow]  {tool_name}  {input_summary}  {elapsed:.1f}s")
        return Text.from_markup("\n".join(lines))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_active_widget.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add hud/widgets/active.py tests/test_active_widget.py
git commit -m "feat: add ActiveWidget for pending tool display with elapsed time"
```

---

## Task 6: Create `HistoryWidget`

**Files:**
- Create: `hud/widgets/history.py`
- Create: `tests/test_history_widget.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history_widget.py`:

```python
from collections import deque
from unittest.mock import patch, MagicMock
from hud.widgets.history import HistoryWidget
from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent


def _post_ok(tool_name="Read", summary="src/foo.py", depth=0, duration_ms=88):
    return ToolEvent(session_id="s", tool_name=tool_name, input_summary=summary,
                     ts=1.0, phase="post", success=True, duration_ms=duration_ms,
                     depth=depth)


def _post_err(tool_name="Bash", summary="npm test", depth=0, error="exit 1"):
    return ToolEvent(session_id="s", tool_name=tool_name, input_summary=summary,
                     ts=1.0, phase="post", success=False, error_excerpt=error,
                     depth=depth)


def test_add_event_newest_on_top():
    w = HistoryWidget()
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(_post_ok("Read", "a.py"))
        w.add_event(_post_ok("Bash", "ls"))
    # newest (Bash) is at index 0
    assert "Bash" in w._lines[0]
    assert "Read" in w._lines[1]


def test_pre_phase_event_is_ignored():
    w = HistoryWidget()
    pre = ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                    ts=1.0, phase="pre")
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(pre)
    assert len(w._lines) == 0


def test_reset_clears_and_adds_separator():
    w = HistoryWidget()
    w._lines.appendleft("old line")
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.reset("abc123")
    assert len(w._lines) == 1
    assert "abc123" in w._lines[0]


def test_indentation_for_depth_one():
    w = HistoryWidget()
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(_post_ok("Read", "foo.py", depth=1))
    assert w._lines[0].startswith("  ")  # 2-space indent


def test_no_indentation_for_depth_zero():
    w = HistoryWidget()
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(_post_ok("Read", "foo.py", depth=0))
    assert not w._lines[0].startswith(" ")


def test_error_excerpt_indented():
    w = HistoryWidget()
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(_post_err("Bash", "npm test", depth=0, error="exit 1"))
    # Should have 2 lines: event line + error excerpt
    assert len(w._lines) == 2
    assert w._lines[0].startswith("       ")  # 7 spaces for error excerpt (newest first)


def test_maxlen_500():
    w = HistoryWidget()
    with patch.object(w, "query_one", return_value=MagicMock()):
        for i in range(600):
            w.add_event(_post_ok("Read", f"file{i}.py"))
    assert len(w._lines) == 500


def test_agent_event_displayed():
    w = HistoryWidget()
    ev = AgentEvent(session_id="s", child_description="code-reviewer", ts=1.0, depth=0)
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(ev)
    assert "AGENT" in w._lines[0]
    assert "code-reviewer" in w._lines[0]


def test_skill_event_displayed():
    w = HistoryWidget()
    ev = SkillEvent(session_id="s", skill_name="tdd", ts=1.0, depth=0)
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(ev)
    assert "SKILL" in w._lines[0]
    assert "tdd" in w._lines[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_history_widget.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'hud.widgets.history'`

- [ ] **Step 3: Create `hud/widgets/history.py`**

```python
from __future__ import annotations

from collections import deque
from datetime import datetime

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent

_STYLE = {
    "ok":      "[green][OK][/green]",
    "err":     "[red][ERR][/red]",
    "skill":   "[purple][SKILL][/purple]",
    "agent":   "[blue][AGENT][/blue]",
    "stop":    "[dim][STOP][/dim]",
}


def _ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def _format_event(event: ToolEvent | AgentEvent | SkillEvent | StopEvent) -> list[str]:
    """Return list of lines (Rich markup strings) for an event. Newest line first."""
    indent = "  " * getattr(event, "depth", 0)

    if isinstance(event, AgentEvent):
        return [f"{indent}{_ts(event.ts)} {_STYLE['agent']} {event.child_description}"]

    if isinstance(event, SkillEvent):
        return [f"{indent}{_ts(event.ts)} {_STYLE['skill']} {event.skill_name}"]

    if isinstance(event, StopEvent):
        return [f"{_STYLE['stop']} session ended"]

    # ToolEvent post
    if isinstance(event, ToolEvent):
        if event.phase == "pre":
            return []  # pre-phase ignored
        dur = f" {event.duration_ms}ms" if event.duration_ms is not None else ""
        if event.success is False:
            err_indent = indent + "       "
            lines = [f"{indent}{_ts(event.ts)} {_STYLE['err']} {event.tool_name}  {event.input_summary}{dur}"]
            if event.error_excerpt:
                lines.append(f"{err_indent}{event.error_excerpt}")
            # Return error excerpt first (it's newer in append order, goes to top)
            return list(reversed(lines))
        return [f"{indent}{_ts(event.ts)} {_STYLE['ok']} {event.tool_name}  {event.input_summary}{dur}"]

    return []


class HistoryWidget(VerticalScroll):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._lines: deque[str] = deque(maxlen=500)

    def compose(self):
        yield Static("", id="history-content", markup=True)

    def on_mount(self) -> None:
        self.border_title = "HISTORY"

    def _refresh_content(self) -> None:
        self.query_one("#history-content", Static).update("\n".join(self._lines))

    def add_event(self, event: ToolEvent | AgentEvent | SkillEvent | StopEvent) -> None:
        lines = _format_event(event)
        for line in lines:
            self._lines.appendleft(line)
        if lines:
            self._refresh_content()

    def reset(self, session_id: str) -> None:
        self._lines.clear()
        self._lines.appendleft(f"[dim]--- new session: {session_id} ---[/dim]")
        self._refresh_content()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_history_widget.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add hud/widgets/history.py tests/test_history_widget.py
git commit -m "feat: add HistoryWidget with newest-on-top, indented hierarchy display"
```

---

## Task 7: Rewire `app.py` and delete `event_stream.py`

**Files:**
- Modify: `hud/app.py`
- Delete: `hud/widgets/event_stream.py`
- Rewrite: `tests/test_app.py`

- [ ] **Step 1: Rewrite `tests/test_app.py`**

```python
from unittest.mock import patch, MagicMock
from hud.models import ToolEvent, SkillEvent, AgentEvent, StopEvent
from hud.widgets.summary import SummaryWidget
from hud.widgets.active import ActiveWidget
from hud.widgets.history import HistoryWidget


# ── SummaryWidget tests (keep existing, these still pass) ──────────────────

def test_summary_counts():
    s = SummaryWidget()
    with patch.object(s, "refresh"):
        s.update_event(ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                                 ts=1.0, phase="post", success=True))
        s.update_event(ToolEvent(session_id="s", tool_name="Bash", input_summary="y",
                                 ts=2.0, phase="post", success=False))
        s.update_event(SkillEvent(session_id="s", skill_name="tdd", ts=3.0))
        s.update_event(AgentEvent(session_id="s", child_description="rev", ts=4.0))
    assert s._tools == 2
    assert s._errors == 1
    assert s._skills == 1
    assert s._agents == 1


def test_summary_reset():
    s = SummaryWidget()
    s._tools = 5
    with patch.object(s, "refresh"):
        s.reset("new-session")
    assert s._tools == 0
    assert s._session_id == "new-session"


def test_summary_token_accumulation():
    s = SummaryWidget()
    with patch.object(s, "refresh"):
        s.update_event(ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                                 ts=1.0, phase="post", success=True,
                                 input_tokens=100, output_tokens=50))
        s.update_event(ToolEvent(session_id="s", tool_name="Bash", input_summary="y",
                                 ts=2.0, phase="post", success=True,
                                 input_tokens=200, output_tokens=80))
    assert s._input_tokens == 300
    assert s._output_tokens == 130


def test_summary_cost_accumulates():
    s = SummaryWidget()
    with patch.object(s, "refresh"):
        s.update_event(ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                                 ts=1.0, phase="post", success=True,
                                 input_tokens=1_000_000, output_tokens=0))
    assert abs(s._cost - 3.0) < 0.001


def test_summary_reset_clears_cost():
    s = SummaryWidget()
    s._cost = 5.0
    with patch.object(s, "refresh"):
        s.reset("new-session")
    assert s._cost == 0.0


# ── Event routing tests ────────────────────────────────────────────────────

def test_pre_event_goes_to_active_only():
    active = ActiveWidget()
    history = HistoryWidget()
    summary = SummaryWidget()

    pre = ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                    ts=1.0, phase="pre")

    with patch.object(active, "refresh"), \
         patch.object(history, "query_one", return_value=MagicMock()), \
         patch.object(summary, "refresh"):
        active.add_pending(pre)

    assert len(active._pending) == 1
    assert len(history._lines) == 0


def test_post_event_goes_to_history_and_summary():
    active = ActiveWidget()
    history = HistoryWidget()
    summary = SummaryWidget()

    pre = ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                    ts=1.0, phase="pre")
    post = ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                     ts=2.0, phase="post", success=True)

    with patch.object(active, "refresh"), \
         patch.object(history, "query_one", return_value=MagicMock()), \
         patch.object(summary, "refresh"):
        active.add_pending(pre)
        active.remove_pending(post)
        history.add_event(post)
        summary.update_event(post)

    assert len(active._pending) == 0
    assert len(history._lines) == 1
    assert summary._tools == 1


def test_skill_event_goes_to_history_not_active():
    active = ActiveWidget()
    history = HistoryWidget()
    summary = SummaryWidget()

    ev = SkillEvent(session_id="s", skill_name="tdd", ts=1.0)

    with patch.object(active, "refresh"), \
         patch.object(history, "query_one", return_value=MagicMock()), \
         patch.object(summary, "refresh"):
        history.add_event(ev)
        summary.update_event(ev)

    assert len(active._pending) == 0
    assert len(history._lines) == 1
    assert summary._skills == 1


def test_session_switch_resets_all_widgets():
    active = ActiveWidget()
    history = HistoryWidget()
    summary = SummaryWidget()

    # Populate state
    with patch.object(active, "refresh"), \
         patch.object(history, "query_one", return_value=MagicMock()), \
         patch.object(summary, "refresh"):
        active.add_pending(ToolEvent(session_id="s", tool_name="Read",
                                     input_summary="x", ts=1.0, phase="pre"))
        summary._tools = 3
        summary._cost = 9.99
        # Reset all
        active.reset()
        history.reset("new-session")
        summary.reset("new-session")

    assert len(active._pending) == 0
    assert summary._tools == 0
    assert summary._cost == 0.0
    assert "new-session" in history._lines[0]
```

- [ ] **Step 2: Run new tests to see current state**

```bash
pytest tests/test_app.py -v
```
Note which pass and which fail — the routing tests will fail until app.py is wired.

- [ ] **Step 3: Rewrite `hud/app.py`**

```python
from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches

from hud.parser import EventParser
from hud.watcher import SessionWatcher
from hud.widgets.active import ActiveWidget
from hud.widgets.history import HistoryWidget
from hud.widgets.summary import SummaryWidget
from hud.models import ToolEvent

CSS = """
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
"""


class HudApp(App):
    CSS = CSS
    TITLE = "Claude HUD"

    def __init__(self, base_dir: str = "/tmp/claude-hud") -> None:
        super().__init__()
        self._watcher = SessionWatcher(base_dir)
        self._parser = EventParser()
        self._current_session: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical():
                yield ActiveWidget()
                yield HistoryWidget()
            yield SummaryWidget()

    async def on_mount(self) -> None:
        self.run_worker(self._watch_loop(), exclusive=True)

    async def _watch_loop(self) -> None:
        tail_task: asyncio.Task | None = None

        async def _tail_session(session_id: str) -> None:
            async for raw in self._watcher.tail(session_id):
                self._handle_raw(raw)

        while True:
            latest = self._watcher.discover_latest_session()
            if latest and latest != self._current_session:
                if tail_task and not tail_task.done():
                    tail_task.cancel()
                self._switch_session(latest)
                tail_task = asyncio.create_task(_tail_session(latest))
            await asyncio.sleep(0.5)

    def _switch_session(self, session_id: str) -> None:
        self._current_session = session_id
        self._parser = EventParser()
        try:
            self.query_one(ActiveWidget).reset()
            self.query_one(HistoryWidget).reset(session_id)
            self.query_one(SummaryWidget).reset(session_id)
        except NoMatches:
            pass

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
        else:
            history.add_event(event)
            summary.update_event(event)
```

- [ ] **Step 4: Delete `event_stream.py`**

```bash
git rm hud/widgets/event_stream.py
```

- [ ] **Step 5: Run full test suite**

```bash
pytest --tb=short -q
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add hud/app.py tests/test_app.py
git commit -m "feat: rewire app.py with Active/History layout, remove EventStreamWidget"
```

---

## Task 8: Smoke test end-to-end

- [ ] **Step 1: Start the HUD**

```bash
python -m hud watch
```

In a second terminal, manually trigger some hook events:

```bash
echo '{"tool_name":"Read","tool_input":{"file_path":"hud/app.py"}}' | CLAUDE_HUD_DIR=/tmp/claude-hud python hook.py pre
echo '{"tool_name":"Read","tool_input":{"file_path":"hud/app.py"},"tool_output":{"output":"..."}}' | CLAUDE_HUD_DIR=/tmp/claude-hud python hook.py post
echo '{"tool_name":"Agent","tool_input":{"description":"code-reviewer"}}' | CLAUDE_HUD_DIR=/tmp/claude-hud python hook.py pre
echo '{"tool_name":"Read","tool_input":{"file_path":"hud/parser.py"},"tool_output":{"output":"..."}}' | CLAUDE_HUD_DIR=/tmp/claude-hud python hook.py post
echo '{"tool_name":"Agent","tool_input":{"description":"code-reviewer"},"tool_output":{}}' | CLAUDE_HUD_DIR=/tmp/claude-hud python hook.py post
```

Expected in HUD:
- ACTIVE panel shows `[...] Read hud/app.py` during pre, clears on post
- HISTORY shows `[AGENT] code-reviewer` then indented `  [OK] Read hud/parser.py` beneath it
- SUMMARY shows tools: 2, agents: 1

- [ ] **Step 2: Final commit**

```bash
git add -A
git commit -m "chore: v2 complete — Active/History split, hierarchy, cost estimation"
```
