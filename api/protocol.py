"""统一客户端协议（内核契约面，与 OpenHarness api/client.py 同源语义）。

api 内核搬迁后必须满足本模块定义的 SupportsStreamingMessages；
引擎节点只依赖这里，不 import 任何具体供应商客户端。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol, Union

from engine.messages import PlatformMessage
from api.usage import UsageSnapshot


@dataclass(frozen=True)
class ApiMessageRequest:
    model: str
    messages: list[PlatformMessage]
    system_prompt: str | None = None
    max_tokens: int = 4096
    tools: list[dict[str, Any]] = field(default_factory=list)  # Anthropic 格式 {name, description, input_schema}
    effort: str | None = None


@dataclass(frozen=True)
class ApiTextDeltaEvent:
    text: str


@dataclass(frozen=True)
class ApiMessageCompleteEvent:
    message: PlatformMessage
    usage: UsageSnapshot
    stop_reason: str | None = None


@dataclass(frozen=True)
class ApiRetryEvent:
    message: str
    attempt: int
    max_attempts: int
    delay_seconds: float


ApiStreamEvent = Union[ApiTextDeltaEvent, ApiMessageCompleteEvent, ApiRetryEvent]


class SupportsStreamingMessages(Protocol):
    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        """Yield streamed events for the request."""
