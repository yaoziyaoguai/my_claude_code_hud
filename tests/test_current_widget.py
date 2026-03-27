import os
import time
from unittest.mock import patch, MagicMock
from hud.widgets.current import CurrentWidget
from hud.models import ToolEvent
from rich.text import Text


def _pre_event(tool_name, summary="x", session_id="s", ts=None):
    """Helper to create a pre-phase ToolEvent."""
    return ToolEvent(
        session_id=session_id, tool_name=tool_name, input_summary=summary,
        ts=ts or time.time(), phase="pre",
    )


def _post_event(tool_name, session_id="s"):
    """Helper to create a post-phase ToolEvent."""
    return ToolEvent(
        session_id=session_id, tool_name=tool_name, input_summary="x",
        ts=time.time(), phase="post", success=True,
    )


def test_read_model_from_settings_returns_model_name():
    """Test reading model from settings.json"""
    w = CurrentWidget()
    with patch("builtins.open", create=True) as mock_file:
        mock_file.return_value.__enter__.return_value.read.return_value = '{"model": "claude-opus-4.6"}'
        with patch("json.load", return_value={"model": "claude-opus-4.6"}):
            model = w._read_model_from_settings()
    assert model == "claude-opus-4.6"


def test_read_model_from_settings_returns_unknown_on_missing():
    """Test fallback when settings not found"""
    w = CurrentWidget()
    with patch("builtins.open", side_effect=FileNotFoundError):
        model = w._read_model_from_settings()
    assert model == "unknown"


def test_read_model_from_settings_returns_unknown_on_json_error():
    """Test fallback when JSON is invalid"""
    w = CurrentWidget()
    with patch("builtins.open", create=True) as mock_file:
        with patch("hud.widgets.current.json.load", side_effect=ValueError):
            model = w._read_model_from_settings()
    assert model == "unknown"


def test_add_pending_stores_entry():
    """Test adding pending entry"""
    w = CurrentWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", "src/foo.py", ts=1000.0))
    assert len(w._pending) == 1


def test_remove_pending_fifo():
    """Test FIFO removal of pending entries"""
    w = CurrentWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", "a.py", ts=1000.0))
        w.add_pending(_pre_event("Read", "b.py", ts=1001.0))
        w.remove_pending(_post_event("Read"))
    # oldest (ts=1000.0) removed first
    assert len(w._pending) == 1
    remaining_key = list(w._pending.keys())[0]
    assert remaining_key[2] == 1001.0  # pre_ts of b.py


def test_remove_pending_no_match_is_noop():
    """Test remove with different tool is noop"""
    w = CurrentWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", ts=1000.0))
        w.remove_pending(_post_event("Bash"))  # different tool — no match
    assert len(w._pending) == 1


def test_reset_clears_pending_and_updates_model():
    """Test reset clears pending and reads model"""
    w = CurrentWidget()
    with patch.object(w, "refresh"):
        w.add_pending(_pre_event("Read", "src/foo.py", ts=1000.0))
        with patch.object(w, "_read_model_from_settings", return_value="claude-opus-4.6"):
            w.reset("session123")
    assert len(w._pending) == 0
    assert w._current_session_id == "session123"
    assert w._current_model == "claude-opus-4.6"


def test_get_current_tool_returns_none_when_empty():
    """Test current tool is None when no pending"""
    w = CurrentWidget()
    assert w._get_current_tool() is None


def test_get_current_tool_returns_most_recent():
    """Test current tool returns most recent pending entry"""
    w = CurrentWidget()
    now = time.time()
    with patch.object(w, "refresh"):
        w.add_pending(ToolEvent(
            session_id="s", tool_name="Read", input_summary="a.py",
            ts=now - 2.0, phase="pre"
        ))
        w.add_pending(ToolEvent(
            session_id="s", tool_name="Bash", input_summary="ls -la",
            ts=now - 0.5, phase="pre"
        ))
    current = w._get_current_tool()
    assert current is not None
    assert "Bash" in current
    assert "↻" in current


