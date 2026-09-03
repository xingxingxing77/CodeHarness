"""图内自定义事件（节点 → 事件泵），由第五节的 events 翻译表映射为平台 SSE 事件。

emitter() 在图内走 LangGraph custom stream writer；图外（单测/直调节点）
回退到 config.configurable.event_sink，保证节点可脱离图独立驱动。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from tools.base import UiPayload
from engine.types import PlatformError


@dataclass(frozen=True)
class AssistantDelta:
    text: str


@dataclass(frozen=True)
class StatusNotice:
    message: str


@dataclass(frozen=True)
class CompactProgress:
    stage: str
    detail: str = ""


@dataclass(frozen=True)
class ToolStarted:
    tool_name: str
    tool_input: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCompleted:
    tool_name: str
    output: str
    is_error: bool
    ui: UiPayload | None = None


@dataclass(frozen=True)
class RunFinished:
    usage_total: Any
    stop_reason_hint: str | None
    error: PlatformError | None


def emitter(config: RunnableConfig | None) -> Callable[[Any], None]:
    try:
        from langgraph.config import get_stream_writer

        return get_stream_writer()
    except Exception:
        configurable = dict((config or {}).get("configurable") or {})
        sink = configurable.get("event_sink")
        if callable(sink):
            return sink
        return lambda event: None


# ---------------------------------------------------------------------------
# SSE 契约④（平台自定义，框架类型不越过此边界）
# ---------------------------------------------------------------------------

SSE_EVENT_TYPES = (
    "assistant_delta",
    "assistant_turn_complete",
    "tool_started",
    "tool_completed",
    "compact_progress",
    "approval_required",
    "status",
    "error",
    "run_finished",
)


class SSEEvent(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


def _error_payload(error: PlatformError | None) -> dict[str, Any] | None:
    return None if error is None else {"code": error.code, "message": error.message}


def translate(event: Any) -> SSEEvent | None:
    """图内事件 → SSE 契约④；approval_required 由 runner 从 __interrupt__ 构造，不经此处。"""
    if isinstance(event, AssistantDelta):
        return SSEEvent(type="assistant_delta", payload={"text": event.text})
    if isinstance(event, StatusNotice):
        return SSEEvent(type="status", payload={"message": event.message})
    if isinstance(event, CompactProgress):
        return SSEEvent(type="compact_progress", payload={"stage": event.stage, "detail": event.detail})
    if isinstance(event, ToolStarted):
        return SSEEvent(type="tool_started", payload={"tool_name": event.tool_name, "tool_input": event.tool_input})
    if isinstance(event, ToolCompleted):
        return SSEEvent(
            type="tool_completed",
            payload={
                "tool_name": event.tool_name,
                "output": event.output,
                "is_error": event.is_error,
                "ui": (
                    {"kind": event.ui.kind, "data": event.ui.data}
                    if event.ui is not None
                    else None
                ),
            },
        )
    if isinstance(event, RunFinished):
        usage = event.usage_total
        return SSEEvent(
            type="run_finished",
            payload={
                "usage": {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "stop_reason_hint": event.stop_reason_hint,
                "error": _error_payload(event.error),
            },
        )
    return None
