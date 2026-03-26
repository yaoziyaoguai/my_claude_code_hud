import time
from unittest.mock import patch
from hud.widgets.active import ActiveWidget
from hud.models import ToolEvent
from rich.text import Text


def _pre_event(tool_name, summary="x", session_id="s", ts=None):
    return ToolEvent(
        session_id=session_id, tool_name=tool_name, input_summary=summary,
        ts=ts or time.time(), phase="pre",
    )


def _post_event(tool_name, session_id="s"):
    return ToolEvent(
        session_id=session_id, tool_name=tool_name, input_summary="x",
        ts=time.time(), phase="post", success=True,
    )


def test_add_pending_stores_entry():
    w = ActiveWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", "src/foo.py", ts=1000.0))
    assert len(w._pending) == 1


def test_remove_pending_fifo():
    w = ActiveWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", "a.py", ts=1000.0))
        w.add_pending(_pre_event("Read", "b.py", ts=1001.0))
        w.remove_pending(_post_event("Read"))
    # oldest (ts=1000.0) removed first
    assert len(w._pending) == 1
    remaining_key = list(w._pending.keys())[0]
    assert remaining_key[2] == 1001.0  # pre_ts of b.py


def test_remove_pending_no_match_is_noop():
    w = ActiveWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", ts=1000.0))
        w.remove_pending(_post_event("Bash"))  # different tool — no match
    assert len(w._pending) == 1


def test_reset_clears_pending():
    w = ActiveWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", ts=1000.0))
        w.reset()
    assert len(w._pending) == 0


def test_overflow_indicator_shown_when_more_than_four():
    w = ActiveWidget()
    with patch.object(w, "refresh"):
        for i in range(6):
            w.add_pending(_pre_event("Read", f"file{i}.py", ts=float(1000 + i)))
    from rich.text import Text
    rendered = w.render()
    assert isinstance(rendered, Text)
    plain = rendered.plain
    assert "+2 more" in plain


def test_render_shows_tool_name_and_summary():
    w = ActiveWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", "src/main.py", ts=time.time() - 0.5))
    from rich.text import Text
    rendered = w.render()
    assert isinstance(rendered, Text)
    plain = rendered.plain
    assert "Read" in plain
    assert "src/main.py" in plain


def test_render_escapes_tool_name_and_summary():
    """Regression test for markup in tool_name or input_summary."""
    w = ActiveWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read[/cyan]", "src[cyan]file[/cyan].py", ts=time.time() - 0.5))
    rendered = w.render()
    assert isinstance(rendered, Text)
    # Verify markup is valid by checking it can be rendered
    # (if markup was invalid, rendering would fail)
    assert "Read" in rendered.plain or "file" in rendered.plain
