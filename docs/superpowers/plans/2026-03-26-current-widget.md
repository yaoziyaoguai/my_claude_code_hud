# Current Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ActiveWidget with CurrentWidget to display Claude Code session state (model, context usage, current tool).

**Architecture:** Create new CurrentWidget that reads session data (transcript tokens, model name) and renders three-line status display. Keep existing pending tool tracking for internal state, but change display output only.

**Tech Stack:** Python 3.10+, Textual TUI, Rich for markup, pytest for testing

---

## Task 1: Create CurrentWidget Implementation

**Files:**
- Create: `hud/widgets/current.py`
- Test: `tests/test_current_widget.py`

### Step 1: Write failing test for model reading
- [ ] Create test file with failing test for `_read_model_from_settings()`

```python
# tests/test_current_widget.py
import time
from unittest.mock import patch, MagicMock
from hud.widgets.current import CurrentWidget
from hud.models import ToolEvent
from rich.text import Text


def test_read_model_from_settings_returns_model_name():
    """Test reading model from settings.json"""
    w = CurrentWidget()
    # Mock settings file with model
    with patch('builtins.open', create=True) as mock_file:
        mock_file.return_value.__enter__.return_value.read.return_value = '{"model": "claude-opus-4.6"}'
        with patch('json.load', return_value={"model": "claude-opus-4.6"}):
            model = w._read_model_from_settings()
    assert model == "claude-opus-4.6"


def test_read_model_from_settings_returns_unknown_on_missing():
    """Test fallback when settings not found"""
    w = CurrentWidget()
    with patch('builtins.open', side_effect=FileNotFoundError):
        model = w._read_model_from_settings()
    assert model == "unknown"
```

- [ ] **Run test to verify it fails**

```bash
cd /Users/jinkun.wang/work_space/my_claude_code_hud
python -m pytest tests/test_current_widget.py::test_read_model_from_settings_returns_model_name -xvs
```

Expected: FAIL - `CurrentWidget` not defined, `_read_model_from_settings` not found

### Step 2: Implement CurrentWidget with model reading
- [ ] Create `hud/widgets/current.py` with skeleton

```python
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from rich.text import Text
from textual.markup import escape
from textual.widget import Widget

from hud.models import ToolEvent, AgentEvent, SkillEvent
from hud.widgets.display import PENDING_BADGE, badge_and_label


class CurrentWidget(Widget):
    """Displays current Claude Code session state: model, context usage, current tool."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # key: (session_id, tool_name, pre_ts)
        # value: (input_summary, depth)
        self._pending: dict[tuple[str, str, float], tuple[str, int]] = {}
        self._current_model: str = "unknown"
        self._current_session_id: str | None = None
        self._context_tokens: int = 0

    def on_mount(self) -> None:
        self.border_title = "CURRENT"

    def _read_model_from_settings(self) -> str:
        """Read model name from ~/.claude/settings.json"""
        try:
            settings_path = Path.home() / ".claude" / "settings.json"
            with open(settings_path) as f:
                settings = json.load(f)
            return settings.get("model", "unknown")
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return "unknown"

    def add_pending(self, event: ToolEvent | AgentEvent | SkillEvent) -> None:
        """Add a pre-phase event to pending tracking."""
        tool_name, label = self._event_display(event)
        self._pending[(event.session_id, tool_name, event.ts)] = (label, event.depth)

    def remove_pending(self, event: ToolEvent | AgentEvent | SkillEvent) -> None:
        """Remove the oldest matching pending entry (FIFO)."""
        tool_name, _ = self._event_display(event)
        min_key = None
        min_ts = float('inf')
        for k in self._pending:
            if k[0] == event.session_id and k[1] == tool_name and k[2] < min_ts:
                min_ts = k[2]
                min_key = k
        if min_key:
            del self._pending[min_key]

    def reset(self, session_id: str) -> None:
        """Reset for new session."""
        self._pending.clear()
        self._current_session_id = session_id
        self._current_model = self._read_model_from_settings()
        self._context_tokens = 0

    def _event_display(self, event: ToolEvent | AgentEvent | SkillEvent) -> tuple[str, str]:
        """Extract tool name and display label from event."""
        if isinstance(event, (AgentEvent, SkillEvent)):
            return event.tool_name, event.tool_name
        return event.tool_name, event.input_summary

    def render(self) -> Text:
        """Render current state: model, context, current tool."""
        lines = []

        # Line 1: Model
        lines.append(f"Model: {self._current_model}")

        # Line 2: Context (placeholder for now)
        lines.append("Context: ██████░░░░ 60% (1200/2000)")

        # Line 3: Current tool (placeholder)
        current_tool = self._get_current_tool()
        if current_tool:
            lines.append(f"Current: {current_tool}")
        else:
            lines.append("Current: idle")

        return Text.from_markup("\n".join(lines))

    def _get_current_tool(self) -> str | None:
        """Get the most recent pending tool with elapsed time."""
        if not self._pending:
            return None

        # Get most recent entry (highest timestamp)
        latest = max(self._pending.items(), key=lambda x: x[0][2])
        (_, tool_name, pre_ts), (input_summary, depth) = latest

        elapsed = time.time() - pre_ts
        return f"{escape(tool_name)} ({elapsed:.1f}s) ↻"
```

