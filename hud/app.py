from __future__ import annotations

import asyncio
import json

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches

from hud.cost import estimate_cost_full
from hud.parser import EventParser
from hud.watcher import SessionWatcher
from hud.widgets.current import CurrentWidget
from hud.widgets.history import HistoryWidget
from hud.widgets.summary import SummaryWidget
from hud.models import ToolEvent, StopEvent, AgentEvent, SkillEvent

CSS = """
Horizontal {
    height: 100%;
}
Vertical {
    width: 3fr;
}
CurrentWidget {
    height: 7;
    border: solid $accent;
}
HistoryWidget {
    border: solid $primary;
}
SummaryWidget {
    width: 1fr;
    border: solid $secondary;
    padding: 1;
}
"""


class HudApp(App):
    CSS = CSS
    TITLE = "Claude HUD"

    def __init__(self, base_dir: str = "/tmp/claude-hud") -> None:
        super().__init__()
        self._watcher = SessionWatcher(base_dir)
        self._parser = EventParser()
        self._current_session: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical():
                yield CurrentWidget()
                yield HistoryWidget()
            yield SummaryWidget()

    async def on_mount(self) -> None:
        self.run_worker(self._watch_loop(), exclusive=True)

    async def _watch_loop(self) -> None:
        tail_worker = None

        while True:
            latest = self._watcher.discover_latest_session()
            if latest and latest != self._current_session:
                if tail_worker is not None:
                    tail_worker.cancel()
                self._switch_session(latest)
                tail_worker = self.run_worker(
                    self._tail_session(latest), exclusive=False, name="tail"
                )
            elif latest and tail_worker is not None and tail_worker.is_done:
                # Restart if tail worker died unexpectedly
                tail_worker = self.run_worker(
                    self._tail_session(latest), exclusive=False, name="tail"
                )
            await asyncio.sleep(0.5)

    async def _tail_session(self, session_id: str) -> None:
        async for raw in self._watcher.tail(session_id):
            self._handle_raw(raw)

    def _switch_session(self, session_id: str) -> None:
        self._current_session = session_id
        self._parser = EventParser()
        try:
            self.query_one(CurrentWidget).reset(session_id)
            self.query_one(HistoryWidget).reset(session_id)
            self.query_one(SummaryWidget).reset(session_id)
        except NoMatches:
            pass

    def _handle_raw(self, raw: dict) -> None:
        event = self._parser.parse(raw)
        if event is None:
            return
        try:
            current = self.query_one(CurrentWidget)
            history = self.query_one(HistoryWidget)
            summary = self.query_one(SummaryWidget)
        except NoMatches:
            return

        # Agent and Skill: display at pre-phase as context boundaries
        if isinstance(event, (AgentEvent, SkillEvent)) and event.phase == "pre":
            current.add_pending(event)
            history.add_event(event)
            current.refresh()
        # Agent and Skill: finalize at post-phase (add close marker to history, update summary)
        elif isinstance(event, (AgentEvent, SkillEvent)) and event.phase == "post":
            current.remove_pending(event)
            history.add_event(event)
            summary.update_event(event)
            current.refresh()
        # Tool: display both pre and post, count at post
        elif isinstance(event, ToolEvent):
            if event.phase == "pre":
                current.add_pending(event)
                current.refresh()
            else:  # post
                current.remove_pending(event)
                history.add_event(event)
                summary.update_event(event)
                current.refresh()
        # Stop: always display and update summary
        else:
            history.add_event(event)
            summary.update_event(event)
            if isinstance(event, StopEvent) and event.transcript_path:
                # Single transcript scan for both context display and cost totals
                tokens = self._read_cumulative_tokens(event.transcript_path)
                in_tok, cache_write, cache_read, out_tok = tokens
                current._context_tokens = in_tok + cache_write + cache_read + out_tok
                cost = estimate_cost_full(in_tok, cache_write, cache_read, out_tok)
                summary.set_totals(in_tok + cache_write + cache_read, out_tok, cost)

    def _update_cost_from_transcript(self, path: str, summary: SummaryWidget) -> None:
        tokens = self._read_cumulative_tokens(path)
        in_tok, cache_write, cache_read, out_tok = tokens
        cost = estimate_cost_full(in_tok, cache_write, cache_read, out_tok)
        summary.set_totals(in_tok + cache_write + cache_read, out_tok, cost)

    @staticmethod
    def _read_cumulative_tokens(path: str) -> tuple[int, int, int, int]:
        """Read cumulative token counts across entire transcript (all assistant messages).

        Called once per StopEvent — no caching needed since transcripts grow during a session.
        Returns: (input_tokens, cache_write, cache_read, output_tokens)
        """
        in_tok = cache_write = cache_read = out_tok = 0
        try:
            with open(path) as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") == "assistant":
                        usage = d.get("message", {}).get("usage", {})
                        in_tok += usage.get("input_tokens") or 0
                        cache_write += usage.get("cache_creation_input_tokens") or 0
                        cache_read += usage.get("cache_read_input_tokens") or 0
                        out_tok += usage.get("output_tokens") or 0
        except OSError:
            pass
        return (in_tok, cache_write, cache_read, out_tok)
