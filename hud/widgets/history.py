from __future__ import annotations

from collections import deque
from datetime import datetime

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent

_STYLE = {
    "ok":      "[green][OK][/green]",
    "err":     "[red][ERR][/red]",
    "skill":   "[purple][SKILL][/purple]",
    "agent":   "[blue][AGENT][/blue]",
    "stop":    "[dim][STOP][/dim]",
}


def _ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def _format_event(event: ToolEvent | AgentEvent | SkillEvent | StopEvent) -> list[str]:
    """Return list of lines (Rich markup strings) for an event. Newest line first."""
    indent = "  " * getattr(event, "depth", 0)

    if isinstance(event, AgentEvent):
        return [f"{indent}{_ts(event.ts)} {_STYLE['agent']} {event.child_description}"]

    if isinstance(event, SkillEvent):
        return [f"{indent}{_ts(event.ts)} {_STYLE['skill']} {event.skill_name}"]

    if isinstance(event, StopEvent):
        return [f"{_STYLE['stop']} session ended"]

    # ToolEvent post
    if isinstance(event, ToolEvent):
        if event.phase == "pre":
            return []  # pre-phase ignored
        dur = f" {event.duration_ms}ms" if event.duration_ms is not None else ""
        if event.success is False:
            err_indent = indent + "       "
            lines = [f"{indent}{_ts(event.ts)} {_STYLE['err']} {event.tool_name}  {event.input_summary}{dur}"]
            if event.error_excerpt:
                lines.append(f"{err_indent}{event.error_excerpt}")
            # Return error excerpt first (it's newer in append order, goes to top)
            return list(reversed(lines))
        return [f"{indent}{_ts(event.ts)} {_STYLE['ok']} {event.tool_name}  {event.input_summary}{dur}"]

    return []


class HistoryWidget(VerticalScroll):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._lines: deque[str] = deque(maxlen=500)

    def compose(self):
        yield Static("", id="history-content", markup=True)

    def on_mount(self) -> None:
        self.border_title = "HISTORY"

    def _refresh_content(self) -> None:
        self.query_one("#history-content", Static).update("\n".join(self._lines))

    def add_event(self, event: ToolEvent | AgentEvent | SkillEvent | StopEvent) -> None:
        lines = _format_event(event)
        # appendleft in reverse so lines[0] ends up at deque index 0 (top of display)
        for line in reversed(lines):
            self._lines.appendleft(line)
        if lines:
            self._refresh_content()

    def reset(self, session_id: str) -> None:
        self._lines.clear()
        self._lines.appendleft(f"[dim]--- new session: {session_id} ---[/dim]")
        self._refresh_content()
