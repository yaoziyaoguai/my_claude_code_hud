from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator


class SessionWatcher:
    def __init__(self, base_dir: str = "/tmp/claude-hud") -> None:
        self._base_dir = Path(base_dir)

    def discover_latest_session(self) -> str | None:
        files = sorted(self._base_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime)
        if not files:
            return None
        return files[-1].stem

    async def tail(self, session_id: str) -> AsyncIterator[dict]:
        path = self._base_dir / f"{session_id}.jsonl"
        offset = 0

        # Read existing content first
        if path.exists():
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue
                offset = path.stat().st_size

        # Poll for new lines
        while True:
            await asyncio.sleep(0.05)  # 50ms polling
            if not path.exists():
                continue
            size = path.stat().st_size
            if size <= offset:
                continue
            with open(path) as f:
                f.seek(offset)
                new_data = f.read()
                offset = f.tell()
            for line in new_data.strip().split("\n"):
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

    async def watch_for_sessions(self) -> AsyncIterator[str]:
        """Yield session IDs as new JSONL files appear."""
        seen: set[str] = set()
        while True:
            if self._base_dir.exists():
                for f in self._base_dir.glob("*.jsonl"):
                    sid = f.stem
                    if sid not in seen:
                        seen.add(sid)
                        yield sid
            await asyncio.sleep(0.2)
