from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ToolEvent:
    session_id: str
    tool_name: str
    input_summary: str
    ts: float
    phase: Literal["pre", "post"]
    success: bool | None = None
    duration_ms: int | None = None
    error_excerpt: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class AgentEvent:
    session_id: str
    child_description: str
    ts: float


@dataclass
class SkillEvent:
    session_id: str
    skill_name: str
    ts: float


@dataclass
class StopEvent:
    session_id: str
    transcript_path: str | None
    ts: float
