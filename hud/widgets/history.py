from __future__ import annotations

from collections import deque
from datetime import datetime

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent
from hud.widgets.display import TYPE_BADGE

def _ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _format_event(event: ToolEvent | AgentEvent | SkillEvent | StopEvent) -> list[str]:
    """Return list of lines (Rich markup strings) for an event. First line first."""
    depth = getattr(event, "depth", 0)

    if isinstance(event, AgentEvent):
        # pre: display agent/subagent as context boundary
        if event.phase == "pre":
            badge = TYPE_BADGE["agent"] if event.depth == 0 else TYPE_BADGE["subagent"]
            return [f"{_ts(event.ts)}  {badge}  {event.child_description}"]
        # post: suppress (already shown in pre-phase)
        return []

    if isinstance(event, SkillEvent):
        # pre: display skill as context boundary
        if event.phase == "pre":
            return [f"{_ts(event.ts)}  {TYPE_BADGE['skill']}  {event.skill_name}"]
        # post: suppress (already shown in pre-phase)
        return []

    if isinstance(event, StopEvent):
        return [f"{TYPE_BADGE['stop']}"]

    # ToolEvent post
    if isinstance(event, ToolEvent):
        if event.phase == "pre":
            return []
        dur = f"  {event.duration_ms}ms" if event.duration_ms is not None else ""
        status = TYPE_BADGE["ok"] if event.success is not False else TYPE_BADGE["err"]

        # Nested tools (depth > 0) show indentation; parent already displayed as separate node
        if depth > 0:
            type_label = f"[cyan]↳[/cyan] {TYPE_BADGE['tool']}"
        else:
            type_label = TYPE_BADGE["tool"]

        line = f"{_ts(event.ts)}  {type_label}  {status}  {event.tool_name}  {event.input_summary}{dur}"
        if event.success is False and event.error_excerpt:
            return [line, f"         {event.error_excerpt}"]
        return [line]

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

        # Suppress consecutive stop markers — they cluster and add no information
        if isinstance(event, StopEvent) and self._lines and self._lines[-1] == f"{TYPE_BADGE['stop']}":
            return

        for line in lines:
            self._lines.append(line)
        if lines:
            self._refresh_content()
            self.scroll_end(animate=False)

    def reset(self, session_id: str) -> None:
        self._lines.clear()
        self._lines.append(f"[dim]─── session {session_id[:8]} ───[/dim]")
        self._refresh_content()
