import json
import os
from pathlib import Path

from tests._hook_helpers import run_hook


def test_hook_writes_jsonl(tmp_path):
    payload = {"tool_name": "Read", "tool_input": {"file_path": "a.py"}}
    session_id = "test-session-123"
    run_hook(hook_type="pre", stdin_data=json.dumps(payload), session_id=session_id, base_dir=str(tmp_path))
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
        run_hook(hook_type="post", stdin_data=json.dumps({"tool_name": f"Tool{i}", "tool_input": {}}), session_id=session_id, base_dir=str(tmp_path))
    lines = (tmp_path / f"{session_id}.jsonl").read_text().strip().split("\n")
    assert len(lines) == 3


def test_hook_exits_zero_on_bad_json(tmp_path):
    exit_code = run_hook(hook_type="pre", stdin_data="not json at all", session_id="bad", base_dir=str(tmp_path))
    assert exit_code == 0


def test_hook_exits_zero_on_missing_session_id(tmp_path):
    exit_code = run_hook(hook_type="pre", stdin_data=json.dumps({"tool_name": "X", "tool_input": {}}), session_id="", base_dir=str(tmp_path))
    assert exit_code == 0
