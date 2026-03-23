# Claude HUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real-time TUI monitoring sidebar for Claude Code that displays tool calls, agent/skill activity, and token usage via Claude Code hooks.

**Architecture:** Claude Code hooks write events to JSONL files in `/tmp/claude-hud/`. A Textual TUI app watches those files and renders a two-panel layout (event stream + summary). `hook.py` is the bridge — a tiny script registered in `settings.json` that reads hook stdin and appends to the log.

**Tech Stack:** Python 3.10+, Textual (TUI), watchfiles (file monitoring), pytest (testing)

**Spec:** `docs/superpowers/specs/2026-03-24-claude-hud-design.md`

---

## File Structure

```
claude-hud/
├── pyproject.toml             # Package config, dependencies, entry point
├── hud/
│   ├── __init__.py
│   ├── __main__.py            # CLI: `python -m hud watch` / `python -m hud install`
│   ├── models.py              # Event dataclasses (ToolEvent, AgentEvent, SkillEvent, StopEvent)
│   ├── parser.py              # Raw JSON dict → typed event, duration correlation
│   ├── watcher.py             # Async file watcher: tail JSONL, discover sessions
│   ├── app.py                 # Textual App: layout, message routing
│   ├── install.py             # Writes hook config to ~/.claude/settings.json
│   └── widgets/
│       ├── __init__.py
│       ├── event_stream.py    # Left panel: scrollable event log
│       └── summary.py         # Right panel: counters + token stats
├── hook.py                    # Hook script for settings.json (~40 lines)
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_parser.py
    ├── test_hook.py
    ├── test_watcher.py
    ├── test_install.py
    └── test_app.py
```

---

### Task 1: Project Scaffold + Models

**Files:**
- Create: `pyproject.toml`
- Create: `hud/__init__.py`
- Create: `hud/models.py`
- Create: `tests/__init__.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "claude-hud"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "textual>=0.47.0",
    "watchfiles>=0.21.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[project.scripts]
claude-hud = "hud.__main__:main"
```

- [ ] **Step 2: Create `hud/__init__.py`**

```python
"""Claude HUD — real-time monitoring sidebar for Claude Code."""
```

- [ ] **Step 3: Write failing tests for models**

```python
# tests/test_models.py
from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent


def test_tool_event_creation():
    ev = ToolEvent(
        session_id="abc",
        tool_name="Read",
        input_summary="src/index.ts",
        ts=1000.0,
        phase="pre",
    )
    assert ev.session_id == "abc"
    assert ev.tool_name == "Read"
    assert ev.phase == "pre"
    assert ev.success is None
    assert ev.duration_ms is None
    assert ev.error_excerpt is None
    assert ev.input_tokens is None
    assert ev.output_tokens is None


def test_agent_event_creation():
    ev = AgentEvent(session_id="abc", child_description="code-reviewer", ts=1000.0)
    assert ev.child_description == "code-reviewer"


def test_skill_event_creation():
    ev = SkillEvent(session_id="abc", skill_name="brainstorming", ts=1000.0)
    assert ev.skill_name == "brainstorming"


def test_stop_event_creation():
    ev = StopEvent(session_id="abc", transcript_path="/tmp/t.jsonl", ts=1000.0)
    assert ev.transcript_path == "/tmp/t.jsonl"
```

- [ ] **Step 4: Run tests — expect FAIL**

Run: `python -m pytest tests/test_models.py -v`
Expected: `ModuleNotFoundError: No module named 'hud.models'`

- [ ] **Step 5: Implement `hud/models.py`**

```python
from dataclasses import dataclass, field
from typing import Literal


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


@dataclass
class AgentEvent:
    session_id: str
    child_description: str
    ts: float


@dataclass
class SkillEvent:
    session_id: str
    skill_name: str
    ts: float


@dataclass
class StopEvent:
    session_id: str
    transcript_path: str | None
    ts: float
```

- [ ] **Step 6: Run tests — expect PASS**

Run: `python -m pytest tests/test_models.py -v`
Expected: 4 passed

- [ ] **Step 7: Create `tests/__init__.py` (empty) and commit**

