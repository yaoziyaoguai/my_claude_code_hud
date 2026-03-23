# Claude HUD

A real-time monitoring sidebar for Claude Code. Watch live tool calls, agent activity, skill activations, and token usage as Claude works—all in a dedicated terminal window.

## ⚠️ Pre-release Notice

This project is in **active development**. While all tests pass, **real-world Claude Code session integration testing is ongoing**. Use at your own risk in production environments.

## Overview

Claude HUD integrates with Claude Code's hooks system to display real-time events without modifying Claude Code itself. Simply run `claude-hud watch` in a separate terminal alongside your normal `claude` session.

**Current Status**: v0.1.0 (28/28 tests passing, beta testing phase)

## Features

- **Real-time Event Monitoring**: Track tool calls, agent hierarchies, skill activations, and token usage
- **Zero Friction**: Installs via `~/.claude/settings.json`—no changes to Claude Code
- **Terminal UI**: Clean Textual-based dashboard with event stream and summary statistics
- **Session Tracking**: Per-session event logging to `/tmp/claude-hud/{session_id}.jsonl`

## Architecture

```
User Terminal 1                    User Terminal 2
─────────────────                 ───────────────────
$ claude-hud watch                $ claude
   │                                 │
   │  Textual TUI                    │  Claude Code
   │  Async file watcher            │  (normal interactive use)
   │  watches /tmp/claude-hud/      │
   │                                 │
   └─────────────────────────────────┘
      File-based event log
  /tmp/claude-hud/{session_id}.jsonl
```

### How It Works

1. **Hook Registration**: `claude-hud install` registers hooks in `~/.claude/settings.json`
2. **Event Capture**: Claude Code hooks pipe JSON events to `hook.py` on stdin
3. **Event Logging**: `hook.py` appends events to the session's JSONL file
4. **Real-time Display**: `claude-hud watch` tails the JSONL file and renders the Textual UI

## Installation

### Prerequisites

- Python 3.10 or higher
- Claude Code installed and configured (`claude` command available)
- `pip` or `uv` for package installation
- Git (to clone this repository)

### Step 1: Clone and Install

```bash
# Clone the repository
git clone https://github.com/yaoziyaoguai/my_claude_code_hud.git
cd my_claude_code_hud

# Install in development mode (installs dependencies and registers CLI)
pip install -e .
```

**Expected output:**
```
Successfully installed claude-hud-0.1.0
```

Verify installation:
```bash
claude-hud --help
```

### Step 2: Register Hooks with Claude Code

```bash
claude-hud install
```

**What this does:**
- Modifies `~/.claude/settings.json` to register three hooks: `PreToolUse`, `PostToolUse`, and `Stop`
- Creates directory `/tmp/claude-hud/` for event logging
- Backs up original `settings.json` to `settings.json.bak`

**Check if successful:**
```bash
grep -A5 "PreToolUse" ~/.claude/settings.json
```

You should see hook configuration referencing `hook.py`.

### Troubleshooting Installation

**"command not found: claude-hud"**
- Ensure Python is in PATH: `which python3`
- Reinstall: `pip install --force-reinstall -e .`
- Try explicit path: `/usr/local/bin/python3 -m pip install -e .`

**"Permission denied" when writing to ~/.claude/settings.json**
- Ensure file is writable: `chmod 600 ~/.claude/settings.json`
- Check directory permissions: `ls -la ~/.claude/`

**"settings.json not found"**
- Run `claude --help` first to initialize Claude Code config
- Or manually create: `mkdir -p ~/.claude`

## Usage

### Start Monitoring

```bash
# Terminal 1: Start the HUD
claude-hud watch

# Terminal 2: Use Claude Code normally
claude
```

The HUD will display:
- **Event Stream**: Live tool calls, agent activity, and skill activations
- **Summary**: Token usage, event counts, and timing statistics

### Uninstall Hooks

```bash
claude-hud uninstall
```

This removes hooks from `~/.claude/settings.json`.

## Project Structure

```
.
├── hook.py                    # ~30-line hook handler (reads stdin → JSONL)
├── hud/                       # Main TUI application
│   ├── __main__.py           # CLI entry point (install/watch commands)
│   ├── app.py                # Textual TUI app
│   ├── widgets/
│   │   ├── event_stream.py   # Event list widget
│   │   └── summary.py        # Statistics widget
│   └── models.py             # Data models (Event, Session)
├── tests/                     # 28 comprehensive tests
├── docs/
│   └── superpowers/
│       ├── specs/            # Design specification
│       └── plans/            # Implementation plan
└── pyproject.toml            # Project configuration
```

## Development

### Run Tests

```bash
pytest -v
```

