# Implementation Recipes for Code Reuse Improvements

Quick reference for applying each refactoring.

---

## Recipe 1: Add Phase Filter Methods to Models

**Files to modify:** `hud/models.py`

**Add to each dataclass (ToolEvent, AgentEvent, SkillEvent):**

```python
def is_pre(self) -> bool:
    """Return True if this is a pre-phase event."""
    return self.phase == "pre"

def is_post(self) -> bool:
    """Return True if this is a post-phase event."""
    return self.phase == "post"
```

**Update locations:**

| File | Line | Old | New |
|------|------|-----|-----|
| app.py | 95 | `if isinstance(event, (ToolEvent, AgentEvent, SkillEvent)) and event.phase == "pre":` | `if isinstance(event, (ToolEvent, AgentEvent, SkillEvent)) and event.is_pre():` |
| app.py | 101 | `elif isinstance(event, (ToolEvent, AgentEvent, SkillEvent)) and event.phase == "post":` | `elif isinstance(event, (ToolEvent, AgentEvent, SkillEvent)) and event.is_post():` |
| summary.py | 46 | `if isinstance(event, ToolEvent) and event.phase == "post":` | `if isinstance(event, ToolEvent) and event.is_post():` |
| summary.py | 59 | `elif isinstance(event, AgentEvent) and event.phase == "post":` | `elif isinstance(event, AgentEvent) and event.is_post():` |
| summary.py | 61 | `elif isinstance(event, SkillEvent) and event.phase == "post":` | `elif isinstance(event, SkillEvent) and event.is_post():` |
| history.py | 41 | `if event.phase == "pre":` | `if event.is_pre():` |
| history.py | 23 | `if event.phase == "pre":` | `if event.is_pre():` |
| history.py | 31 | `if event.phase == "pre":` | `if event.is_pre():` |

**Estimated effort:** 5 minutes
**Risk:** Minimal (pure rename, no logic change)
**Benefit:** Prevents phase string typos, improves readability

---

## Recipe 2: Centralize Context Label Format

**Files to modify:** `hud/models.py`, `hud/parser.py`

**In models.py (add after imports):**

```python
# Context label format constants — shared contract between parser and display
LABEL_PREFIX_AGENT = "agent:"
LABEL_PREFIX_SKILL = "skill:"
LABEL_PREFIXES = frozenset({LABEL_PREFIX_AGENT, LABEL_PREFIX_SKILL})

def strip_context_prefix(context_label: str | None) -> str:
    """Extract display name from context_label by removing prefix.

    Example: "agent:foo" → "foo", "skill:bar" → "bar"
    """
    if not context_label:
        return ""
    for prefix in LABEL_PREFIXES:
        if context_label.startswith(prefix):
            return context_label[len(prefix):]
    return context_label
```

**In parser.py (update lines 93 & 106):**

```python
# OLD (line 93):
label = f"agent:{str(tool_input.get('description', ''))[:20]}"

# NEW:
from hud.models import LABEL_PREFIX_AGENT
label = f"{LABEL_PREFIX_AGENT}{str(tool_input.get('description', ''))[:20]}"

# OLD (line 106):
label = f"skill:{str(tool_input.get('skill', ''))}"

# NEW:
from hud.models import LABEL_PREFIX_SKILL
label = f"{LABEL_PREFIX_SKILL}{str(tool_input.get('skill', ''))}"
```

**In display.py (update context_display_name, line 34):**

```python
# OLD:
def context_display_name(context_label: str | None) -> str:
    """Strip type prefix from context_label, returning the bare name."""
    if not context_label:
        return ""
    for prefix in ("agent:", "skill:"):
        if context_label.startswith(prefix):
            return context_label[len(prefix):]
    return context_label

# NEW:
from hud.models import strip_context_prefix

def context_display_name(context_label: str | None) -> str:
    """Strip type prefix from context_label, returning the bare name."""
    return strip_context_prefix(context_label)
```

**Estimated effort:** 10 minutes
**Risk:** Very low (no behavior change, pure extraction)
**Benefit:** Single source of truth for label format; prevents drift if prefixes change

---

## Recipe 3: Unify Cost Aggregation

**Files to modify:** `hud/cost.py`, `hud/summary.py`, `hud/app.py`

