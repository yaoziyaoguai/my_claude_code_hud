"""Install Claude HUD hooks into ~/.claude/settings.json."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_DEFAULT_SETTINGS = os.path.expanduser("~/.claude/settings.json")


def _make_hook_entry(hook_script_path: str, hook_type: str, async_: bool = False) -> dict:
    entry: dict = {
        "type": "command",
        "command": f"{sys.executable} {hook_script_path} {hook_type}",
    }
    if async_:
        entry["async"] = True
    return entry


def _hook_already_present(entries: list, hook_script_path: str) -> bool:
    for entry in entries:
        for h in entry.get("hooks", []):
            if hook_script_path in h.get("command", ""):
                return True
    return False


def install_hooks(
    settings_path: str = _DEFAULT_SETTINGS,
    hook_script_path: str | None = None,
) -> None:
    if hook_script_path is None:
        hook_script_path = str(Path(__file__).parent.parent / "hook.py")

    path = Path(settings_path)
    if path.exists():
        data = json.loads(path.read_text())
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}

    hooks = data.setdefault("hooks", {})

    hook_configs = [
        ("PreToolUse", "pre", False, "*"),
        ("PostToolUse", "post", True, "*"),
        ("Stop", "stop", True, None),
    ]

    for event_name, type_arg, async_, matcher in hook_configs:
        entries = hooks.setdefault(event_name, [])
        if _hook_already_present(entries, hook_script_path):
            continue
        new_entry: dict = {"hooks": [_make_hook_entry(hook_script_path, type_arg, async_)]}
        if matcher:
            new_entry["matcher"] = matcher
        entries.append(new_entry)

    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Hooks installed to {settings_path}")


if __name__ == "__main__":
    install_hooks()
