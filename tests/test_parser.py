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
