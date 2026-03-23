from __future__ import annotations

from textual.widgets import Static

from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent


class SummaryWidget(Static):
    def __init__(self) -> None:
        super().__init__()
        self._tools = 0
        self._agents = 0
        self._skills = 0
        self._errors = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._session_id = ""

    def on_mount(self) -> None:
        self.border_title = "SUMMARY"
        self._render()

    def reset(self, session_id: str) -> None:
        self._tools = 0
        self._agents = 0
        self._skills = 0
        self._errors = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._session_id = session_id
        self._render()

    def update_event(self, event: ToolEvent | AgentEvent | SkillEvent | StopEvent) -> None:
        if isinstance(event, ToolEvent) and event.phase == "post":
            self._tools += 1
            if event.success is False:
                self._errors += 1
            if event.input_tokens:
                self._input_tokens += event.input_tokens
            if event.output_tokens:
                self._output_tokens += event.output_tokens
        elif isinstance(event, AgentEvent):
            self._agents += 1
        elif isinstance(event, SkillEvent):
            self._skills += 1
        self._render()

    def _render(self) -> None:
        sid = self._session_id[:8] if self._session_id else "--"
        tok_in = f"{self._input_tokens:,}" if self._input_tokens else "--"
        tok_out = f"{self._output_tokens:,}" if self._output_tokens else "--"
        self.update(
            f"[dim]{sid}[/dim]\n\n"
            f"skills:  {self._skills}\n"
            f"agents:  {self._agents}\n"
            f"tools:   {self._tools}\n"
            f"[red]errors:  {self._errors}[/red]\n\n"
            f"[dim]in:[/dim]  {tok_in}\n"
            f"[dim]out:[/dim] {tok_out}"
        )
