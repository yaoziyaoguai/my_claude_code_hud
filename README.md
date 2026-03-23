# Claude HUD

A real-time monitoring sidebar for Claude Code. Watch live tool calls, agent activity, skill activations, and token usage as Claude works—all in a dedicated terminal window.

## Overview

Claude HUD integrates with Claude Code's hooks system to display real-time events without modifying Claude Code itself. Simply run `claude-hud watch` in a separate terminal alongside your normal `claude` session.

**Current Status**: v0.1.0 (28/28 tests passing)

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

- Python 3.10+
- Claude Code installed and configured

### Install Claude HUD

```bash
pip install -e .
```

### Register Hooks with Claude Code

```bash
claude-hud install
```

This modifies `~/.claude/settings.json` to register Claude HUD's hooks.

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

**HUD won't start?**
- Ensure Claude Code session has `CLAUDE_SESSION_ID` environment variable set
- Check that `/tmp/claude-hud/` directory exists and is writable

**No events appearing?**
- Run `claude-hud install` to register hooks
- Verify `~/.claude/settings.json` contains hook configurations
- Check that Claude Code is running in a new session

**Hook not firing?**
- Verify `hook.py` is in the project root
- Check Claude Code log for hook execution errors

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
