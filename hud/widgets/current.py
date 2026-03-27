from __future__ import annotations

import json
import time
from pathlib import Path

from rich.text import Text
from textual.markup import escape
from textual.widget import Widget

from hud.models import ToolEvent, AgentEvent, SkillEvent
from hud.widgets.display import PENDING_BADGE, badge_and_label

# Constants
MAX_CONTEXT_TOKENS = 200000
PROGRESS_BAR_WIDTH = 10


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

        percentage = (total / MAX_CONTEXT_TOKENS) * 100 if MAX_CONTEXT_TOKENS > 0 else 0.0

        return (total, percentage)

    def _read_request_tokens(self, transcript_path: str) -> tuple[int, int, int, int]:
        """Read token counts from the LAST assistant message in transcript file.

        This represents the CURRENT REQUEST's context usage (not session cumulative).
        Only the most recent assistant response is considered, showing the snapshot
        of context consumption for the current Claude Code request.

        Contrast with HudApp._read_cumulative_tokens() which sums ALL messages
        for the entire session (used by SummaryWidget).

        Returns: (input_tokens, cache_write, cache_read, output_tokens) from last message only
        """
        try:
            # Read all lines and get the last assistant message
            last_usage = None
            with open(transcript_path) as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") == "assistant":
                        last_usage = d.get("message", {}).get("usage", {})

            # Extract token counts from last message
            if last_usage:
                in_tok = last_usage.get("input_tokens") or 0
                cache_write = last_usage.get("cache_creation_input_tokens") or 0
                cache_read = last_usage.get("cache_read_input_tokens") or 0
                out_tok = last_usage.get("output_tokens") or 0
                return (in_tok, cache_write, cache_read, out_tok)
        except OSError:
            pass
        return (0, 0, 0, 0)

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

    def update_context_from_transcript(self, transcript_path: str | None) -> None:
        """Read token counts from transcript and update context display."""
        if not transcript_path:
            return
        in_tok, cache_write, cache_read, out_tok = self._read_request_tokens(transcript_path)
        self._context_tokens = in_tok + cache_write + cache_read + out_tok

    def set_transcript_path(self, transcript_path: str | None) -> None:
        """Set current session's transcript path for context calculation."""
        if transcript_path:
            self.update_context_from_transcript(transcript_path)

    def _event_display(self, event: ToolEvent | AgentEvent | SkillEvent) -> tuple[str, str]:
        """Extract tool name and display label from event."""
        if isinstance(event, AgentEvent):
            return "Agent", event.child_description
        if isinstance(event, SkillEvent):
            return "Skill", event.skill_name
        return event.tool_name, event.input_summary

    def _get_current_tool(self) -> str | None:
        """Get the most recent pending tool with elapsed time, with highlighted name."""
        if not self._pending:
            return None

        latest = max(self._pending.items(), key=lambda x: x[0][2])
        (_, tool_name, pre_ts), (input_summary, depth) = latest

        elapsed = time.time() - pre_ts
        return f"Current: [bold]{escape(tool_name)}[/bold] ({elapsed:.1f}s) ↻"

    def render(self) -> Text:
        """Render current state: model, context, current tool."""
        lines = []

        # Line 1: Model
        lines.append(f"Model: {self._current_model}")

        # Line 2: Context with progress bar
        total_tokens, percentage = self._calculate_context_usage(
            self._context_tokens, 0, 0, 0
        )
        capped_percentage = min(percentage, 100.0)  # Cap at 100%
        used = int(capped_percentage / PROGRESS_BAR_WIDTH)
        bar = "█" * used + "░" * (PROGRESS_BAR_WIDTH - used)
        formatted_tokens = f"({total_tokens}/{MAX_CONTEXT_TOKENS})" if total_tokens > 0 else f"(0/{MAX_CONTEXT_TOKENS})"
        # Show warning if over limit
        if percentage > 100:
            lines.append(f"Context: {bar} ⚠️  {formatted_tokens}")
        else:
            lines.append(f"Context: {bar} {percentage:.0f}% {formatted_tokens}")

        # Line 3: Current tool with elapsed time
        current = self._get_current_tool()
        if current:
            lines.append(current)
        else:
            lines.append("Current: idle")

        return Text.from_markup("\n".join(lines))
