from __future__ import annotations

from textual.widgets import Static
from rich.console import RichCast

from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent
from hud.cost import estimate_cost


class SummaryWidget(Static):
    def __init__(self) -> None:
        super().__init__()
        self._tools = 0
        self._subagents = 0
        self._agents = 0
        self._skills = 0
        self._errors = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost = 0.0
        self._session_id = ""

    def on_mount(self) -> None:
        self.border_title = "SUMMARY"

    def reset(self, session_id: str) -> None:
        self._tools = 0
        self._subagents = 0
        self._agents = 0
        self._skills = 0
        self._errors = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost = 0.0
        self._session_id = session_id
        self.refresh()

    def set_totals(self, input_tokens: int, output_tokens: int, cost: float) -> None:
        """Override accumulated per-tool counts with authoritative transcript totals."""
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._cost = cost
        self.refresh()

    def update_event(self, event: ToolEvent | AgentEvent | SkillEvent | StopEvent) -> None:
        if isinstance(event, ToolEvent) and event.phase == "post":
            if event.depth > 0:
                self._subagents += 1
            else:
                self._tools += 1
            if event.success is False:
                self._errors += 1
            new_in = event.input_tokens or 0
            new_out = event.output_tokens or 0
            if new_in or new_out:
                self._input_tokens += new_in
                self._output_tokens += new_out
                self._cost += estimate_cost(new_in, new_out)
        elif isinstance(event, AgentEvent) and event.phase == "post":
            self._agents += 1
        elif isinstance(event, SkillEvent) and event.phase == "post":
            self._skills += 1
        else:
            return
        self.refresh()

    def render(self) -> RichCast:
        sid = self._session_id[:8] if self._session_id else "--"
        tok_in = f"{self._input_tokens:,}" if self._input_tokens else "--"
        tok_out = f"{self._output_tokens:,}" if self._output_tokens else "--"
        return (
            f"[dim]{sid}[/dim]\n\n"
            f"agents:  {self._agents}\n"
            f"skills:  {self._skills}\n"
            f"tools:   {self._tools}\n"
            f"actions: {self._subagents}\n"
            f"[red]errors:  {self._errors}[/red]\n\n"
            f"[dim]in:[/dim]  {tok_in}\n"
            f"[dim]out:[/dim] {tok_out}\n"
            f"~${self._cost:.3f}"
        )
