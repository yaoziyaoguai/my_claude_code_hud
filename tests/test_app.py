from unittest.mock import patch, MagicMock
from hud.models import ToolEvent, SkillEvent, AgentEvent, StopEvent
from hud.widgets.summary import SummaryWidget
from hud.widgets.active import ActiveWidget
from hud.widgets.history import HistoryWidget


# ── SummaryWidget tests ──────────────────────────────────────────────────────

def test_summary_counts():
    s = SummaryWidget()
    with patch.object(s, "refresh"):
        s.update_event(ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                                 ts=1.0, phase="post", success=True))
        s.update_event(ToolEvent(session_id="s", tool_name="Bash", input_summary="y",
                                 ts=2.0, phase="post", success=False))
        s.update_event(SkillEvent(session_id="s", skill_name="tdd", ts=3.0, phase="post"))
        s.update_event(AgentEvent(session_id="s", child_description="rev", ts=4.0, phase="post"))
    assert s._tools == 2
    assert s._errors == 1
    assert s._skills == 1
    assert s._agents == 1


def test_summary_reset():
    s = SummaryWidget()
    s._tools = 5
    with patch.object(s, "refresh"):
        s.reset("new-session")
    assert s._tools == 0
    assert s._session_id == "new-session"


def test_summary_token_accumulation():
    s = SummaryWidget()
    with patch.object(s, "refresh"):
        s.update_event(ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                                 ts=1.0, phase="post", success=True,
                                 input_tokens=100, output_tokens=50))
        s.update_event(ToolEvent(session_id="s", tool_name="Bash", input_summary="y",
                                 ts=2.0, phase="post", success=True,
                                 input_tokens=200, output_tokens=80))
    assert s._input_tokens == 300
    assert s._output_tokens == 130


def test_summary_cost_accumulates():
    s = SummaryWidget()
    with patch.object(s, "refresh"):
        s.update_event(ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                                 ts=1.0, phase="post", success=True,
                                 input_tokens=1_000_000, output_tokens=0))
    assert abs(s._cost - 3.0) < 0.001


def test_summary_reset_clears_cost():
    s = SummaryWidget()
    s._cost = 5.0
    with patch.object(s, "refresh"):
        s.reset("new-session")
    assert s._cost == 0.0


# ── Event routing tests ────────────────────────────────────────────────────

def test_pre_event_goes_to_active_only():
    active = ActiveWidget()
    history = HistoryWidget()
    summary = SummaryWidget()

    pre = ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                    ts=1.0, phase="pre")

    with patch.object(active, "refresh"), \
         patch.object(history, "query_one", return_value=MagicMock()), \
         patch.object(summary, "refresh"):
        active.add_pending(pre)

    assert len(active._pending) == 1
    assert len(history._lines) == 0


def test_post_event_goes_to_history_and_summary():
    active = ActiveWidget()
    history = HistoryWidget()
    summary = SummaryWidget()

    pre = ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                    ts=1.0, phase="pre")
    post = ToolEvent(session_id="s", tool_name="Read", input_summary="x",
                     ts=2.0, phase="post", success=True)

    with patch.object(active, "refresh"), \
         patch.object(history, "query_one", return_value=MagicMock()), \
         patch.object(summary, "refresh"):
        active.add_pending(pre)
        active.remove_pending(post)
        history.add_event(post)
        summary.update_event(post)

    assert len(active._pending) == 0
    assert len(history._lines) == 1
    assert summary._tools == 1


def test_skill_event_goes_to_history_not_active():
    active = ActiveWidget()
    history = HistoryWidget()
    summary = SummaryWidget()

    # Skills are displayed at pre phase (marks context boundary), counted at post phase
    ev_pre = SkillEvent(session_id="s", skill_name="tdd", ts=1.0, phase="pre")
    ev_post = SkillEvent(session_id="s", skill_name="tdd", ts=1.5, phase="post")

    with patch.object(active, "refresh"), \
         patch.object(history, "query_one", return_value=MagicMock()), \
         patch.object(summary, "refresh"):
        history.add_event(ev_pre)  # pre phase shown in history
        summary.update_event(ev_post)  # post phase counted in summary

    assert len(active._pending) == 0
    assert len(history._lines) == 1
    assert summary._skills == 1


def test_session_switch_resets_all_widgets():
    active = ActiveWidget()
    history = HistoryWidget()
    summary = SummaryWidget()

    with patch.object(active, "refresh"), \
         patch.object(history, "query_one", return_value=MagicMock()), \
         patch.object(summary, "refresh"):
        active.add_pending(ToolEvent(session_id="s", tool_name="Read",
                                     input_summary="x", ts=1.0, phase="pre"))
        summary._tools = 3
        summary._cost = 9.99
        active.reset()
        history.reset("new-session")
        summary.reset("new-session")

    assert len(active._pending) == 0
    assert summary._tools == 0
    assert summary._cost == 0.0
    assert history._lines[0].startswith("[dim]") and "new-sess" in history._lines[0]