```bash
git add pyproject.toml hud/ tests/
git commit -m "feat: project scaffold and event data models"
```

---

### Task 2: Parser — JSON to Typed Events

**Files:**
- Create: `hud/parser.py`
- Create: `tests/test_parser.py`

- [ ] **Step 1: Write failing tests for parser**

```python
# tests/test_parser.py
from hud.parser import EventParser
from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent


def test_parse_pre_tool_event():
    raw = {
        "tool_name": "Read",
        "tool_input": {"file_path": "src/index.ts"},
        "session_id": "abc",
        "hook_type": "pre",
        "ts": 1000.0,
    }
    parser = EventParser()
    ev = parser.parse(raw)
    assert isinstance(ev, ToolEvent)
    assert ev.phase == "pre"
    assert ev.input_summary == "src/index.ts"
    assert ev.success is None


def test_parse_post_tool_event_with_duration():
    parser = EventParser()
    # Feed a pre event first
    pre = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "session_id": "abc",
        "hook_type": "pre",
        "ts": 1000.0,
    }
    parser.parse(pre)

    post = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "tool_output": {"output": "all tests passed"},
        "usage": {"input_tokens": 100, "output_tokens": 50},
        "session_id": "abc",
        "hook_type": "post",
        "ts": 1002.5,
    }
    ev = parser.parse(post)
    assert isinstance(ev, ToolEvent)
    assert ev.phase == "post"
    assert ev.duration_ms == 2500
    assert ev.success is True
    assert ev.input_tokens == 100
    assert ev.output_tokens == 50


def test_parse_agent_event():
    parser = EventParser()
    raw = {
        "tool_name": "Agent",
        "tool_input": {"description": "Review code quality", "prompt": "..."},
        "session_id": "abc",
        "hook_type": "post",
        "ts": 1000.0,
    }
    ev = parser.parse(raw)
    assert isinstance(ev, AgentEvent)
    assert ev.child_description == "Review code quality"


def test_parse_skill_event():
    parser = EventParser()
    raw = {
        "tool_name": "Skill",
        "tool_input": {"skill": "superpowers:brainstorming"},
        "session_id": "abc",
        "hook_type": "post",
        "ts": 1000.0,
    }
    ev = parser.parse(raw)
    assert isinstance(ev, SkillEvent)
    assert ev.skill_name == "superpowers:brainstorming"


def test_parse_stop_event():
    parser = EventParser()
    raw = {
        "transcript_path": "/tmp/transcript.jsonl",
        "session_id": "abc",
        "hook_type": "stop",
        "ts": 1000.0,
    }
    ev = parser.parse(raw)
    assert isinstance(ev, StopEvent)
    assert ev.transcript_path == "/tmp/transcript.jsonl"


def test_parse_post_without_pre_has_no_duration():
    parser = EventParser()
    post = {
        "tool_name": "Read",
        "tool_input": {"file_path": "a.py"},
        "tool_output": {"output": "..."},
        "session_id": "abc",
        "hook_type": "post",
        "ts": 1000.0,
    }
    ev = parser.parse(post)
    assert isinstance(ev, ToolEvent)
    assert ev.duration_ms is None


def test_input_summary_truncation():
    parser = EventParser()
    long_cmd = "x" * 200
    raw = {
        "tool_name": "Bash",
        "tool_input": {"command": long_cmd},
        "session_id": "abc",
        "hook_type": "pre",
        "ts": 1000.0,
    }
    ev = parser.parse(raw)
    assert len(ev.input_summary) <= 60


def test_token_usage_fallback_field_names():
    parser = EventParser()
    raw = {
        "tool_name": "Read",
        "tool_input": {"file_path": "a.py"},
        "tool_output": {"output": "..."},
        "token_usage": {"prompt_tokens": 200, "completion_tokens": 80},
        "session_id": "abc",
        "hook_type": "post",
        "ts": 1000.0,
    }
    ev = parser.parse(raw)
    assert ev.input_tokens == 200
    assert ev.output_tokens == 80


def test_parse_failed_tool_with_error_excerpt():
    parser = EventParser()
    raw = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "tool_output": {"output": "", "error": "Error: test suite failed with 3 failures in auth module"},
        "session_id": "abc",
        "hook_type": "post",
        "ts": 1000.0,
    }
    ev = parser.parse(raw)
    assert isinstance(ev, ToolEvent)
    assert ev.success is False
    assert ev.error_excerpt is not None
    assert "test suite failed" in ev.error_excerpt
    assert len(ev.error_excerpt) <= 80


def test_parse_tool_with_empty_output_is_success():
    parser = EventParser()
    raw = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "a.py"},
        "tool_output": {},
        "session_id": "abc",
        "hook_type": "post",
        "ts": 1000.0,
    }
    ev = parser.parse(raw)
    assert ev.success is True
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest tests/test_parser.py -v`
Expected: `ModuleNotFoundError: No module named 'hud.parser'`

