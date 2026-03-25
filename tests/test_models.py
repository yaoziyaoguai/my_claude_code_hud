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


def test_tool_event_has_depth_and_context_label():
    ev = ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                   ts=1.0, phase="pre")
    assert ev.depth == 0
    assert ev.context_label is None


def test_agent_event_has_depth():
    ev = AgentEvent(session_id="s", child_description="rev", ts=1.0)
    assert ev.depth == 0


def test_skill_event_has_depth():
    ev = SkillEvent(session_id="s", skill_name="tdd", ts=1.0)
    assert ev.depth == 0
