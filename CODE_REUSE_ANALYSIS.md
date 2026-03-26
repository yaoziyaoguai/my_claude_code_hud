# Code Reuse & Duplication Analysis

## Executive Summary

The diff introduces good separation of concerns with new display constants, but contains **3-4 extraction opportunities** with moderate to high impact for maintainability.

---

## 1. 🔴 HIGH PRIORITY: Repeated Event Type Discrimination Logic

### Problem
**Event type checking appears 6+ times** across multiple files, always following the same pattern:

```python
if isinstance(event, ToolEvent):
    # handle ToolEvent
elif isinstance(event, AgentEvent):
    # handle AgentEvent
elif isinstance(event, SkillEvent):
    # handle SkillEvent
```

### Locations
- **app.py** (lines 95, 101): Event phase filtering & routing
- **active.py** (lines 24-30): `_event_display()` method
- **history.py** (lines 21, 29, 40): `_format_event()` branches
- **summary.py** (lines 46, 59, 61): `update_event()` counting logic

### Recommendation: Extract a Type Registry Pattern

**File:** `hud/models.py` (add)

```python
from abc import ABC

class Event(ABC):
    """Base class for all events."""
    session_id: str
    ts: float
    depth: int = 0
    phase: Literal["pre", "post"] = "pre"

    def event_type(self) -> str:
        """Return canonical event type for routing."""
        raise NotImplementedError

# Then in ToolEvent, AgentEvent, SkillEvent:
def event_type(self) -> str:
    if isinstance(self, AgentEvent):
        return "agent"
    elif isinstance(self, SkillEvent):
        return "skill"
    return "tool"
```

**Impact:** Replace 6+ type checks with a single polymorphic method, reducing branching complexity by ~40%.

---

## 2. 🟡 MEDIUM PRIORITY: Phase Filtering (pre/post) Logic

### Problem
**Phase checking repeats 4 times** with nearly identical logic:

```python
if event.phase == "pre":
    # do X
elif event.phase == "post":
    # do Y
```

### Locations
- **app.py** (lines 95, 101): Conditional routing
- **history.py** (line 41): Suppress pre-phase ToolEvents
- **summary.py** (lines 46, 59, 61): Count only post-phase events
- **active.py** (implicit in add_pending/remove_pending separation)

### Current Workaround
Event models now have `phase` field (good), but no helper for common phase filtering.

### Recommendation: Add Phase Filter Helpers

**File:** `hud/models.py` (add to each dataclass)

```python
def is_pre(self) -> bool:
    return self.phase == "pre"

def is_post(self) -> bool:
    return self.phase == "post"
```

**Then in app.py:**
```python
# OLD:
if isinstance(event, ToolEvent) and event.phase == "pre":

# NEW:
if isinstance(event, ToolEvent) and event.is_pre():
```

**Impact:** Modest (readability + consistency), but prevents phase string typos.

---

## 3. 🟡 MEDIUM PRIORITY: Display Label Extraction (context_display_name → parent label)

### Problem
Dual responsibility conflict in `context_display_name()`:

**File:** `hud/widgets/display.py` (lines 34-41)
```python
def context_display_name(context_label: str | None) -> str:
    """Strip type prefix from context_label, returning the bare name."""
    if not context_label:
        return ""
    for prefix in ("agent:", "skill:"):
        if context_label.startswith(prefix):
            return context_label[len(prefix):]
    return context_label
```

**Usage in history.py (line 48):**
```python
parent = context_display_name(event.context_label) if event.context_label else "?"
```

### Issue
This function is doing **label parsing** (extracting name from "agent:description" format), but the format itself is defined in **parser.py (lines 93, 106)**:

```python
label = f"agent:{str(tool_input.get('description', ''))[:20]}"
label = f"skill:{str(tool_input.get('skill', ''))}"
```

**Coupling:** The prefix format ("agent:", "skill:") appears in two places (parser.py and display.py). If format changes, both must update.

### Recommendation: Centralize Label Format

**File:** `hud/models.py` (add)

```python
# Label format constants
LABEL_PREFIX_AGENT = "agent:"
LABEL_PREFIX_SKILL = "skill:"
LABEL_PREFIXES = frozenset({LABEL_PREFIX_AGENT, LABEL_PREFIX_SKILL})

def strip_context_prefix(context_label: str | None) -> str:
    """Extract display name from context_label by removing prefix."""
    if not context_label:
        return ""
    for prefix in LABEL_PREFIXES:
        if context_label.startswith(prefix):
            return context_label[len(prefix):]
    return context_label
```

**Then in parser.py:**
```python
from hud.models import LABEL_PREFIX_AGENT, LABEL_PREFIX_SKILL

label = f"{LABEL_PREFIX_AGENT}{str(tool_input.get('description', ''))[:20]}"
```