def test_render_shows_model_and_context():
    """Test render output includes model and context"""
    w = CurrentWidget()
    w._current_model = "claude-opus-4.6"
    rendered = w.render()
    assert isinstance(rendered, Text)
    plain = rendered.plain
    assert "Model:" in plain
    assert "claude-opus-4.6" in plain
    assert "Context:" in plain


def test_render_shows_current_tool_when_pending():
    """Test render includes current tool when pending"""
    w = CurrentWidget()
    now = time.time()
    w._current_model = "claude-opus-4.6"
    with patch.object(w, "refresh"):
        w.add_pending(ToolEvent(
            session_id="s", tool_name="Read", input_summary="src/main.py",
            ts=now - 0.5, phase="pre"
        ))
    rendered = w.render()
    plain = rendered.plain
    assert "Current:" in plain
    assert "Read" in plain


def test_render_shows_idle_when_no_pending():
    """Test render shows idle when no pending tools"""
    w = CurrentWidget()
    w._current_model = "claude-opus-4.6"
    rendered = w.render()
    plain = rendered.plain
    assert "Current: idle" in plain


def test_event_display_extracts_tool_name():
    """Test event display returns correct tool name and label"""
    w = CurrentWidget()
    event = ToolEvent(
        session_id="s", tool_name="Read", input_summary="src/foo.py",
        ts=1000.0, phase="pre"
    )
    tool_name, label = w._event_display(event)
    assert tool_name == "Read"
    assert label == "src/foo.py"


def test_on_mount_sets_border_title():
    """Test on_mount sets correct border title"""
    w = CurrentWidget()
    w.on_mount()
    assert w.border_title == "CURRENT"


def test_calculate_context_usage_returns_percentage():
    """Test context calculation from token counts."""
    w = CurrentWidget()
    # 2000 tokens used out of 200000 = 1%
    result = w._calculate_context_usage(
        input_tokens=1000,
        cache_write_tokens=500,
        cache_read_tokens=300,
        output_tokens=200
    )
    assert result == (2000, 1.0)  # (total_tokens, percentage)


def test_calculate_context_usage_handles_missing_values():
    """Test calculation with None values."""
    w = CurrentWidget()
    result = w._calculate_context_usage(
        input_tokens=500,
        cache_write_tokens=None,
        cache_read_tokens=None,
        output_tokens=None
    )
    assert result == (500, 0.25)  # 500 / 200000 * 100 = 0.25%


def test_read_request_tokens_reads_last_event():
    """Test reading tokens from LAST assistant message only (not cumulative)."""
    import json
    import tempfile

    w = CurrentWidget()
    # Create temporary transcript with two assistant messages
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write(json.dumps({
            "type": "assistant",
            "message": {
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 10,
                    "cache_read_input_tokens": 5
                }
            }
        }) + "\n")
        # Second (latest) message should be used
        f.write(json.dumps({
            "type": "assistant",
            "message": {
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 75,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0
                }
            }
        }) + "\n")
        temp_path = f.name

    try:
        # Should return tokens from LAST message only, not cumulative
        in_tok, cache_write, cache_read, out_tok = w._read_request_tokens(temp_path)
        assert in_tok == 200  # From last message
        assert cache_write == 0  # From last message
        assert cache_read == 0  # From last message
        assert out_tok == 75  # From last message
    finally:
        os.unlink(temp_path)


def test_render_shows_warning_only_for_extremely_large_responses():
    """Test that warning is only shown for unusually large single responses."""
    w = CurrentWidget()
    # Extremely large single response (edge case)
    w._context_tokens = 250_000  # 125% of limit
    output = str(w.render())
    # Should show warning icon
    assert "⚠️" in output
    # Should NOT show percentage > 100%
    assert "125%" not in output


def test_render_shows_percentage_normally():
    """Test normal percentage display for typical requests."""
    w = CurrentWidget()
    # Typical context usage from a single response
    w._context_tokens = 100_000  # 50% of 200k
    output = str(w.render())
    # Should show 50%
    assert "50%" in output
    # Should NOT show warning
    assert "⚠️" not in output