**In cost.py (add at end):**

```python
from dataclasses import dataclass

@dataclass
class TokenCount:
    """Normalized token counts from any source.

    Combines input, cache, and output tokens into a single accounting unit.
    """
    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0

    @staticmethod
    def from_tool_event(event) -> "TokenCount":
        """Extract token counts from a post-phase ToolEvent."""
        from hud.models import ToolEvent
        if not isinstance(event, ToolEvent) or not event.is_post():
            return TokenCount()
        return TokenCount(
            input_tokens=event.input_tokens or 0,
            output_tokens=event.output_tokens or 0,
        )

    @staticmethod
    def from_transcript_usage(usage: dict) -> "TokenCount":
        """Extract token counts from Claude transcript usage dict."""
        return TokenCount(
            input_tokens=usage.get("input_tokens") or 0,
            cache_write_tokens=usage.get("cache_creation_input_tokens") or 0,
            cache_read_tokens=usage.get("cache_read_input_tokens") or 0,
            output_tokens=usage.get("output_tokens") or 0,
        )

    def cost(self) -> float:
        """Calculate cost of this token batch."""
        return estimate_cost_full(
            self.input_tokens,
            self.cache_write_tokens,
            self.cache_read_tokens,
            self.output_tokens,
        )

    def __add__(self, other: "TokenCount") -> "TokenCount":
        """Accumulate two token counts."""
        return TokenCount(
            input_tokens=self.input_tokens + other.input_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )
```

**In summary.py (update __init__ and update_event):**

```python
# OLD __init__:
def __init__(self) -> None:
    super().__init__()
    self._tools = 0
    self._subagents = 0
    self._agents = 0
    self._skills = 0
    self._errors = 0
    self._input_tokens = 0
    self._output_tokens = 0
    self._cost = 0.0
    self._session_id = ""

# NEW __init__:
from hud.cost import TokenCount

def __init__(self) -> None:
    super().__init__()
    self._tools = 0
    self._subagents = 0
    self._agents = 0
    self._skills = 0
    self._errors = 0
    self._accumulated = TokenCount()
    self._session_id = ""

# OLD reset:
def reset(self, session_id: str) -> None:
    self._tools = 0
    self._subagents = 0
    self._agents = 0
    self._skills = 0
    self._errors = 0
    self._input_tokens = 0
    self._output_tokens = 0
    self._cost = 0.0
    self._session_id = session_id
    self.refresh()

# NEW reset:
def reset(self, session_id: str) -> None:
    self._tools = 0
    self._subagents = 0
    self._agents = 0
    self._skills = 0
    self._errors = 0
    self._accumulated = TokenCount()
    self._session_id = session_id
    self.refresh()

# OLD update_event (ToolEvent section):
if isinstance(event, ToolEvent) and event.phase == "post":
    if event.depth > 0:
        self._subagents += 1
    else:
        self._tools += 1
    if event.success is False:
        self._errors += 1
    new_in = event.input_tokens or 0
    new_out = event.output_tokens or 0
    if new_in or new_out:
        self._input_tokens += new_in
        self._output_tokens += new_out
        self._cost += estimate_cost(new_in, new_out)

# NEW update_event (ToolEvent section):
if isinstance(event, ToolEvent) and event.is_post():
    if event.depth > 0:
        self._subagents += 1
    else:
        self._tools += 1
    if event.success is False:
        self._errors += 1
    tokens = TokenCount.from_tool_event(event)
    self._accumulated = self._accumulated + tokens

# OLD render (token display):
tok_in = f"{self._input_tokens:,}" if self._input_tokens else "--"
tok_out = f"{self._output_tokens:,}" if self._output_tokens else "--"
...
f"~${self._cost:.3f}"

# NEW render (token display):
tok_in = f"{self._accumulated.input_tokens:,}" if self._accumulated.input_tokens else "--"
tok_out = f"{self._accumulated.output_tokens:,}" if self._accumulated.output_tokens else "--"
...
f"~${self._accumulated.cost():.3f}"
```

**In app.py (update _update_cost_from_transcript):**

