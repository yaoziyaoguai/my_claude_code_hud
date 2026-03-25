from __future__ import annotations

import time

from rich.text import Text
from textual.widget import Widget

from hud.models import ToolEvent


class ActiveWidget(Widget):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # key: (session_id, tool_name, pre_ts) — pre_ts disambiguates parallel same-tool calls
        # value: input_summary
        self._pending: dict[tuple[str, str, float], str] = {}

    def on_mount(self) -> None:
        self.border_title = "ACTIVE"
        self.set_interval(1.0, self.refresh)

    def add_pending(self, event: ToolEvent) -> None:
        """Add a pre-phase ToolEvent to the pending display."""
        self._pending[(event.session_id, event.tool_name, event.ts)] = event.input_summary
        self.refresh()

    def remove_pending(self, event: ToolEvent) -> None:
        """Remove the oldest matching pending entry (FIFO) for a post-phase ToolEvent."""
        matches = [(k, v) for k, v in self._pending.items()
                   if k[0] == event.session_id and k[1] == event.tool_name]
        if matches:
            oldest_key = min(matches, key=lambda x: x[0][2])[0]
            del self._pending[oldest_key]
        self.refresh()

    def reset(self) -> None:
        self._pending.clear()
        self.refresh()

    def render(self) -> Text:
        now = time.time()
        lines = []
        items = list(self._pending.items())
        for i, ((sid, tool_name, pre_ts), input_summary) in enumerate(items):
            if i >= 4:
                lines.append(f"[dim]+{len(items) - 4} more...[/dim]")
                break
            elapsed = now - pre_ts
            lines.append(f"[yellow][...][/yellow]  {tool_name}  {input_summary}  {elapsed:.1f}s")
        return Text.from_markup("\n".join(lines))
