from __future__ import annotations

from hud.colors import SPAN_COLORS
from hud.models import ToolEvent, AgentEvent, SkillEvent, StopEvent

_SUMMARY_KEYS: dict[str, list[str]] = {
    "Read": ["file_path"],
    "Bash": ["command"],
    "Edit": ["file_path"],
    "Write": ["file_path"],
    "Grep": ["pattern", "path"],
    "Glob": ["pattern"],
    "Agent": ["description"],
    "Skill": ["skill"],
}

# Keys whose values are file/directory paths (candidates for relativization)
_PATH_KEYS: frozenset[str] = frozenset({"file_path", "path"})


def rel_path(value: str, cwd: str) -> str:
    """Return a path relative to cwd if value is absolute and under cwd, else return value unchanged."""
    if not cwd or not value.startswith("/"):
        return value
    cwd_with_sep = cwd.rstrip("/") + "/"
    if value.startswith(cwd_with_sep):
        return value[len(cwd_with_sep):]
    if value == cwd.rstrip("/"):
        return "."
    return value


def _extract_summary(tool_name: str, tool_input: dict, cwd: str = "") -> str:
    keys = _SUMMARY_KEYS.get(tool_name, [])
    parts = []
    for k in keys:
        if k not in tool_input:
            continue
        v = str(tool_input[k])
        if k in _PATH_KEYS:
            v = rel_path(v, cwd)
        parts.append(v)
    text = " ".join(parts) if parts else str(tool_input)
    return text[:60]


def _extract_tokens(raw: dict) -> tuple[int | None, int | None]:
    usage = raw.get("usage") or raw.get("token_usage") or {}
    inp = usage.get("input_tokens") or usage.get("prompt_tokens")
    out = usage.get("output_tokens") or usage.get("completion_tokens")
    return (int(inp) if inp is not None else None,
            int(out) if out is not None else None)


