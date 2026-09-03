"""Mock chat（开发/演示用，无供应商 key 时的确定性脚本）。

脚本：轮1 发起 write_file 工具调用；轮2 流式文本收敛。
让浏览器端到端看到 assistant_delta / tool_started / tool_completed / run_finished。
"""

from __future__ import annotations

from typing import AsyncIterator

from api.protocol import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiStreamEvent,
    ApiTextDeltaEvent,
)
from engine.messages import PlatformMessage, ToolCallBlock
from api.usage import UsageSnapshot


class MockChat:
    """SupportsStreamingMessages 的确定性实现（仅 dev）。"""

    def __init__(self, *, file_name: str = "hello.txt") -> None:
        self._file_name = file_name

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        # 轮1：写一个文件（走真实网关闸门与沙箱）
        has_tool_call = any(m.tool_calls for m in request.messages if m.role == "assistant")
        if not has_tool_call:
            for piece in ("好的，", "我先创建"):
                yield ApiTextDeltaEvent(text=piece)
            yield ApiMessageCompleteEvent(
                message=self._tool_call_message(),
                usage=UsageSnapshot(input_tokens=12, output_tokens=8),
                stop_reason="tool_use",
            )
            return

        # 轮2：文本收敛
        for word in ("Hello from ", "Codeharness! ", "I created ", f"{self._file_name} ", "in your workspace."):
            yield ApiTextDeltaEvent(text=word)
        yield ApiMessageCompleteEvent(
            message=PlatformMessage.assistant(
                f"Hello from Codeharness! I created {self._file_name} in your workspace."
            ),
            usage=UsageSnapshot(input_tokens=6, output_tokens=5),
            stop_reason="end_turn",
        )

    def _tool_call_message(self) -> PlatformMessage:
        return PlatformMessage(
            role="assistant",
            content=[
                ToolCallBlock(
                    id="mock-1",
                    name="write_file",
                    input={"file_path": self._file_name, "content": "hello from codeharness\n"},
                )
            ],
        )