- [ ] **Step 3: Implement `hud/parser.py`**

```python
from __future__ import annotations

import json
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
        self._pending: dict[tuple[str, str], float] = {}  # (session_id, tool_name) → pre_ts

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

        # Agent and Skill are special tool names on post
        if hook_type == "post" and tool_name == "Agent":
            return AgentEvent(
                session_id=session_id,
                child_description=str(tool_input.get("description", ""))[:60],
                ts=ts,
            )

        if hook_type == "post" and tool_name == "Skill":
            return SkillEvent(
                session_id=session_id,
                skill_name=str(tool_input.get("skill", "")),
                ts=ts,
            )

        # Tool event (pre or post)
        key = (session_id, tool_name)

        if hook_type == "pre":
            self._pending[key] = ts
            return ToolEvent(
                session_id=session_id,
                tool_name=tool_name,
                input_summary=_extract_summary(tool_name, tool_input),
                ts=ts,
                phase="pre",
            )

        # post
        pre_ts = self._pending.pop(key, None)
        duration_ms = int((ts - pre_ts) * 1000) if pre_ts is not None else None
        tool_output = raw.get("tool_output", {})
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
        )
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest tests/test_parser.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add hud/parser.py tests/test_parser.py
git commit -m "feat: event parser with duration correlation and token extraction"
```

---

### Task 3: Hook Script

**Files:**
- Create: `hook.py`
- Create: `tests/test_hook.py`

- [ ] **Step 1: Write failing tests for hook**

```python
# tests/test_hook.py
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from tests._hook_helpers import run_hook


def test_hook_writes_jsonl(tmp_path):
    payload = {"tool_name": "Read", "tool_input": {"file_path": "a.py"}}
    session_id = "test-session-123"

    run_hook(
        hook_type="pre",
        stdin_data=json.dumps(payload),
        session_id=session_id,
        base_dir=str(tmp_path),
    )

    jsonl_path = tmp_path / f"{session_id}.jsonl"
    assert jsonl_path.exists()
    line = json.loads(jsonl_path.read_text().strip())
    assert line["tool_name"] == "Read"
    assert line["session_id"] == session_id
    assert line["hook_type"] == "pre"
    assert "ts" in line


def test_hook_appends_multiple_events(tmp_path):
    session_id = "test-multi"
    for i in range(3):
        run_hook(
            hook_type="post",
            stdin_data=json.dumps({"tool_name": f"Tool{i}", "tool_input": {}}),
            session_id=session_id,
            base_dir=str(tmp_path),
        )

    lines = (tmp_path / f"{session_id}.jsonl").read_text().strip().split("\n")
    assert len(lines) == 3


def test_hook_exits_zero_on_bad_json(tmp_path):
    exit_code = run_hook(
        hook_type="pre",
        stdin_data="not json at all",
        session_id="bad",
        base_dir=str(tmp_path),
    )
    assert exit_code == 0


def test_hook_exits_zero_on_missing_session_id(tmp_path):
    exit_code = run_hook(
        hook_type="pre",
        stdin_data=json.dumps({"tool_name": "X", "tool_input": {}}),
        session_id="",  # empty
        base_dir=str(tmp_path),
    )
    assert exit_code == 0
```