- [ ] **Run test to verify it passes**

```bash
python -m pytest tests/test_current_widget.py::test_read_model_from_settings_returns_model_name -xvs
```

Expected: PASS

---

## Task 2: Implement Context Usage Calculation

**Files:**
- Modify: `hud/widgets/current.py`
- Test: `tests/test_current_widget.py`

### Step 1: Write test for context calculation
- [ ] Add test for `_calculate_context_usage()`

```python
def test_calculate_context_usage_returns_percentage():
    """Test context calculation from token counts."""
    w = CurrentWidget()
    # 2000 tokens used out of 200000 = 1%
    result = w._calculate_context_usage(
        input_tokens=1000,
        cache_write_tokens=500,
        cache_read_tokens=300,
        output_tokens=200
    )
    assert result == (2000, 1.0)  # (total_tokens, percentage)


def test_calculate_context_usage_handles_missing_values():
    """Test calculation with None values."""
    w = CurrentWidget()
    result = w._calculate_context_usage(
        input_tokens=500,
        cache_write_tokens=None,
        cache_read_tokens=None,
        output_tokens=None
    )
    assert result == (500, 0.25)  # 500 / 200000 * 100 = 0.25%
```

- [ ] **Add implementation to CurrentWidget**

```python
def _calculate_context_usage(
    self,
    input_tokens: int | None,
    cache_write_tokens: int | None,
    cache_read_tokens: int | None,
    output_tokens: int | None
) -> tuple[int, float]:
    """Calculate total tokens and percentage used.

    Returns: (total_tokens_used, percentage)
    """
    total = 0
    total += input_tokens or 0
    total += cache_write_tokens or 0
    total += cache_read_tokens or 0
    total += output_tokens or 0

    max_tokens = 200000
    percentage = (total / max_tokens) * 100 if max_tokens > 0 else 0.0

    return (total, percentage)
```

- [ ] **Run tests**

```bash
python -m pytest tests/test_current_widget.py::test_calculate_context_usage -xvs
```

Expected: PASS

---

## Task 3: Implement Transcript Reading and Context Update

**Files:**
- Modify: `hud/widgets/current.py`
- Test: `tests/test_current_widget.py`

### Step 1: Write test for reading transcript tokens
- [ ] Add test for `_read_transcript_tokens()`

```python
def test_read_transcript_tokens_sums_all_events():
    """Test reading and summing tokens from transcript."""
    w = CurrentWidget()
    # Create temporary transcript
    import tempfile
    import json

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write(json.dumps({
            "type": "assistant",
            "message": {
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 10,
                    "cache_read_input_tokens": 5
                }
            }
        }) + "\n")
        f.write(json.dumps({
            "type": "assistant",
            "message": {
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 75,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0
                }
            }
        }) + "\n")
        temp_path = f.name

    try:
        in_tok, cache_write, cache_read, out_tok = w._read_transcript_tokens(temp_path)
        assert in_tok == 300
        assert cache_write == 10
        assert cache_read == 5
        assert out_tok == 125
    finally:
        os.unlink(temp_path)
```

- [ ] **Add implementation**

```python
def _read_transcript_tokens(self, transcript_path: str) -> tuple[int, int, int, int]:
    """Read and sum all token counts from transcript file.

    Returns: (input_tokens, cache_write, cache_read, output_tokens)
    """
    in_tok = cache_write = cache_read = out_tok = 0
    try:
        with open(transcript_path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("type") == "assistant":
                    usage = d.get("message", {}).get("usage", {})
                    in_tok += usage.get("input_tokens") or 0
                    cache_write += usage.get("cache_creation_input_tokens") or 0
                    cache_read += usage.get("cache_read_input_tokens") or 0
                    out_tok += usage.get("output_tokens") or 0
    except OSError:
        pass
    return (in_tok, cache_write, cache_read, out_tok)
```

