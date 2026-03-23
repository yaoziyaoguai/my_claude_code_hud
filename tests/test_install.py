import json
from pathlib import Path

from hud.install import install_hooks


def test_install_creates_hooks_in_empty_settings(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")
    install_hooks(settings_path=str(settings_path), hook_script_path="/usr/local/bin/hook.py")
    data = json.loads(settings_path.read_text())
    assert "hooks" in data
    assert "PreToolUse" in data["hooks"]
    assert "PostToolUse" in data["hooks"]
    assert "Stop" in data["hooks"]
    assert data["hooks"]["PreToolUse"][0]["matcher"] == "*"
    assert data["hooks"]["PostToolUse"][0]["hooks"][0].get("async") is True


def test_install_is_idempotent(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")
    install_hooks(settings_path=str(settings_path), hook_script_path="/x/hook.py")
    install_hooks(settings_path=str(settings_path), hook_script_path="/x/hook.py")
    data = json.loads(settings_path.read_text())
    assert len(data["hooks"]["PreToolUse"]) == 1


def test_install_preserves_existing_hooks(tmp_path):
    settings_path = tmp_path / "settings.json"
    existing = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}
            ]
        }
    }
    settings_path.write_text(json.dumps(existing))
    install_hooks(settings_path=str(settings_path), hook_script_path="/x/hook.py")
    data = json.loads(settings_path.read_text())
    assert len(data["hooks"]["PreToolUse"]) == 2