- [ ] **Step 2: Create test helper `tests/_hook_helpers.py`**

```python
# tests/_hook_helpers.py
import subprocess
import sys
import os


def run_hook(
    hook_type: str,
    stdin_data: str,
    session_id: str,
    base_dir: str,
) -> int:
    env = {**os.environ, "CLAUDE_SESSION_ID": session_id, "CLAUDE_HUD_DIR": base_dir}
    result = subprocess.run(
        [sys.executable, "hook.py", hook_type],
        input=stdin_data,
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    return result.returncode
```

- [ ] **Step 3: Run tests — expect FAIL**

Run: `python -m pytest tests/test_hook.py -v`
Expected: FAIL (hook.py doesn't exist)

- [ ] **Step 4: Implement `hook.py`**

```python
#!/usr/bin/env python3
"""Claude Code hook script — appends events to JSONL log.

Usage: python hook.py <pre|post|stop>

Reads JSON from stdin, enriches with session_id/ts/hook_type,
writes one line to /tmp/claude-hud/{session_id}.jsonl.

EXIT CODE IS ALWAYS 0. Never block Claude Code.
"""
import json
import os
import sys
import time


def main() -> None:
    hook_type = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    base_dir = os.environ.get("CLAUDE_HUD_DIR", "/tmp/claude-hud")

    if not session_id:
        return

    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    data["session_id"] = session_id
    data["hook_type"] = hook_type
    data["ts"] = time.time()

    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, f"{session_id}.jsonl")

    with open(path, "a") as f:
        f.write(json.dumps(data, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            base_dir = os.environ.get("CLAUDE_HUD_DIR", "/tmp/claude-hud")
            os.makedirs(base_dir, exist_ok=True)
            with open(os.path.join(base_dir, "hook-errors.log"), "a") as f:
                f.write(f"{time.time()} {exc}\n")
        except Exception:
            pass
    sys.exit(0)
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `python -m pytest tests/test_hook.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add hook.py tests/test_hook.py tests/_hook_helpers.py
git commit -m "feat: hook script for Claude Code settings.json integration"
```

---

### Task 4: File Watcher

**Files:**
- Create: `hud/watcher.py`
- Create: `tests/test_watcher.py`

- [ ] **Step 1: Write failing tests for watcher**

```python
# tests/test_watcher.py
import asyncio
import json
from pathlib import Path

import pytest

from hud.watcher import SessionWatcher


@pytest.mark.asyncio
async def test_watcher_reads_existing_lines(tmp_path):
    session_id = "sess1"
    jsonl = tmp_path / f"{session_id}.jsonl"
    event = {"tool_name": "Read", "tool_input": {}, "session_id": session_id, "hook_type": "pre", "ts": 1.0}
    jsonl.write_text(json.dumps(event) + "\n")

    watcher = SessionWatcher(str(tmp_path))
    events = []

    async def collect():
        async for raw in watcher.tail(session_id):
            events.append(raw)
            if len(events) >= 1:
                break

    await asyncio.wait_for(collect(), timeout=2.0)
    assert len(events) == 1
    assert events[0]["tool_name"] == "Read"


@pytest.mark.asyncio
async def test_watcher_detects_new_lines(tmp_path):
    session_id = "sess2"
    jsonl = tmp_path / f"{session_id}.jsonl"
    jsonl.touch()

    watcher = SessionWatcher(str(tmp_path))
    events = []

    async def collect():
        async for raw in watcher.tail(session_id):
            events.append(raw)
            if len(events) >= 1:
                break

    async def write_after_delay():
        await asyncio.sleep(0.2)
        event = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "session_id": session_id, "hook_type": "post", "ts": 2.0}
        with open(jsonl, "a") as f:
            f.write(json.dumps(event) + "\n")

    await asyncio.gather(
        asyncio.wait_for(collect(), timeout=3.0),
        write_after_delay(),
    )
    assert events[0]["tool_name"] == "Bash"


