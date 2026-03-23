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
