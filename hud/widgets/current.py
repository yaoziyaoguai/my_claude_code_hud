from __future__ import annotations

import json
import time
from pathlib import Path

from rich.text import Text
from textual.markup import escape
from textual.widget import Widget

from hud.models import ToolEvent, AgentEvent, SkillEvent
from hud.widgets.display import PENDING_BADGE, badge_and_label


class CurrentWidget(Widget):
    """Displays current Claude Code session state: model, context usage, current tool."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # key: (session_id, tool_name, pre_ts)
        # value: (input_summary, depth)
        self._pending: dict[tuple[str, str, float], tuple[str, int]] = {}
        self._current_model: str = "unknown"
        self._current_session_id: str | None = None
        self._context_tokens: int = 0

    def on_mount(self) -> None:
        self.border_title = "CURRENT"

    def _read_model_from_settings(self) -> str:
        """Read model name from ~/.claude/settings.json"""
        try:
            settings_path = Path.home() / ".claude" / "settings.json"
            with open(settings_path) as f:
                settings = json.load(f)
            return settings.get("model", "unknown")
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            return "unknown"

    def _calculate_context_usage(
        self,
        input_tokens: int | None,
        cache_write_tokens: int | None,
        cache_read_tokens: int | None,
        output_tokens: int | None
    ) -> tuple[int, float]:
        """Calculate total tokens and percentage used.

        Returns: (total_tokens_used, percentage)
        """
        total = 0
        total += input_tokens or 0
        total += cache_write_tokens or 0
        total += cache_read_tokens or 0
        total += output_tokens or 0

        max_tokens = 200000
        percentage = (total / max_tokens) * 100 if max_tokens > 0 else 0.0

        return (total, percentage)

    def add_pending(self, event: ToolEvent | AgentEvent | SkillEvent) -> None:
        """Add a pre-phase event to pending tracking."""
        tool_name, label = self._event_display(event)
        self._pending[(event.session_id, tool_name, event.ts)] = (label, event.depth)

    def remove_pending(self, event: ToolEvent | AgentEvent | SkillEvent) -> None:
        """Remove the oldest matching pending entry (FIFO)."""
        tool_name, _ = self._event_display(event)
        min_key = None
        min_ts = float('inf')
        for k in self._pending:
            if k[0] == event.session_id and k[1] == tool_name and k[2] < min_ts:
                min_ts = k[2]
                min_key = k
        if min_key:
            del self._pending[min_key]

    def reset(self, session_id: str) -> None:
        """Reset for new session."""
        self._pending.clear()
        self._current_session_id = session_id
        self._current_model = self._read_model_from_settings()
        self._context_tokens = 0

    def _event_display(self, event: ToolEvent | AgentEvent | SkillEvent) -> tuple[str, str]:
        """Extract tool name and display label from event."""
        if isinstance(event, AgentEvent):
            return "Agent", event.child_description
        if isinstance(event, SkillEvent):
            return "Skill", event.skill_name
        return event.tool_name, event.input_summary

    def _get_current_tool(self) -> str | None:
        """Get the most recent pending tool with elapsed time."""
        if not self._pending:
            return None

        # Get most recent entry (highest timestamp)
        latest = max(self._pending.items(), key=lambda x: x[0][2])
        (_, tool_name, pre_ts), (input_summary, depth) = latest

        elapsed = time.time() - pre_ts
        return f"{escape(tool_name)} ({elapsed:.1f}s) ↻"

    def render(self) -> Text:
        """Render current state: model, context, current tool."""
        lines = []

        # Line 1: Model
        lines.append(f"Model: {self._current_model}")

        # Line 2: Context (placeholder for now)
        lines.append("Context: ██████░░░░ 60% (1200/2000)")

        # Line 3: Current tool (placeholder)
        current_tool = self._get_current_tool()
        if current_tool:
            lines.append(f"Current: {current_tool}")
        else:
            lines.append("Current: idle")

        return Text.from_markup("\n".join(lines))
