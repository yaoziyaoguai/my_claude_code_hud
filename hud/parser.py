from __future__ import annotations

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


def _extract_summary(tool_name: str, tool_input: dict) -> str:
    keys = _SUMMARY_KEYS.get(tool_name, [])
    parts = [str(tool_input.get(k, "")) for k in keys if k in tool_input]
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

        if hook_type == "post" and tool_name == "Agent":
            return AgentEvent(
                session_id=session_id,
                child_description=str(tool_input.get("description", ""))[:60],
                ts=ts,
            )

        if hook_type == "post" and tool_name == "Skill":
            return SkillEvent(
                session_id=session_id,
                skill_name=str(tool_input.get("skill", "")),
                ts=ts,
            )

        key = (session_id, tool_name)

        if hook_type == "pre":
            self._pending[key] = ts
            return ToolEvent(
                session_id=session_id,
                tool_name=tool_name,
                input_summary=_extract_summary(tool_name, tool_input),
                ts=ts,
                phase="pre",
            )

        # post
        pre_ts = self._pending.pop(key, None)
        duration_ms = int((ts - pre_ts) * 1000) if pre_ts is not None else None
        tool_output = raw.get("tool_output", {})
        error_text = tool_output.get("error") or tool_output.get("stderr") or ""
        success = not bool(error_text)
        error_excerpt = error_text[:80] if error_text else None
        input_tokens, output_tokens = _extract_tokens(raw)

        return ToolEvent(
            session_id=session_id,
            tool_name=tool_name,
            input_summary=_extract_summary(tool_name, tool_input),
            ts=ts,
            phase="post",
            success=success,
            duration_ms=duration_ms,
            error_excerpt=error_excerpt,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