Current coverage: **80%+**

### Test-Driven Development

Tests cover:
- **Unit Tests**: Individual functions and widgets
- **Integration Tests**: Hook payload parsing, event logging
- **E2E Tests**: Full install → watch → event flow

## Hook Payload Specification

### PreToolUse Event

```json
{
  "tool_name": "Bash",
  "tool_input": {"command": "ls -la"}
}
```

### PostToolUse Event

```json
{
  "tool_name": "Bash",
  "tool_input": {"command": "ls -la"},
  "tool_output": {"stdout": "..."},
  "usage": {
    "input_tokens": 1000,
    "output_tokens": 500,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0
  }
}
```

### Stop Event

```json
{
  "transcript_path": "/path/to/transcript"
}
```

## Troubleshooting

### HUD won't start / Blank window appears

**Symptoms**: `claude-hud watch` starts but shows empty event stream

**Solutions:**
1. Verify `CLAUDE_SESSION_ID` is set in Claude Code session:
   ```bash
   echo $CLAUDE_SESSION_ID
   ```
   If empty, restart Claude Code.

2. Check event log directory exists:
   ```bash
   ls -la /tmp/claude-hud/
   ls -la /tmp/claude-hud/$CLAUDE_SESSION_ID.jsonl
   ```

3. Manually test hook execution:
   ```bash
   echo '{"tool_name": "Bash", "tool_input": {"command": "ls"}}' | python hook.py pre
   ```
   Should append to JSONL file without errors.

### No events appearing in HUD

**Symptoms**: HUD is running but no events displayed even after running `claude` commands

**Solutions:**
1. Verify hooks are registered:
   ```bash
   cat ~/.claude/settings.json | grep -A2 "PreToolUse"
   ```
   Should show hook configuration with path to `hook.py`.

2. Check hooks are actually firing (enable Claude Code debug):
   ```bash
   CLAUDE_DEBUG=true claude
   ```
   Look for "Hook fired" messages.

3. Verify event file is being written:
   ```bash
   tail -f /tmp/claude-hud/$CLAUDE_SESSION_ID.jsonl
   ```
   Run a command in Claude and watch for new lines.

4. Reinstall hooks:
   ```bash
   claude-hud uninstall
   claude-hud install
   ```

### "Permission denied" errors

**Symptoms**:
```
PermissionError: [Errno 13] Permission denied: '/tmp/claude-hud/...'
```

**Solutions:**
```bash
# Check /tmp/claude-hud/ permissions
ls -la /tmp/claude-hud/

# Make writable if needed
chmod 777 /tmp/claude-hud/

# Or reset completely
rm -rf /tmp/claude-hud/
mkdir -p /tmp/claude-hud/
chmod 777 /tmp/claude-hud/
```

### HUD crashes with "CLAUDE_SESSION_ID not set"

**Symptoms**:
```
Error: CLAUDE_SESSION_ID environment variable not set
```

**Solutions:**
- Always start HUD **after** starting Claude Code (which sets the session ID)
- Claude Code sets `CLAUDE_SESSION_ID` automatically on startup
- If using a shell session that predates Claude startup, source it:
  ```bash
  eval $(claude env)  # If available
  ```

### High CPU usage or slow response

**Symptoms**: HUD UI is laggy, CPU at 50%+

**Solutions:**
1. Check event file size (may be too large):
   ```bash
   wc -l /tmp/claude-hud/$CLAUDE_SESSION_ID.jsonl
   du -h /tmp/claude-hud/$CLAUDE_SESSION_ID.jsonl
   ```

2. If > 100MB, clean up old sessions:
   ```bash
   rm /tmp/claude-hud/*.jsonl
   ```

3. Restart HUD to reload fresh session

### HUD won't uninstall / settings.json corruption

**Solutions:**
1. Manual restoration:
   ```bash
   # If backup exists
   cp ~/.claude/settings.json.bak ~/.claude/settings.json
   ```

2. Or manually edit `~/.claude/settings.json`:
   - Remove all `PreToolUse`, `PostToolUse`, and `Stop` hook entries
   - Verify JSON syntax (use `jq` to validate):
     ```bash
     jq . ~/.claude/settings.json
     ```

## Next Steps

- [ ] Real-world testing with live Claude Code sessions
- [ ] Consider integrating `watchfiles` library for more reliable file watching
- [ ] Expand EventStreamWidget test coverage
- [ ] Performance optimization for high-volume events

## License

See LICENSE file for details.

## Contributing

Contributions welcome! Please follow the development workflow:
1. Write tests first (TDD)
2. Implement to pass tests
3. Ensure 80%+ coverage
4. Create PR with comprehensive test plan