```python
# OLD:
def _update_cost_from_transcript(self, path: str, summary: SummaryWidget) -> None:
    in_tok = cache_write = cache_read = out_tok = 0
    try:
        with open(path) as f:
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
        return
    cost = estimate_cost_full(in_tok, cache_write, cache_read, out_tok)
    summary.set_totals(in_tok + cache_write + cache_read, out_tok, cost)

# NEW:
from hud.cost import TokenCount

def _update_cost_from_transcript(self, path: str, summary: SummaryWidget) -> None:
    total = TokenCount()
    try:
        with open(path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("type") == "assistant":
                    usage = d.get("message", {}).get("usage", {})
                    total = total + TokenCount.from_transcript_usage(usage)
    except OSError:
        return
    summary.set_totals(
        total.input_tokens + total.cache_write_tokens + total.cache_read_tokens,
        total.output_tokens,
        total.cost(),
    )
```

**Also update SummaryWidget.set_totals to take a TokenCount (optional, but cleaner):**

```python
# OLD:
def set_totals(self, input_tokens: int, output_tokens: int, cost: float) -> None:
    """Override accumulated per-tool counts with authoritative transcript totals."""
    self._input_tokens = input_tokens
    self._output_tokens = output_tokens
    self._cost = cost
    self.refresh()

# NEW:
def set_totals(self, input_tokens: int, output_tokens: int, cost: float) -> None:
    """Override accumulated per-tool counts with authoritative transcript totals."""
    self._accumulated = TokenCount(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    # Note: cost is derived from _accumulated.cost(), not stored directly
    self.refresh()
```

**Estimated effort:** 30 minutes
**Risk:** Low (same outputs, refactored logic)
**Benefit:** Single cost calculation path, easier debugging, clearer token accounting

---

## Recipe 4: Event Type Polymorphism (Optional, Higher Risk)

This requires adding a base class, which changes the model structure. **Lower priority** than the above three.

**Files to modify:** `hud/models.py` (major)

**Add base class:**

```python
from abc import ABC
from dataclasses import dataclass

@dataclass
class Event(ABC):
    """Base event class for polymorphic dispatch."""
    session_id: str
    ts: float
    depth: int = 0

    def event_type(self) -> str:
        """Return canonical type string for routing ('tool', 'agent', 'skill', 'stop')."""
        raise NotImplementedError
```

**Update each event to inherit:**

```python
@dataclass
class ToolEvent(Event):
    ...
    def event_type(self) -> str:
        return "tool"

@dataclass
class AgentEvent(Event):
    ...
    def event_type(self) -> str:
        return "agent"

# etc.
```

**Then in app.py (eliminate isinstance chains):**

```python
# OLD:
if isinstance(event, ToolEvent) and event.is_pre():
    active.add_pending(event)
    if isinstance(event, AgentEvent):
        history.add_event(event)
    elif isinstance(event, SkillEvent):
        history.add_event(event)

# NEW:
if event.event_type() != "stop" and event.is_pre():
    active.add_pending(event)
    if event.event_type() in ("agent", "skill"):
        history.add_event(event)
```

**Estimated effort:** 1 hour (requires testing type dispatch)
**Risk:** Medium (changes dispatch patterns, must update all type checks)
**Benefit:** More extensible if new event types added later

---

## Testing Checklist After Refactoring

- [ ] Run `pytest tests/` — all 28 tests pass
- [ ] `pytest tests/test_history_widget.py::test_indentation_for_depth_one` — depth > 0 still shows context
- [ ] `pytest tests/test_app.py::test_summary_counts` — token accumulation unchanged
- [ ] Manual test: `python -m hud watch` alongside Claude Code session
  - [ ] Agent/Skill events display in history with correct phase
  - [ ] Cost totals match transcript
  - [ ] No typo-related crashes on phase checks

---

## Recommended Merge Order

1. **Recipe 1** (Phase methods) → merge immediately, minimal risk
2. **Recipe 2** (Label format) → merge next, prevents bugs
3. **Recipe 3** (Cost aggregation) → merge after thorough testing
4. **Recipe 4** (Polymorphism) → defer unless you plan to add more event types

**Commit messages:**

```
refactor: add phase checking helpers to event models

refactor: centralize context label format constants in models

refactor: unify cost aggregation with TokenCount class

refactor(optional): add polymorphic event dispatch
```
