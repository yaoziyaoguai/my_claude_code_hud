# Current Widget Design

**Date:** 2026-03-26  
**Status:** Design Approved  
**Scope:** Replace ActiveWidget with CurrentWidget to display Claude Code session state

## Overview

Replace the `ActiveWidget` (which displays pending tools) with a new `CurrentWidget` that shows the current session state in a three-line hierarchical layout:

```
Model: claude-opus-4.6
Context: ████████░░ 82% (2000/2400)
Current: Bash (2.3s) ↻
```

## Data Sources and Calculations

### Model Name
- **Source:** `~/.claude/settings.json` (model field) or from hook payload
- **Display:** Current model name (e.g., "claude-opus-4.6")
- **Update:** Once at session initialization
- **Fallback:** "unknown" if not available

### Context Usage
- **Source:** `transcript_path` file from current session
- **Calculation:** 
  ```
  used = input_tokens + cache_write_tokens + cache_read_tokens + output_tokens
  total = 200000  # bytes for all Claude models
  percentage = (used / total) * 100
  ```
- **Display:** Progress bar + percentage + (used/total)
  - Example: `████████░░ 82% (2000/2400)`
- **Update:** After each post-phase hook event
- **Note:** All Claude models (Opus, Sonnet, Haiku) use 200k context window

### Current Tool
- **Source:** Most recent pre-phase hook event
- **Display:** Tool name + elapsed time + status indicator
  - Example: `Bash (2.3s) ↻`
- **Update:** 
  - Pre-phase: update tool name, start timing
  - Post-phase: remove tool (blank until next pre-phase)
- **Status Indicator:** 
  - `↻` = running (pre-phase active)
  - blank = idle (post-phase or waiting)
- **Timing:** Calculated as `now() - pre_phase_ts`, updated continuously

## UI Layout

```
┌─ CURRENT ──────────────────────────────┐
│ Model: claude-opus-4.6                 │
│ Context: ████████░░ 82% (2000/2400)   │
│ Current: Bash (2.3s) ↻                 │
└────────────────────────────────────────┘
```

### Styling
- Use Textual markup for colors and emphasis
- Model name: plain text
- Context bar: use rich progress bar visualization
- Current tool: escape user input to prevent markup injection
- Status icon: `↻` for running

## Implementation Changes

### Files to Modify

#### 1. `hud/widgets/active.py` → `hud/widgets/current.py`
- Rename class `ActiveWidget` to `CurrentWidget`
- Rewrite `render()` method to return three-line hierarchical layout
- Add `_read_model_from_settings()` method
- Add `_calculate_context_usage()` method
- Keep existing `add_pending()`, `remove_pending()`, `reset()` methods (still track pending for tool selection)

#### 2. `hud/app.py`
- Change import: `from hud.widgets.current import CurrentWidget`
- Change references: `ActiveWidget` → `CurrentWidget`
- No logic changes

#### 3. `tests/test_active_widget.py` → `tests/test_current_widget.py`
- Update test imports and class references
- Verify model reading logic
- Verify context calculation
- Verify three-line layout rendering

### Backward Compatibility
- No changes to hook data parsing
- No changes to event flow
- No changes to summary widget
- No changes to history widget
- Only display output changes

## Data Flow

1. **Hook receives pre-phase event**
   - Store tool name and timestamp
   - Trigger widget refresh
   - Display: `Current: Bash (0.0s) ↻`

2. **Hook receives post-phase event**
   - Read transcript file
   - Calculate new context percentage
   - Trigger widget refresh
   - Display: updated context bar and cleared current tool

3. **Continuous render loop**
   - Update elapsed time in real-time
   - Smooth display of `(Xs)` counter

## Error Handling

- **Model not found:** Display "unknown"
- **Transcript file missing:** Display "0% (0/200k)"
- **Invalid token counts:** Treat as 0
- **Malformed JSON in transcript:** Skip line, continue
- **User data with markup chars:** Escape using `textual.markup.escape()`

## Testing

- Unit tests for model reading
- Unit tests for context calculation (various token combinations)
- Unit tests for elapsed time display
- Integration test: full session flow
- Visual test: verify three-line layout renders correctly

## Scope Limitations

- Only changes the display of the widget (top-left panel)
- Does NOT change:
  - Event parsing logic
  - Hook handling
  - Summary widget
  - History widget
  - App layout
  - Any other components

## Future Enhancements (Out of Scope)

- Add cache hit percentage separately
- Add token/second throughput
- Add cost estimation per session
- Configurable context window size