@pytest.mark.asyncio
async def test_watcher_discover_latest_session(tmp_path):
    (tmp_path / "old.jsonl").write_text('{"ts":1}\n')
    import time; time.sleep(0.01)
    (tmp_path / "new.jsonl").write_text('{"ts":2}\n')

    watcher = SessionWatcher(str(tmp_path))
    latest = watcher.discover_latest_session()
    assert latest == "new"
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest tests/test_watcher.py -v`
Expected: `ModuleNotFoundError: No module named 'hud.watcher'`

- [ ] **Step 3: Implement `hud/watcher.py`**

```python
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import AsyncIterator


class SessionWatcher:
    def __init__(self, base_dir: str = "/tmp/claude-hud") -> None:
        self._base_dir = Path(base_dir)

    def discover_latest_session(self) -> str | None:
        files = sorted(self._base_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime)
        if not files:
            return None
        return files[-1].stem

    async def tail(self, session_id: str) -> AsyncIterator[dict]:
        path = self._base_dir / f"{session_id}.jsonl"
        offset = 0

        # Read existing content first
        if path.exists():
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue
                offset = path.stat().st_size

        # Poll for new lines
        while True:
            await asyncio.sleep(0.05)  # 50ms polling
            if not path.exists():
                continue
            size = path.stat().st_size
            if size <= offset:
                continue
            with open(path) as f:
                f.seek(offset)
                new_data = f.read()
                offset = f.tell()
            for line in new_data.strip().split("\n"):
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

    async def watch_for_sessions(self) -> AsyncIterator[str]:
        """Yield session IDs as new JSONL files appear."""
        seen: set[str] = set()
        while True:
            if self._base_dir.exists():
                for f in self._base_dir.glob("*.jsonl"):
                    sid = f.stem
                    if sid not in seen:
                        seen.add(sid)
                        yield sid
            await asyncio.sleep(0.2)
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest tests/test_watcher.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add hud/watcher.py tests/test_watcher.py
git commit -m "feat: session watcher with file tail and session discovery"
```

---

### Task 5: Textual Widgets

**Files:**
- Create: `hud/widgets/__init__.py`
- Create: `hud/widgets/event_stream.py`
- Create: `hud/widgets/summary.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: Create `hud/widgets/__init__.py`**

```python
from hud.widgets.event_stream import EventStreamWidget
from hud.widgets.summary import SummaryWidget
```

- [ ] **Step 2: Implement `hud/widgets/event_stream.py`**

```python
from __future__ import annotations

from textual.widgets import RichLog
from textual.message import Message

from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent

_STYLE = {
    "ok": "[green][OK][/green]",
    "err": "[red][ERR][/red]",
    "pending": "[yellow][...][/yellow]",
    "skill": "[purple][SKILL][/purple]",
    "agent": "[blue][AGENT][/blue]",
    "stop": "[dim][STOP][/dim]",
}


class EventStreamWidget(RichLog):

    class NewEvent(Message):
        def __init__(self, event: ToolEvent | AgentEvent | SkillEvent | StopEvent) -> None:
            super().__init__()
            self.event = event

    def on_mount(self) -> None:
        self.border_title = "EVENT STREAM"

    def add_event(self, event: ToolEvent | AgentEvent | SkillEvent | StopEvent) -> None:
        from datetime import datetime
        ts_str = datetime.fromtimestamp(event.ts).strftime("%H:%M")

        if isinstance(event, SkillEvent):
            self.write(f"{ts_str} {_STYLE['skill']} {event.skill_name}")
        elif isinstance(event, AgentEvent):
            self.write(f"{ts_str} {_STYLE['agent']} {event.child_description}")
        elif isinstance(event, StopEvent):
            self.write(f"{ts_str} {_STYLE['stop']} session ended")
        elif isinstance(event, ToolEvent):
            if event.phase == "pre":
                self.write(f"{ts_str} {_STYLE['pending']} {event.tool_name}  {event.input_summary}")
            elif event.success is False:
                self.write(f"{ts_str} {_STYLE['err']} {event.tool_name}  {event.input_summary}")
                if event.error_excerpt:
                    self.write(f"       {event.error_excerpt}")
            else:
                dur = f" {event.duration_ms}ms" if event.duration_ms is not None else ""
                self.write(f"{ts_str} {_STYLE['ok']} {event.tool_name}  {event.input_summary}{dur}")

    def clear_with_separator(self, session_id: str) -> None:
        self.clear()
        self.write(f"[dim]--- new session: {session_id} ---[/dim]")
```

