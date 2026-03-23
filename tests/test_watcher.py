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