- [ ] **Run tests**

```bash
python -m pytest tests/test_current_widget.py::test_read_transcript_tokens -xvs
```

Expected: PASS

---

## Task 4: Update app.py to Use CurrentWidget

**Files:**
- Modify: `hud/app.py`

### Step 1: Update imports and references
- [ ] Update line 14: change import

```python
# OLD:
from hud.widgets.active import ActiveWidget

# NEW:
from hud.widgets.current import CurrentWidget
```

- [ ] Update line 54: change reference

```python
# OLD:
yield ActiveWidget()

# NEW:
yield CurrentWidget()
```

- [ ] Update line 81: change reference

```python
# OLD:
self.query_one(ActiveWidget).reset()

# NEW:
self.query_one(CurrentWidget).reset()
```

- [ ] Update line 90: change reference

```python
# OLD:
active = self.query_one(ActiveWidget)

# NEW:
current = self.query_one(CurrentWidget)
```

- [ ] Update lines 98, 100, 103, 105, 109, 110, 115: change `active.` to `current.`

```python
# Lines 98-100 (Agent/Skill pre)
# OLD: active.add_pending(event) ... active.refresh()
# NEW: current.add_pending(event) ... current.refresh()

# And so on for all other active references
```

- [ ] **Run app to verify imports work**

```bash
python -c "from hud.app import HudApp; print('Import successful')"
```

Expected: "Import successful"

- [ ] **Commit**

```bash
git add hud/app.py
git commit -m "refactor: update app.py to use CurrentWidget instead of ActiveWidget"
```

---

## Task 5: Update Tests

**Files:**
- Rename: `tests/test_active_widget.py` → `tests/test_current_widget.py`
- Modify: `tests/test_current_widget.py`

### Step 1: Rename and update test file
- [ ] Copy existing tests to new file with updated references

```python
# tests/test_current_widget.py
import time
import json
import tempfile
import os
from unittest.mock import patch
from hud.widgets.current import CurrentWidget
from hud.models import ToolEvent
from rich.text import Text


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
    w = CurrentWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", "src/foo.py", ts=1000.0))
    assert len(w._pending) == 1


def test_remove_pending_fifo():
    w = CurrentWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", "a.py", ts=1000.0))
        w.add_pending(_pre_event("Read", "b.py", ts=1001.0))
        w.remove_pending(_post_event("Read"))
    assert len(w._pending) == 1
    remaining_key = list(w._pending.keys())[0]
    assert remaining_key[2] == 1001.0


def test_remove_pending_no_match_is_noop():
    w = CurrentWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", ts=1000.0))
        w.remove_pending(_post_event("Bash"))
    assert len(w._pending) == 1


def test_reset_clears_pending_and_sets_model():
    w = CurrentWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", ts=1000.0))
    with patch.object(w, "_read_model_from_settings", return_value="claude-opus-4.6"):
        w.reset("session123")
    assert len(w._pending) == 0
    assert w._current_session_id == "session123"
    assert w._current_model == "claude-opus-4.6"


def test_calculate_context_usage_returns_percentage():
    w = CurrentWidget()
    total, percentage = w._calculate_context_usage(1000, 500, 300, 200)
    assert total == 2000
    assert percentage == 1.0  # 2000/200000


def test_calculate_context_usage_handles_none():
    w = CurrentWidget()
    total, percentage = w._calculate_context_usage(500, None, None, None)
    assert total == 500
    assert percentage == 0.25


def test_render_shows_model_and_idle_state():
    w = CurrentWidget()
    w._current_model = "claude-sonnet-4.6"
    rendered = w.render()
    assert isinstance(rendered, Text)
    plain = rendered.plain
    assert "Model: claude-sonnet-4.6" in plain
    assert "idle" in plain
```

- [ ] **Run all tests to verify they pass**

```bash
python -m pytest tests/test_current_widget.py -xvs
```

Expected: All PASS

- [ ] **Delete old test file**

```bash
rm tests/test_active_widget.py
```

- [ ] **Commit**