- [ ] **Step 3: Implement `hud/widgets/summary.py`**

```python
from __future__ import annotations

from textual.widgets import Static

from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent


class SummaryWidget(Static):
    def __init__(self) -> None:
        super().__init__()
        self._tools = 0
        self._agents = 0
        self._skills = 0
        self._errors = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._session_id = ""

    def on_mount(self) -> None:
        self.border_title = "SUMMARY"
        self._render()

    def reset(self, session_id: str) -> None:
        self._tools = 0
        self._agents = 0
        self._skills = 0
        self._errors = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._session_id = session_id
        self._render()

    def update_event(self, event: ToolEvent | AgentEvent | SkillEvent | StopEvent) -> None:
        if isinstance(event, ToolEvent) and event.phase == "post":
            self._tools += 1
            if event.success is False:
                self._errors += 1
            if event.input_tokens:
                self._input_tokens += event.input_tokens
            if event.output_tokens:
                self._output_tokens += event.output_tokens
        elif isinstance(event, AgentEvent):
            self._agents += 1
        elif isinstance(event, SkillEvent):
            self._skills += 1
        self._render()

    def _render(self) -> None:
        sid = self._session_id[:8] if self._session_id else "--"
        tok_in = f"{self._input_tokens:,}" if self._input_tokens else "--"
        tok_out = f"{self._output_tokens:,}" if self._output_tokens else "--"
        self.update(
            f"[dim]{sid}[/dim]\n\n"
            f"skills:  {self._skills}\n"
            f"agents:  {self._agents}\n"
            f"tools:   {self._tools}\n"
            f"[red]errors:  {self._errors}[/red]\n\n"
            f"[dim]in:[/dim]  {tok_in}\n"
            f"[dim]out:[/dim] {tok_out}"
        )
```

- [ ] **Step 4: Write tests for widgets (before implementation — TDD)**

```python
# tests/test_app.py
from unittest.mock import patch
from hud.models import ToolEvent, SkillEvent, AgentEvent, StopEvent
from hud.widgets.summary import SummaryWidget


def test_summary_counts():
    s = SummaryWidget()
    s._session_id = "abc"
    with patch.object(s, "_render"):  # avoid calling self.update() without mount
        s.update_event(ToolEvent(
            session_id="abc", tool_name="Read", input_summary="x",
            ts=1.0, phase="post", success=True,
        ))
        s.update_event(ToolEvent(
            session_id="abc", tool_name="Bash", input_summary="y",
            ts=2.0, phase="post", success=False,
        ))
        s.update_event(SkillEvent(session_id="abc", skill_name="tdd", ts=3.0))
        s.update_event(AgentEvent(session_id="abc", child_description="rev", ts=4.0))
    assert s._tools == 2
    assert s._errors == 1
    assert s._skills == 1
    assert s._agents == 1


def test_summary_reset():
    s = SummaryWidget()
    s._tools = 5
    with patch.object(s, "_render"):
        s.reset("new-session")
    assert s._tools == 0
    assert s._session_id == "new-session"


def test_summary_token_accumulation():
    s = SummaryWidget()
    with patch.object(s, "_render"):
        s.update_event(ToolEvent(
            session_id="abc", tool_name="Read", input_summary="x",
            ts=1.0, phase="post", success=True, input_tokens=100, output_tokens=50,
        ))
        s.update_event(ToolEvent(
            session_id="abc", tool_name="Bash", input_summary="y",
            ts=2.0, phase="post", success=True, input_tokens=200, output_tokens=80,
        ))
    assert s._input_tokens == 300
    assert s._output_tokens == 130
```

- [ ] **Step 5: Run tests — expect FAIL**