class EventParser:
    def __init__(self) -> None:
        self._pending: dict[tuple[str, str], float] = {}
        # Each entry: (label, tool_name, span_id, root_color)
        self._context_stack: list[tuple[str, str, int, str]] = []
        # Track pre-phase timestamps for Agent/Skill duration calculation
        self._agent_pre_ts: list[float] = []
        self._skill_pre_ts: list[float] = []
        self._next_span_id: int = 0
        self._top_level_span_count: int = 0  # drives palette index for top-level agents

    def _current_depth(self) -> int:
        return len(self._context_stack)

    def _current_label(self) -> str | None:
        return self._context_stack[-1][0] if self._context_stack else None

    def _pop_context(self, tool_name: str) -> None:
        for i in range(len(self._context_stack) - 1, -1, -1):
            if self._context_stack[i][1] == tool_name:
                self._context_stack.pop(i)
                break

    def _current_span_info(self) -> tuple[int, str] | tuple[None, None]:
        """Return (span_id, root_color) from stack top, or (None, None) if empty."""
        if self._context_stack:
            _, _, span_id, root_color = self._context_stack[-1]
            return span_id, root_color
        return None, None

    def parse(self, raw: dict) -> ToolEvent | AgentEvent | SkillEvent | StopEvent:
        hook_type = raw.get("hook_type", "")
        session_id = raw.get("session_id", "")
        ts = raw.get("ts", 0.0)

        if hook_type == "stop":
            return StopEvent(
                session_id=session_id,
                transcript_path=raw.get("transcript_path"),
                ts=ts,
            )

        tool_name = raw.get("tool_name", "")
        tool_input = raw.get("tool_input", {})
        cwd = raw.get("cwd", "")

        # Agent pre: record in context stack, return AgentEvent at current depth
        if hook_type == "pre" and tool_name == "Agent":
            depth = self._current_depth()
            label = f"agent:{str(tool_input.get('description', ''))[:20]}"
            # Allocate span: top-level gets new palette color, child inherits parent
            self._next_span_id += 1
            span_id = self._next_span_id
            if self._context_stack:
                _, _, _, root_color = self._context_stack[-1]  # inherit parent
            else:
                root_color = SPAN_COLORS[self._top_level_span_count % len(SPAN_COLORS)]
                self._top_level_span_count += 1
            self._context_stack.append((label, "Agent", span_id, root_color))
            self._agent_pre_ts.append(ts)
            return AgentEvent(
                session_id=session_id,
                child_description=str(tool_input.get("description", ""))[:60],
                ts=ts,
                depth=depth,
                phase="pre",
                span_id=span_id,
                span_color=root_color,
            )

        # Skill pre: record in context stack, return SkillEvent at current depth
        if hook_type == "pre" and tool_name == "Skill":
            depth = self._current_depth()
            label = f"skill:{str(tool_input.get('skill', ''))}"
            self._next_span_id += 1
            span_id = self._next_span_id
            if self._context_stack:
                _, _, _, root_color = self._context_stack[-1]
            else:
                root_color = SPAN_COLORS[self._top_level_span_count % len(SPAN_COLORS)]
                self._top_level_span_count += 1
            self._context_stack.append((label, "Skill", span_id, root_color))
            self._skill_pre_ts.append(ts)
            return SkillEvent(
                session_id=session_id,
                skill_name=str(tool_input.get("skill", "")),
                ts=ts,
                depth=depth,
                phase="pre",
                span_id=span_id,
                span_color=root_color,
            )

        # Agent post: pop context stack, return AgentEvent with duration
        if hook_type == "post" and tool_name == "Agent":
            span_id, span_color = self._current_span_info()
            self._pop_context("Agent")
            pre_ts = self._agent_pre_ts.pop() if self._agent_pre_ts else None
            duration_ms = int((ts - pre_ts) * 1000) if pre_ts is not None else None
            return AgentEvent(
                session_id=session_id,
                child_description=str(tool_input.get("description", ""))[:60],
                ts=ts,
                depth=self._current_depth(),
                phase="post",
                duration_ms=duration_ms,
                span_id=span_id,
                span_color=span_color,
            )

        # Skill post: pop context stack, return SkillEvent with duration
        if hook_type == "post" and tool_name == "Skill":
            span_id, span_color = self._current_span_info()
            self._pop_context("Skill")
            pre_ts = self._skill_pre_ts.pop() if self._skill_pre_ts else None
            duration_ms = int((ts - pre_ts) * 1000) if pre_ts is not None else None
            return SkillEvent(
                session_id=session_id,
                skill_name=str(tool_input.get("skill", "")),
                ts=ts,
                depth=self._current_depth(),
                phase="post",
                duration_ms=duration_ms,
                span_id=span_id,
                span_color=span_color,
            )

        span_id, span_color = self._current_span_info()
        key = (session_id, tool_name)
        depth = self._current_depth()
        label = self._current_label()

        if hook_type == "pre":
            self._pending[key] = ts
            return ToolEvent(
                session_id=session_id,
                tool_name=tool_name,
                input_summary=_extract_summary(tool_name, tool_input, cwd),
                ts=ts,
                phase="pre",
                depth=depth,
                context_label=label,
                span_id=span_id,
                span_color=span_color,
            )

        pre_ts = self._pending.pop(key, None)
        duration_ms = int((ts - pre_ts) * 1000) if pre_ts is not None else None
        tool_output = raw.get("tool_response") or raw.get("tool_output") or {}
        error_text = tool_output.get("error") or tool_output.get("stderr") or ""
        success = not bool(error_text)
        error_excerpt = error_text[:80] if error_text else None
        input_tokens, output_tokens = _extract_tokens(raw)

        return ToolEvent(
            session_id=session_id,
            tool_name=tool_name,
            input_summary=_extract_summary(tool_name, tool_input, cwd),
            ts=ts,
            phase="post",
            success=success,
            duration_ms=duration_ms,
            error_excerpt=error_excerpt,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            depth=depth,
            context_label=label,
            span_id=span_id,
            span_color=span_color,
        )