```bash
git add tests/test_current_widget.py
git rm tests/test_active_widget.py
git commit -m "test: replace active widget tests with current widget tests"
```

---

## Task 6: Update render() with Real Data

**Files:**
- Modify: `hud/widgets/current.py`

### Step 1: Implement full render() method
- [ ] Replace placeholder render() with full implementation

```python
def render(self) -> Text:
    """Render current state: model, context, current tool."""
    lines = []

    # Line 1: Model
    lines.append(f"Model: {self._current_model}")

    # Line 2: Context with progress bar
    total_tokens, percentage = self._calculate_context_usage(
        self._context_tokens, 0, 0, 0  # TODO: get from transcript
    )
    used = min(int(percentage / 10), 10)  # 10 chars for bar
    bar = "█" * used + "░" * (10 - used)
    formatted_tokens = f"({total_tokens}/200000)" if total_tokens > 0 else "(0/200000)"
    lines.append(f"Context: {bar} {percentage:.0f}% {formatted_tokens}")

    # Line 3: Current tool with elapsed time
    current = self._get_current_tool()
    if current:
        lines.append(f"Current: {current}")
    else:
        lines.append("Current: idle")

    return Text.from_markup("\n".join(lines))
```

- [ ] **Add method to update context from transcript**

```python
def update_context_from_transcript(self, transcript_path: str | None) -> None:
    """Read token counts from transcript and update context display."""
    if not transcript_path:
        return
    in_tok, cache_write, cache_read, out_tok = self._read_transcript_tokens(transcript_path)
    self._context_tokens = in_tok + cache_write + cache_read + out_tok
```

- [ ] **Update app.py to call this method after post-phase**

In `hud/app.py`, update the post-phase handler to call `update_context_from_transcript()`:

```python
# Around line 113-115 (ToolEvent post)
else:  # post
    current.remove_pending(event)
    current.update_context_from_transcript(event.context_label)  # NEW LINE
    history.add_event(event)
    summary.update_event(event)
    current.refresh()
```

Wait, we need the transcript_path. Let me check the event structure... It should be in the summary update. Actually, for now let's keep it simple and store it in the app.

Actually, simpler approach: store the transcript_path when we see it in a stop event.

- [ ] **Revert that, use a simpler approach:**

Add to CurrentWidget:

```python
def set_transcript_path(self, transcript_path: str | None) -> None:
    """Set current session's transcript path for context calculation."""
    if transcript_path:
        self.update_context_from_transcript(transcript_path)
```

And in app.py at line 120-121 (StopEvent handling):

```python
if isinstance(event, StopEvent) and event.transcript_path:
    current.set_transcript_path(event.transcript_path)  # NEW
    self._update_cost_from_transcript(event.transcript_path, summary)
```

- [ ] **Run tests again**

```bash
python -m pytest tests/test_current_widget.py -xvs
```

Expected: All PASS

- [ ] **Manual test: run HUD and verify display**

```bash
python -m hud watch &
# Switch to another terminal and run: claude
# Verify HUD shows: Model, Context bar, Current tool
```

Expected: Three-line display with real data

- [ ] **Commit**

```bash
git add hud/widgets/current.py hud/app.py
git commit -m "feat: implement full current widget with context and tool display"
```

---

## Task 7: Final Polish and Testing

**Files:**
- Verify: All files
- Test: Integration

### Step 1: Run full test suite
- [ ] Run all tests

```bash
python -m pytest --tb=short
```

Expected: All tests pass

### Step 2: Manual integration test
- [ ] Start HUD: `python -m hud watch &`
- [ ] Run claude in another terminal: `claude`
- [ ] Execute several tools and verify:
  - Model name displays correctly
  - Context bar updates with each tool execution
  - Current tool shows and updates elapsed time
  - No errors in terminal

### Step 3: Final commit and summary
- [ ] Create summary commit if needed

```bash
git log --oneline -7
```

Should show:
- current widget implementation complete
- app.py updated
- tests updated
- etc.

---

## Summary of Changes

| File | Action | Changes |
|------|--------|---------|
| `hud/widgets/current.py` | Create | New 200-line CurrentWidget class |
| `hud/app.py` | Modify | Update imports and 7 references (active → current) |
| `tests/test_current_widget.py` | Create | 12+ test cases for new widget |
| `tests/test_active_widget.py` | Delete | Replaced by test_current_widget.py |

Total: ~300 lines of new/modified code, TDD throughout, frequent commits.
