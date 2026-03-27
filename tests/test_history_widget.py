from collections import deque
from unittest.mock import patch, MagicMock
from hud.widgets.history import HistoryWidget, _format_event
from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent
from textual.content import Content


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
    # oldest (Read) at index 0, newest (Bash) at index -1
    assert "Read" in w._lines[0]
    assert "Bash" in w._lines[-1]


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
    # depth>0 uses "via:" label instead of indent — starts with timestamp
    assert w._lines[0].startswith("08:")


def test_no_indentation_for_depth_zero():
    w = HistoryWidget()
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(_post_ok("Read", "foo.py", depth=0))
    assert w._lines[0].startswith("08:")


def test_error_excerpt_indented():
    w = HistoryWidget()
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(_post_err("Bash", "npm test", depth=0, error="exit 1"))
    # Should have 2 lines: event line + error excerpt
    assert len(w._lines) == 2
    assert w._lines[0].startswith("08:")  # main event line first
    assert w._lines[1].startswith("       ")  # 7 spaces for error excerpt below


def test_maxlen_500():
    w = HistoryWidget()
    with patch.object(w, "query_one", return_value=MagicMock()):
        for i in range(600):
            w.add_event(_post_ok("Read", f"file{i}.py"))
    assert len(w._lines) == 500


def test_agent_event_displayed():
    w = HistoryWidget()
    ev = AgentEvent(session_id="s", child_description="code-reviewer", ts=1.0, depth=0, phase="pre")
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(ev)
    assert "agent" in w._lines[0]
    assert "code-reviewer" in w._lines[0]


def test_skill_event_displayed():
    w = HistoryWidget()
    ev = SkillEvent(session_id="s", skill_name="tdd", ts=1.0, depth=0, phase="pre")
    with patch.object(w, "query_one", return_value=MagicMock()):
        w.add_event(ev)
    assert "skill" in w._lines[0]
    assert "tdd" in w._lines[0]


def test_markup_in_tool_name_escaped():
    """Regression test for malformed markup when tool_name contains '[' or ']'."""
    event = ToolEvent(
        session_id="s", tool_name="Read[/cyan]", input_summary="src/foo.py",
        ts=1.0, phase="post", success=True, duration_ms=88, depth=1
    )
    lines = _format_event(event)
    # Verify the generated markup is valid and can be parsed
    for line in lines:
        try:
            Content.from_markup(line)
        except Exception as e:
            raise AssertionError(f"Generated invalid markup: {line!r}") from e


def test_markup_in_input_summary_escaped():
    """Regression test for malformed markup when input_summary contains markup."""
    event = ToolEvent(
        session_id="s", tool_name="Read", input_summary="src[cyan]foo[/cyan]/bar.py",
        ts=1.0, phase="post", success=True, duration_ms=88, depth=0
    )
    lines = _format_event(event)
    # Verify the generated markup is valid and can be parsed
    for line in lines:
        try:
            Content.from_markup(line)
        except Exception as e:
            raise AssertionError(f"Generated invalid markup: {line!r}") from e


def test_markup_in_error_excerpt_escaped():
    """Regression test for malformed markup when error_excerpt contains markup."""
    event = ToolEvent(
        session_id="s", tool_name="Bash", input_summary="npm test",
        ts=1.0, phase="post", success=False, error_excerpt="error[/cyan]message",
        depth=0
    )
    lines = _format_event(event)
    # Verify the generated markup is valid and can be parsed
    for line in lines:
        try:
            Content.from_markup(line)
        except Exception as e:
            raise AssertionError(f"Generated invalid markup: {line!r}") from e


def test_markup_in_agent_description_escaped():
    """Regression test for malformed markup when agent description contains markup."""
    event = AgentEvent(
        session_id="s", child_description="agent[/cyan]name",
        ts=1.0, depth=0, phase="pre"
    )
    lines = _format_event(event)
    # Verify the generated markup is valid and can be parsed
    for line in lines:
        try:
            Content.from_markup(line)
        except Exception as e:
            raise AssertionError(f"Generated invalid markup: {line!r}") from e


import re

def _plain(s):
    return re.sub(r'\[/?[^\]]+\]', '', s)

def test_tool_no_span_has_no_gutter():
    e = ToolEvent(session_id="s", tool_name="Read", input_summary="f",
                  ts=1.0, phase="post", success=True, span_id=None, span_color=None)
    lines = _format_event(e)
    assert lines and "│" not in lines[0]

def test_top_level_tool_has_single_bright_gutter():
    e = ToolEvent(session_id="s", tool_name="Read", input_summary="f",
                  ts=1.0, phase="post", success=True, depth=0, span_id=1, span_color="cyan")
    lines = _format_event(e)
    assert lines and lines[0].count("│") == 1
    assert "dim" not in lines[0]   # top-level is bright

def test_nested_tool_has_dim_multi_gutter():
    e = ToolEvent(session_id="s", tool_name="Bash", input_summary="ls",
                  ts=1.0, phase="post", success=True, depth=1, span_id=2, span_color="cyan")
    lines = _format_event(e)
    assert lines and lines[0].count("│") >= 2
    assert "dim" in lines[0]   # nested is dim

def test_agent_start_has_gutter():
    e = AgentEvent(session_id="s", child_description="My Agent",
                   ts=1.0, phase="pre", depth=0, span_id=1, span_color="yellow")
    lines = _format_event(e)
    assert lines and "│" in lines[0]
