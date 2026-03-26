# Quick Reference: Duplication Map

Visual summary of what repeats across the codebase.

---

## 1. Event Type Discrimination Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│ REPEATED 6+ TIMES across 4 files                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  if isinstance(event, ToolEvent):                               │
│      # handle ToolEvent                                         │
│  elif isinstance(event, AgentEvent):                            │
│      # handle AgentEvent                                        │
│  elif isinstance(event, SkillEvent):                            │
│      # handle SkillEvent                                        │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│ LOCATIONS:                                                      │
│                                                                   │
│ 1. app.py:95-100          — Route pre-phase to active          │
│ 2. app.py:101-104         — Route post-phase to history/summary│
│ 3. active.py:24-30        — Extract display label              │
│ 4. history.py:21-44       — Format event for display           │
│ 5. summary.py:46-62       — Accumulate counts                  │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│ SOLUTION: Polymorphic event_type() method (Optional)            │
│ or: Keep isinstance but use in fewer places                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Phase Filtering Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│ REPEATED 4 TIMES across 3 files                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  if event.phase == "pre":                                      │
│      # do something                                            │
│  elif event.phase == "post":                                   │
│      # do something else                                       │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│ LOCATIONS:                                                      │
│                                                                   │
│ • app.py:95              — isinstance(...) and event.phase == "pre"
│ • app.py:101             — isinstance(...) and event.phase == "post"
│ • summary.py:46, 59, 61  — Three separate checks              │
│ • history.py:23, 31, 41  — Three separate checks              │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│ SOLUTION: Add is_pre(), is_post() helpers to models            │
│                                                                   │
│ OLD: if event.phase == "pre":                                  │
│ NEW: if event.is_pre():                                        │
│                                                                   │
│ BENEFIT: Typo prevention, readability                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Context Label Format Coupling

