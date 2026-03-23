from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches

from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent
from hud.parser import EventParser
from hud.watcher import SessionWatcher
from hud.widgets.event_stream import EventStreamWidget
from hud.widgets.summary import SummaryWidget

CSS = """
Horizontal {
    height: 100%;
}
EventStreamWidget {
    width: 3fr;
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
            yield EventStreamWidget(id="stream")
            yield SummaryWidget()

    async def on_mount(self) -> None:
        self.run_worker(self._watch_loop(), exclusive=True)

    async def _watch_loop(self) -> None:
        tail_task: asyncio.Task | None = None

        async def _tail_session(session_id: str) -> None:
            async for raw in self._watcher.tail(session_id):
                self._handle_raw(raw)

        while True:
            latest = self._watcher.discover_latest_session()
            if latest and latest != self._current_session:
                if tail_task and not tail_task.done():
                    tail_task.cancel()
                self._switch_session(latest)
                tail_task = asyncio.create_task(_tail_session(latest))
            await asyncio.sleep(0.5)

    def _switch_session(self, session_id: str) -> None:
        self._current_session = session_id
        self._parser = EventParser()
        try:
            stream = self.query_one("#stream", EventStreamWidget)
            stream.clear_with_separator(session_id)
            summary = self.query_one(SummaryWidget)
            summary.reset(session_id)
        except NoMatches:
            pass

    def _handle_raw(self, raw: dict) -> None:
        event = self._parser.parse(raw)
        try:
            stream = self.query_one("#stream", EventStreamWidget)
            stream.add_event(event)
            summary = self.query_one(SummaryWidget)
            summary.update_event(event)
        except NoMatches:
            pass
