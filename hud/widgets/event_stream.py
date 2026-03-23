from __future__ import annotations

from textual.widgets import RichLog
from textual.message import Message

from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent

_STYLE = {
    "ok": "[green][OK][/green]",
    "err": "[red][ERR][/red]",
    "pending": "[yellow][...][/yellow]",
    "skill": "[purple][SKILL][/purple]",
    "agent": "[blue][AGENT][/blue]",
    "stop": "[dim][STOP][/dim]",
}


class EventStreamWidget(RichLog):

    class NewEvent(Message):
        def __init__(self, event: ToolEvent | AgentEvent | SkillEvent | StopEvent) -> None:
            super().__init__()
            self.event = event

    def on_mount(self) -> None:
        self.border_title = "EVENT STREAM"

    def add_event(self, event: ToolEvent | AgentEvent | SkillEvent | StopEvent) -> None:
        from datetime import datetime
        ts_str = datetime.fromtimestamp(event.ts).strftime("%H:%M")

        if isinstance(event, SkillEvent):
            self.write(f"{ts_str} {_STYLE['skill']} {event.skill_name}")
        elif isinstance(event, AgentEvent):
            self.write(f"{ts_str} {_STYLE['agent']} {event.child_description}")
        elif isinstance(event, StopEvent):
            self.write(f"{ts_str} {_STYLE['stop']} session ended")
        elif isinstance(event, ToolEvent):
            if event.phase == "pre":
                self.write(f"{ts_str} {_STYLE['pending']} {event.tool_name}  {event.input_summary}")
            elif event.success is False:
                self.write(f"{ts_str} {_STYLE['err']} {event.tool_name}  {event.input_summary}")
                if event.error_excerpt:
                    self.write(f"       {event.error_excerpt}")
            else:
                dur = f" {event.duration_ms}ms" if event.duration_ms is not None else ""
                self.write(f"{ts_str} {_STYLE['ok']} {event.tool_name}  {event.input_summary}{dur}")

    def clear_with_separator(self, session_id: str) -> None:
        self.clear()
        self.write(f"[dim]--- new session: {session_id} ---[/dim]")
