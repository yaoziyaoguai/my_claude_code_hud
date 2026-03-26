from __future__ import annotations

import time

from rich.text import Text
from textual.markup import escape
from textual.widget import Widget

from hud.models import ToolEvent, AgentEvent, SkillEvent
from hud.widgets.display import PENDING_BADGE, badge_and_label


class ActiveWidget(Widget):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # key: (session_id, tool_name, pre_ts)
        # value: (input_summary, depth)
        self._pending: dict[tuple[str, str, float], tuple[str, int]] = {}

    def on_mount(self) -> None:
        self.border_title = "ACTIVE"
        self.set_interval(1.0, self.refresh)

    def _event_display(self, event: ToolEvent | AgentEvent | SkillEvent) -> tuple[str, str]:
        """Return (tool_name, label) for use as pending dict key and display."""
        if isinstance(event, AgentEvent):
            return "Agent", event.child_description
        if isinstance(event, SkillEvent):
            return "Skill", event.skill_name
        return event.tool_name, event.input_summary

    def add_pending(self, event: ToolEvent | AgentEvent | SkillEvent) -> None:
        """Add a pre-phase event to the pending display."""
        tool_name, label = self._event_display(event)
        self._pending[(event.session_id, tool_name, event.ts)] = (label, event.depth)

    def remove_pending(self, event: ToolEvent | AgentEvent | SkillEvent) -> None:
        """Remove the oldest matching pending entry (FIFO) for a post-phase event."""
        tool_name, _ = self._event_display(event)
        # Single-pass search for minimum timestamp (FIFO removal)
        min_key = None
        min_ts = float('inf')
        for k in self._pending:
            if k[0] == event.session_id and k[1] == tool_name and k[2] < min_ts:
                min_ts = k[2]
                min_key = k
        if min_key:
            del self._pending[min_key]

    def reset(self) -> None:
        self._pending.clear()

    def render(self) -> Text:
        now = time.time()
        lines = []
        items = list(self._pending.items())
        for i, ((sid, tool_name, pre_ts), (input_summary, depth)) in enumerate(items):
            if i >= 4:
                lines.append(f"[dim]+{len(items) - 4} more…[/dim]")
                break
            elapsed = now - pre_ts
            bkey, label = badge_and_label(tool_name, depth)
            badge = PENDING_BADGE[bkey]

            # Show explicit type label for nested tools
            if depth > 0 and tool_name != "Agent" and tool_name != "Skill":
                prefix = "  " * (depth - 1) + "↳ "
                badge_display = f"{PENDING_BADGE['tool']}"
            else:
                prefix = ("  " * (depth - 1) + "↳ ") if depth > 0 else ""
                badge_display = badge

            lines.append(f"{prefix}{badge_display} {escape(label)}  {escape(input_summary)}  {elapsed:.1f}s")
        return Text.from_markup("\n".join(lines))