Run: `python -m pytest tests/test_app.py -v`
Expected: `ModuleNotFoundError` (widgets not yet created)

- [ ] **Step 6: Implement widgets** (event_stream.py and summary.py as shown above)

- [ ] **Step 7: Run tests — expect PASS**

Run: `python -m pytest tests/test_app.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add hud/widgets/ tests/test_app.py
git commit -m "feat: event stream and summary widgets"
```

---

### Task 6: Textual App — Layout and Event Routing

**Files:**
- Create: `hud/app.py`
- Create: `hud/__main__.py`

- [ ] **Step 1: Implement `hud/app.py`**

```python
from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches

from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent
from hud.parser import EventParser
from hud.watcher import SessionWatcher
from hud.widgets.event_stream import EventStreamWidget
from hud.widgets.summary import SummaryWidget

CSS = """
Horizontal {
    height: 100%;
}
EventStreamWidget {
    width: 3fr;
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
            yield EventStreamWidget(id="stream")
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
            stream = self.query_one("#stream", EventStreamWidget)
            stream.clear_with_separator(session_id)
            summary = self.query_one(SummaryWidget)
            summary.reset(session_id)
        except NoMatches:
            pass

    def _handle_raw(self, raw: dict) -> None:
        event = self._parser.parse(raw)
        try:
            stream = self.query_one("#stream", EventStreamWidget)
            stream.add_event(event)
            summary = self.query_one(SummaryWidget)
            summary.update_event(event)
        except NoMatches:
            pass
```

- [ ] **Step 2: Implement `hud/__main__.py`**

```python
"""CLI entry point: python -m hud <command>"""
import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m hud <watch|install>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "watch":
        from hud.app import HudApp
        base_dir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/claude-hud"
        app = HudApp(base_dir=base_dir)
        app.run()

    elif command == "install":
        from hud.install import install_hooks
        install_hooks()

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Manual smoke test**

Run: `python -m hud watch /tmp/claude-hud-test`
Expected: TUI launches, shows empty "EVENT STREAM" and "SUMMARY" panels. Press `q` to quit.

- [ ] **Step 4: Commit**

```bash
git add hud/app.py hud/__main__.py
git commit -m "feat: textual app with layout and event routing"
```

---

### Task 7: Install Script

**Files:**
- Create: `hud/install.py`
- Create: `tests/test_install.py`

- [ ] **Step 1: Write failing tests for install**

```python
# tests/test_install.py
import json
from pathlib import Path

from hud.install import install_hooks


