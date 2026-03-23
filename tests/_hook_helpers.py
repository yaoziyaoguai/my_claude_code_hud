import subprocess
import sys
import os


def run_hook(
    hook_type: str,
    stdin_data: str,
    session_id: str,
    base_dir: str,
) -> int:
    env = {**os.environ, "CLAUDE_SESSION_ID": session_id, "CLAUDE_HUD_DIR": base_dir}
    result = subprocess.run(
        [sys.executable, "hook.py", hook_type],
        input=stdin_data,
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    return result.returncode
