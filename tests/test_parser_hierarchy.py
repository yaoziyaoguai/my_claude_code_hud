from hud.parser import EventParser
from hud.models import ToolEvent, AgentEvent, SkillEvent
from hud.colors import SPAN_COLORS


def _pre(tool_name, tool_input=None, session_id="s", ts=1.0):
    return {"tool_name": tool_name, "tool_input": tool_input or {},
            "session_id": session_id, "hook_type": "pre", "ts": ts}


def _post(tool_name, tool_input=None, session_id="s", ts=2.0):
    return {"tool_name": tool_name, "tool_input": tool_input or {},
            "tool_output": {}, "session_id": session_id, "hook_type": "post", "ts": ts}


def test_top_level_tool_has_depth_zero():
    p = EventParser()
    ev = p.parse(_pre("Read", {"file_path": "a.py"}))
    assert isinstance(ev, ToolEvent)
    assert ev.depth == 0
    assert ev.context_label is None


def test_tool_inside_agent_has_depth_one():
    p = EventParser()
    p.parse(_pre("Agent", {"description": "code-reviewer"}, ts=1.0))
    ev = p.parse(_pre("Read", {"file_path": "a.py"}, ts=1.1))
    assert isinstance(ev, ToolEvent)
    assert ev.depth == 1
    assert ev.context_label == "agent:code-reviewer"


def test_depth_returns_to_zero_after_agent_post():
    p = EventParser()
    p.parse(_pre("Agent", {"description": "reviewer"}, ts=1.0))
    p.parse(_pre("Read", {"file_path": "a.py"}, ts=1.1))
    p.parse(_post("Read", {"file_path": "a.py"}, ts=1.2))
    p.parse(_post("Agent", {"description": "reviewer"}, ts=2.0))
    ev = p.parse(_pre("Bash", {"command": "ls"}, ts=2.1))
    assert ev.depth == 0
    assert ev.context_label is None


def test_nested_agent_has_depth_two():
    p = EventParser()
    p.parse(_pre("Agent", {"description": "outer"}, ts=1.0))
    p.parse(_pre("Agent", {"description": "inner"}, ts=1.1))
    ev = p.parse(_pre("Read", {"file_path": "x.py"}, ts=1.2))
    assert ev.depth == 2
    assert ev.context_label == "agent:inner"


def test_skill_increments_depth():
    p = EventParser()
    p.parse(_pre("Skill", {"skill": "tdd"}, ts=1.0))
    ev = p.parse(_pre("Read", {"file_path": "a.py"}, ts=1.1))
    assert ev.depth == 1
    assert ev.context_label == "skill:tdd"


def test_agent_event_itself_has_depth_at_time_of_firing():
    p = EventParser()
    ev = p.parse(_pre("Agent", {"description": "reviewer"}, ts=1.0))
    assert isinstance(ev, AgentEvent)
    assert ev.depth == 0


def test_stack_resets_on_new_parser_instance():
    p = EventParser()
    p.parse(_pre("Agent", {"description": "x"}, ts=1.0))
    p2 = EventParser()
    ev = p2.parse(_pre("Read", {"file_path": "a.py"}, ts=1.0))
    assert ev.depth == 0


def test_top_level_agent_gets_first_color():
    p = EventParser()
    pre = p.parse({"hook_type": "pre", "tool_name": "Agent", "session_id": "s", "ts": 1.0,
                   "tool_input": {"description": "A", "subagent_type": "g", "prompt": "x"}})
    assert pre.span_id == 1
    assert pre.span_color == SPAN_COLORS[0]


def test_child_agent_inherits_parent_color():
    """Child agent MUST share parent's root color, not take the next palette color."""
    p = EventParser()
    p.parse({"hook_type": "pre", "tool_name": "Agent", "session_id": "s", "ts": 1.0,
             "tool_input": {"description": "A", "subagent_type": "g", "prompt": "x"}})
    child = p.parse({"hook_type": "pre", "tool_name": "Agent", "session_id": "s", "ts": 2.0,
                     "tool_input": {"description": "B", "subagent_type": "g", "prompt": "x"}})
    assert child.span_color == SPAN_COLORS[0]   # same as parent
    assert child.span_id == 2                    # different span_id


def test_tool_inside_agent_inherits_span():
    p = EventParser()
    p.parse({"hook_type": "pre", "tool_name": "Agent", "session_id": "s", "ts": 1.0,
             "tool_input": {"description": "A", "subagent_type": "g", "prompt": "x"}})
    tool = p.parse({"hook_type": "post", "tool_name": "Bash", "session_id": "s", "ts": 2.0,
                    "tool_input": {"command": "ls"}})
    assert tool.span_id == 1
    assert tool.span_color == SPAN_COLORS[0]


def test_tool_outside_agent_has_no_span():
    p = EventParser()
    tool = p.parse({"hook_type": "post", "tool_name": "Bash", "session_id": "s", "ts": 1.0,
                    "tool_input": {"command": "ls"}})
    assert tool.span_id is None
    assert tool.span_color is None


def test_parent_span_restored_after_child_ends():
    """After child agent ends, parent span (same color, parent id) is active."""
    p = EventParser()
    p.parse({"hook_type": "pre", "tool_name": "Agent", "session_id": "s", "ts": 1.0,
             "tool_input": {"description": "A", "subagent_type": "g", "prompt": "x"}})
    p.parse({"hook_type": "pre", "tool_name": "Agent", "session_id": "s", "ts": 2.0,
             "tool_input": {"description": "B", "subagent_type": "g", "prompt": "x"}})
    p.parse({"hook_type": "post", "tool_name": "Agent", "session_id": "s", "ts": 3.0,
             "tool_input": {"description": "B", "subagent_type": "g", "prompt": "x"}})
    tool = p.parse({"hook_type": "post", "tool_name": "Bash", "session_id": "s", "ts": 4.0,
                    "tool_input": {"command": "ls"}})
    assert tool.span_id == 1              # back to outer span
    assert tool.span_color == SPAN_COLORS[0]


def test_second_top_level_agent_gets_different_color():
    """Sequential top-level agents use different palette colors."""
    p = EventParser()
    p.parse({"hook_type": "pre", "tool_name": "Agent", "session_id": "s", "ts": 1.0,
             "tool_input": {"description": "A", "subagent_type": "g", "prompt": "x"}})
    p.parse({"hook_type": "post", "tool_name": "Agent", "session_id": "s", "ts": 2.0,
             "tool_input": {"description": "A", "subagent_type": "g", "prompt": "x"}})
    pre2 = p.parse({"hook_type": "pre", "tool_name": "Agent", "session_id": "s", "ts": 3.0,
                    "tool_input": {"description": "C", "subagent_type": "g", "prompt": "x"}})
    assert pre2.span_color == SPAN_COLORS[1]  # second top-level gets next color
