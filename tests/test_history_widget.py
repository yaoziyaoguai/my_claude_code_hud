from collections import deque
from unittest.mock import patch, MagicMock
from hud.widgets.history import HistoryWidget
from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent


def _post_ok(tool_name="Read", summary="src/foo.py", depth=0, duration_ms=88):
    return ToolEvent(session_id="s", tool_name=tool_name, input_summary=summary,
                     ts=1.0, phase="post", success=True, duration_ms=duration_ms,
                     depth=depth)


def _post_err(tool_name="Bash", summary="npm test", depth=0, error="exit 1"):
    return ToolEvent(session_id="s", tool_name=tool_name, input_summary=summary,
                     ts=1.0, phase="post", success=False, error_excerpt=error,
                     depth=depth)


def test_add_event_newest_on_top():
    w = HistoryWidget()
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(_post_ok("Read", "a.py"))
        w.add_event(_post_ok("Bash", "ls"))
    # newest (Bash) is at index 0
    assert "Bash" in w._lines[0]
    assert "Read" in w._lines[1]


def test_pre_phase_event_is_ignored():
    w = HistoryWidget()
    pre = ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                    ts=1.0, phase="pre")
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(pre)
    assert len(w._lines) == 0


def test_reset_clears_and_adds_separator():
    w = HistoryWidget()
    w._lines.appendleft("old line")
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.reset("abc123")
    assert len(w._lines) == 1
    assert "abc123" in w._lines[0]


def test_indentation_for_depth_one():
    w = HistoryWidget()
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(_post_ok("Read", "foo.py", depth=1))
    assert w._lines[0].startswith("  ")  # 2-space indent


def test_no_indentation_for_depth_zero():
    w = HistoryWidget()
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(_post_ok("Read", "foo.py", depth=0))
    assert not w._lines[0].startswith(" ")


def test_error_excerpt_indented():
    w = HistoryWidget()
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(_post_err("Bash", "npm test", depth=0, error="exit 1"))
    # Should have 2 lines: event line + error excerpt
    assert len(w._lines) == 2
    assert w._lines[0].startswith("       ")  # 7 spaces for error excerpt (newest first)


def test_maxlen_500():
    w = HistoryWidget()
    with patch.object(w, "query_one", return_value=MagicMock()):
        for i in range(600):
            w.add_event(_post_ok("Read", f"file{i}.py"))
    assert len(w._lines) == 500


def test_agent_event_displayed():
    w = HistoryWidget()
    ev = AgentEvent(session_id="s", child_description="code-reviewer", ts=1.0, depth=0)
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(ev)
    assert "AGENT" in w._lines[0]
    assert "code-reviewer" in w._lines[0]


def test_skill_event_displayed():
    w = HistoryWidget()
    ev = SkillEvent(session_id="s", skill_name="tdd", ts=1.0, depth=0)
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(ev)
    assert "SKILL" in w._lines[0]
    assert "tdd" in w._lines[0]
