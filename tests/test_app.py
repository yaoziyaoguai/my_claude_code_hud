from unittest.mock import patch
from hud.models import ToolEvent, SkillEvent, AgentEvent, StopEvent
from hud.widgets.summary import SummaryWidget


def test_summary_counts():
    s = SummaryWidget()
    s._session_id = "abc"
    with patch.object(s, "refresh"):  # avoid calling self.update() without mount
        s.update_event(ToolEvent(
            session_id="abc", tool_name="Read", input_summary="x",
            ts=1.0, phase="post", success=True,
        ))
        s.update_event(ToolEvent(
            session_id="abc", tool_name="Bash", input_summary="y",
            ts=2.0, phase="post", success=False,
        ))
        s.update_event(SkillEvent(session_id="abc", skill_name="tdd", ts=3.0))
        s.update_event(AgentEvent(session_id="abc", child_description="rev", ts=4.0))
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
        s.update_event(ToolEvent(
            session_id="abc", tool_name="Read", input_summary="x",
            ts=1.0, phase="post", success=True, input_tokens=100, output_tokens=50,
        ))
        s.update_event(ToolEvent(
            session_id="abc", tool_name="Bash", input_summary="y",
            ts=2.0, phase="post", success=True, input_tokens=200, output_tokens=80,
        ))
    assert s._input_tokens == 300
    assert s._output_tokens == 130


def test_summary_cost_accumulates():
    from hud.widgets.summary import SummaryWidget
    from hud.models import ToolEvent
    from unittest.mock import patch
    s = SummaryWidget()
    with patch.object(s, "refresh"):
        s.update_event(ToolEvent(
            session_id="s", tool_name="Read", input_summary="x",
            ts=1.0, phase="post", success=True,
            input_tokens=1_000_000, output_tokens=0,
        ))
    assert abs(s._cost - 3.0) < 0.001


def test_summary_reset_clears_cost():
    from hud.widgets.summary import SummaryWidget
    from unittest.mock import patch
    s = SummaryWidget()
    s._cost = 5.0
    with patch.object(s, "refresh"):
        s.reset("new-session")
    assert s._cost == 0.0