**Impact:** Prevents label format drift, centralizes contract between parser and display.

---

## 4. 🟡 MEDIUM PRIORITY: Cost Calculation Code Duplication

### Problem
Two separate cost estimation paths exist:

**In summary.py (lines 56-58):**
```python
new_in = event.input_tokens or 0
new_out = event.output_tokens or 0
if new_in or new_out:
    self._input_tokens += new_in
    self._output_tokens += new_out
    self._cost += estimate_cost(new_in, new_out)
```

**In app.py (lines 112-129):**
```python
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
```

### Issue
- `estimate_cost()` vs `estimate_cost_full()` are **not compatible** (second omits cache token prices)
- Per-tool accumulation (summary.py) vs transcript-wide totals (app.py) create two different cost models
- No clear priority when transcript totals are available (should they override?)

### Recommendation: Unify Cost Aggregation

**File:** `hud/cost.py` (add)

```python
@dataclass
class TokenCount:
    """Normalized token counts from any source."""
    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0

    @staticmethod
    def from_tool_event(event: ToolEvent) -> "TokenCount":
        return TokenCount(
            input_tokens=event.input_tokens or 0,
            output_tokens=event.output_tokens or 0,
        )

    @staticmethod
    def from_transcript_usage(usage: dict) -> "TokenCount":
        return TokenCount(
            input_tokens=usage.get("input_tokens") or 0,
            cache_write_tokens=usage.get("cache_creation_input_tokens") or 0,
            cache_read_tokens=usage.get("cache_read_input_tokens") or 0,
            output_tokens=usage.get("output_tokens") or 0,
        )

    def cost(self) -> float:
        return estimate_cost_full(
            self.input_tokens,
            self.cache_write_tokens,
            self.cache_read_tokens,
            self.output_tokens,
        )

    def __add__(self, other: "TokenCount") -> "TokenCount":
        return TokenCount(
            input_tokens=self.input_tokens + other.input_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )
```

**Then in summary.py:**
```python
from hud.cost import TokenCount

# In update_event:
tokens = TokenCount.from_tool_event(event)
self._accumulated = self._accumulated + tokens
self._cost = self._accumulated.cost()
```

**Then in app.py:**
```python
# In _update_cost_from_transcript:
total = TokenCount()
for d in transcript_lines:
    if d.get("type") == "assistant":
        usage = d.get("message", {}).get("usage", {})
        total = total + TokenCount.from_transcript_usage(usage)
summary.set_totals(total)
```

**Impact:** Single source of truth for cost calculation, easier to debug token accounting.

---

## 5. ✅ GOOD: Badge/Display Constants Already Extracted

**File:** `hud/widgets/display.py` contains:
- `TYPE_BADGE` — status/type display badges
- `PENDING_BADGE` — lightweight pending display badges
- `badge_and_label()` — event → badge mapping
- `context_display_name()` — context label parsing

This is well-designed. The constants are **reused consistently** across:
- active.py (line 61-62)
- history.py (lines 24, 32, 44, 49, 80)

✅ No duplication here; good pattern.

---

## 6. ✅ GOOD: Relative Path Utility Already Extracted

**File:** `hud/parser.py` lines 22-31

```python
def rel_path(value: str, cwd: str) -> str:
    """Return a path relative to cwd if value is absolute and under cwd, else return value unchanged."""
    ...
```

- Used in `_extract_summary()` (line 42)
- Centralized format logic for path relativization
- No duplication

✅ Good pattern.

---

## Summary Table

| Issue | Files | Occurrences | Priority | Refactor Effort | Maintainability Gain |
|-------|-------|-------------|----------|-----------------|----------------------|
| Event type discrimination | 4 files | 6+ | HIGH | Medium (add ABC) | High (reduce branches) |
| Phase filtering | 4 files | 4 | MEDIUM | Low (add 2 methods) | Medium (prevent typos) |
| Context label format | parser.py, display.py | 2 | MEDIUM | Low (constants) | Medium (prevent drift) |
| Cost aggregation | summary.py, app.py | 2 | MEDIUM | Medium (add class) | Medium (single source of truth) |
| Badge constants | ✅ | ✅ | N/A | N/A | ✅ |
| Path utilities | ✅ | ✅ | N/A | N/A | ✅ |

---

## Recommended Refactor Order

1. **Phase filtering helpers** (lowest risk, quick win)
2. **Context label format constants** (low risk, prevents bugs)
3. **Event type discrimination → polymorphism** (medium risk, high payoff)
4. **Cost aggregation unification** (medium risk, clarifies intent)

**Total effort:** ~3-4 hours for all 4 items.
**Benefit:** Reduced coupling, fewer branches, easier to maintain phase/type logic.