```
┌─────────────────────────────────────────────────────────────────┐
│ DUAL OWNERSHIP: parser.py writes format, display.py reads it  │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│ PARSER.PY (lines 93, 106):                                    │
│  label = f"agent:{description}"                               │
│  label = f"skill:{skill_name}"                                │
│                                                                   │
│ DISPLAY.PY (lines 34-41):                                     │
│  for prefix in ("agent:", "skill:"):                          │
│      if context_label.startswith(prefix):                     │
│          return context_label[len(prefix):]                   │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│ RISK: If format changes in parser.py, display.py breaks       │
│       (no build-time check, runtime bug)                       │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│ SOLUTION: Define constants in models.py                        │
│                                                                   │
│ LABEL_PREFIX_AGENT = "agent:"                                 │
│ LABEL_PREFIX_SKILL = "skill:"                                 │
│                                                                   │
│ Both files import and use these constants                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Cost Calculation Divergence

```
┌─────────────────────────────────────────────────────────────────┐
│ TWO INDEPENDENT PATHS to calculate cost                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│ PATH 1: Per-tool accumulation (summary.py:56-58)              │
│  ├─ Accumulates estimate_cost(in, out) per ToolEvent          │
│  └─ Runs during live session                                  │
│                                                                   │
│ PATH 2: Transcript totals (app.py:112-129)                   │
│  ├─ Sums estimate_cost_full(in, cache_w, cache_r, out)       │
│  └─ Runs at session end from transcript                       │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│ ISSUE 1: Different function signatures                         │
│  estimate_cost(in, out)                                       │
│  estimate_cost_full(in, cache_w, cache_r, out)               │
│                                                                   │
│ ISSUE 2: No cache token accounting in live path               │
│  (estimate_cost doesn't know about cache_creation/read)       │
│                                                                   │
│ ISSUE 3: Unclear merge strategy                               │
│  (does transcript total override? or accumulate?)             │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│ SOLUTION: TokenCount class                                     │
│  ├─ from_tool_event()      — normalize tool event input       │
│  ├─ from_transcript_usage() — normalize transcript usage dict │
│  ├─ cost()                 — calculate full cost              │
│  └─ __add__()              — accumulate token counts          │
│                                                                   │
│ Both paths use same TokenCount class, same cost() formula     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. ✅ Good Patterns (Already Applied)

### Badge/Display Constants
```
hud/widgets/display.py
├── TYPE_BADGE          → Used in history.py, active.py ✅
├── PENDING_BADGE       → Used in active.py ✅
├── badge_and_label()   → Used in active.py ✅
└── context_display_name() → Used in history.py ✅

✅ No duplication: centralized, reused consistently
```

### Relative Path Utility
```
hud/parser.py:rel_path()
└── Used in _extract_summary() at lines 41-42 ✅

✅ No duplication: defined once, used where needed
```

---

## Refactor Priority Matrix

```
                  EFFORT
             Low ←────→ High
        ┌──────────────────────────┐
   High │                          │
        │ Phase helpers   Cost     │
  I     │ (1: EASY)       (3: MED) │
  M     │                          │
  P     │ Label format            │
  A     │ (2: EASY)               │
  C     │                          │
  T Low │                          │
        │ Polymorphism (4: HARD)  │
        └──────────────────────────┘

RECOMMENDATION:
Start with 1 & 2 (quick wins, high ROI)
Then 3 (higher effort but clearer code)
Defer 4 (only if adding more event types)
```

---

## Implementation Roadmap

### Week 1: Low-Risk Wins

**Monday:**
- [ ] Add `is_pre()`, `is_post()` methods to models
- [ ] Update 9 call sites to use new helpers
- [ ] Run tests → should all pass

**Tuesday:**
- [ ] Define label format constants in models
- [ ] Update parser.py to use constants
- [ ] Update display.py context_display_name()
- [ ] Run tests → should all pass

### Week 2: Consolidate Cost Logic

**Wednesday:**
- [ ] Add TokenCount class to cost.py
- [ ] Update summary.py to use TokenCount
- [ ] Update app.py to use TokenCount
- [ ] Run tests → verify cost accumulation

**Thursday:**
- [ ] Manual testing: real Claude Code session
- [ ] Verify cost totals match transcript
- [ ] Document in project memory

### Week 3+: Optional Polymorphism

- [ ] Design event base class (if needed)
- [ ] Migrate dispatch logic
- [ ] Add tests for new dispatch
- [ ] Low priority unless adding event types

---

## Files Affected by Each Refactoring

### Refactoring 1: Phase Helpers
```
hud/models.py          — Add is_pre(), is_post()
hud/app.py             — Replace 2 checks
hud/summary.py         — Replace 5 checks
hud/history.py         — Replace 3 checks
Tests: No changes needed (same behavior)
```

### Refactoring 2: Label Format Constants
```
hud/models.py          — Add constants + function
hud/parser.py          — Import & use constants (2 locations)
hud/widgets/display.py — Update context_display_name()
Tests: No changes needed
```

### Refactoring 3: Cost Aggregation
```
hud/cost.py            — Add TokenCount class
hud/summary.py         — Refactor token tracking
hud/app.py             — Simplify _update_cost_from_transcript()
Tests: test_app.py may need minor updates
```

### Refactoring 4: Polymorphism (Optional)
```
hud/models.py          — Major: add Event base class
hud/app.py             — Update dispatch logic
hud/parser.py          — Update return types
hud/widgets/*.py       — Update isinstance chains
Tests: Significant updates
```

---

## Rollback Plan

All refactorings are localized to single modules or tightly coupled pairs.

**If something breaks:**
1. Run `git diff HEAD` to see what changed
2. Revert affected file: `git checkout HEAD -- <file>`
3. Re-apply changes incrementally with more testing

**No cascading failures expected** because:
- Changes are syntax-preserving (same inputs/outputs)
- Type system catches most errors (dataclasses, type hints)
- Test suite covers all user-facing behavior

---

## Summary

**High-Priority Wins:**
- 🟢 Phase helpers: 5 min coding, 9 replacements
- 🟢 Label format: 10 min coding, centralizes contract

**Medium-Priority:**
- 🟡 Cost aggregation: 30 min coding, clarifies intent

**Low-Priority (Nice-to-have):**
- 🔵 Polymorphism: 1 hour coding, only if extensibility needed

**Total potential gain:** ~40% fewer duplicated patterns, fewer type-related bugs.