def test_install_creates_hooks_in_empty_settings(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")

    install_hooks(settings_path=str(settings_path), hook_script_path="/usr/local/bin/hook.py")

    data = json.loads(settings_path.read_text())
    assert "hooks" in data
    assert "PreToolUse" in data["hooks"]
    assert "PostToolUse" in data["hooks"]
    assert "Stop" in data["hooks"]
    # Verify matcher
    assert data["hooks"]["PreToolUse"][0]["matcher"] == "*"
    # Verify async on post
    assert data["hooks"]["PostToolUse"][0]["hooks"][0].get("async") is True


def test_install_is_idempotent(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")

    install_hooks(settings_path=str(settings_path), hook_script_path="/x/hook.py")
    install_hooks(settings_path=str(settings_path), hook_script_path="/x/hook.py")

    data = json.loads(settings_path.read_text())
    # Should not duplicate
    assert len(data["hooks"]["PreToolUse"]) == 1


def test_install_preserves_existing_hooks(tmp_path):
    settings_path = tmp_path / "settings.json"
    existing = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}
            ]
        }
    }
    settings_path.write_text(json.dumps(existing))

    install_hooks(settings_path=str(settings_path), hook_script_path="/x/hook.py")

    data = json.loads(settings_path.read_text())
    # Should have both: original + ours
    assert len(data["hooks"]["PreToolUse"]) == 2
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest tests/test_install.py -v`
Expected: `ModuleNotFoundError: No module named 'install'`

- [ ] **Step 3: Implement `hud/install.py`**

```python
"""Install Claude HUD hooks into ~/.claude/settings.json."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_DEFAULT_SETTINGS = os.path.expanduser("~/.claude/settings.json")


def _make_hook_entry(hook_script_path: str, hook_type: str, async_: bool = False) -> dict:
    entry: dict = {
        "type": "command",
        "command": f"{sys.executable} {hook_script_path} {hook_type}",
    }
    if async_:
        entry["async"] = True
    return entry


def _hook_already_present(entries: list, hook_script_path: str) -> bool:
    for entry in entries:
        for h in entry.get("hooks", []):
            if hook_script_path in h.get("command", ""):
                return True
    return False


def install_hooks(
    settings_path: str = _DEFAULT_SETTINGS,
    hook_script_path: str | None = None,
) -> None:
    if hook_script_path is None:
        hook_script_path = str(Path(__file__).parent / "hook.py")

    path = Path(settings_path)
    if path.exists():
        data = json.loads(path.read_text())
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}

    hooks = data.setdefault("hooks", {})

    hook_configs = [
        ("PreToolUse", "pre", False, "*"),
        ("PostToolUse", "post", True, "*"),
        ("Stop", "stop", True, None),
    ]

    for event_name, type_arg, async_, matcher in hook_configs:
        entries = hooks.setdefault(event_name, [])
        if _hook_already_present(entries, hook_script_path):
            continue
        new_entry: dict = {"hooks": [_make_hook_entry(hook_script_path, type_arg, async_)]}
        if matcher:
            new_entry["matcher"] = matcher
        entries.append(new_entry)

    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Hooks installed to {settings_path}")


if __name__ == "__main__":
    install_hooks()
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest tests/test_install.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add hud/install.py tests/test_install.py
git commit -m "feat: install script for settings.json hook registration"
```

---

### Task 8: Integration Test — End-to-End

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
"""End-to-end: hook.py writes → parser reads → correct events."""
import json
from pathlib import Path

from tests._hook_helpers import run_hook
from hud.parser import EventParser


def test_hook_to_parser_roundtrip(tmp_path):
    session_id = "integration-test"

    # Simulate PreToolUse
    run_hook("pre", json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
    }), session_id, str(tmp_path))

    # Simulate PostToolUse
    run_hook("post", json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "tool_output": {"output": "OK"},
        "usage": {"input_tokens": 500, "output_tokens": 100},
    }), session_id, str(tmp_path))

    # Simulate Skill
    run_hook("post", json.dumps({
        "tool_name": "Skill",
        "tool_input": {"skill": "brainstorming"},
    }), session_id, str(tmp_path))

    # Simulate Stop
    run_hook("stop", json.dumps({
        "transcript_path": "/tmp/t.jsonl",
    }), session_id, str(tmp_path))

    # Parse all events
    jsonl = tmp_path / f"{session_id}.jsonl"
    lines = [json.loads(l) for l in jsonl.read_text().strip().split("\n")]
    assert len(lines) == 4

    parser = EventParser()
    events = [parser.parse(line) for line in lines]

    from hud.models import ToolEvent, SkillEvent, StopEvent
    assert isinstance(events[0], ToolEvent)
    assert events[0].phase == "pre"
    assert isinstance(events[1], ToolEvent)
    assert events[1].phase == "post"
    assert events[1].duration_ms is not None
    assert events[1].input_tokens == 500
    assert isinstance(events[2], SkillEvent)
    assert events[2].skill_name == "brainstorming"
    assert isinstance(events[3], StopEvent)
```

- [ ] **Step 2: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All passed (models + parser + hook + watcher + app + install + integration)

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end integration test hook → parser"
```

---

### Task 9: pip install + Final Verification

- [ ] **Step 1: Install in dev mode**

Run: `pip install -e ".[dev]"`
Expected: Successfully installed

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 3: Verify CLI entry point**

Run: `claude-hud watch /tmp/claude-hud-verify`
Expected: TUI launches. Press `q` to quit.

- [ ] **Step 4: Install hooks**

Run: `python -m hud install`
Expected: Prints "Hooks installed to ~/.claude/settings.json"

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: finalize v0.1.0 setup"
```
