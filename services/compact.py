"""Compactor 协议的最小实现（三层上下文防御的事前/事后策略，P2）。

- estimate：字符/4 启发式（tokenizer 无关的保守估算）
- microcompact：保留首条 + 最近 keep_last 条消息；窗口外的 tool_result 正文
  替换为占位（保留结构，模型知道有工具发生过）
- summarize：旁路小模型把窗口外历史压成摘要（carryover 已在 SessionState，
  由 gateway 记账，天然存活于压缩）
"""

from __future__ import annotations

from typing import Any, Callable

from state.session_state import SessionState
from engine.messages import PlatformMessage, TextBlock
from api.protocol import SupportsStreamingMessages
from api.usage import UsageSnapshot

_CHARS_PER_TOKEN = 4
_SUMMARY_MAX_CHARS = 2_000


class BasicCompactor:
    def __init__(
        self,
        chat: SupportsStreamingMessages,
        model: str,
        *,
        keep_last: int = 6,
        summarize_model: str | None = None,
    ) -> None:
        self._chat = chat
        self._model = model
        self._summarize_model = summarize_model or model
        self._keep_last = keep_last

    def estimate(self, messages: list[PlatformMessage], state: SessionState) -> int:
        total = sum(len(m.text) + 32 * len(m.tool_calls) + 64 * len(m.images) for m in messages)
        return total // _CHARS_PER_TOKEN

    def microcompact(
        self, messages: list[PlatformMessage], state: SessionState
    ) -> list[PlatformMessage] | None:
        """窗口外 tool_result 正文清空；无收益返回 None。"""
        if len(messages) <= self._keep_last + 1:
            return None
        cut = len(messages) - self._keep_last
        changed = False
        new_messages: list[PlatformMessage] = []
        for idx, message in enumerate(messages):
            if idx == 0 or idx >= cut:
                new_messages.append(message)
                continue
            results = message.tool_results
            if not results:
                new_messages.append(message)
                continue
            content = [
                type(block)(**{**block.model_dump(), "content": "[tool result compacted]"})
                if hasattr(block, "content") and hasattr(block, "tool_use_id")
                else block
                for block in message.content
            ]
            changed = True
            new_messages.append(message.model_copy(update={"content": content}))
        return new_messages if changed else None

    async def summarize(
        self,
        messages: list[PlatformMessage],
        state: SessionState,
        emit: Callable[[Any], None],
    ) -> list[PlatformMessage] | None:
        """旁路模型摘要：窗口外历史 → 一段摘要文本（作为 user 注入消息）。"""
        cut = max(1, len(messages) - self._keep_last)
        older = messages[:cut]
        transcript = "\n".join(
            f"[{m.role}] {m.text[:400]}" + (f" (tools: {len(m.tool_calls)})" if m.tool_calls else "")
            for m in older
        )[:_SUMMARY_MAX_CHARS]
        from api.protocol import ApiMessageCompleteEvent, ApiMessageRequest

        request = ApiMessageRequest(
            model=self._summarize_model,
            messages=[
                PlatformMessage.user(
                    "Summarize the conversation so far for continuation. "
                    "Keep goals, key file paths, decisions and pending steps.\n\n"
                    f"TRANSCRIPT:\n{transcript}"
                )
            ],
            system_prompt="You compress agent conversation history. Output the summary only.",
            max_tokens=1024,
        )
        summary_text = ""
        try:
            async for event in self._chat.stream_message(request):
                if isinstance(event, ApiMessageCompleteEvent):
                    summary_text = event.message.text
        except Exception:  # noqa: BLE001 — 摘要失败则不压缩（引擎会再试 microcompact/反应式）
            return None
        if not summary_text.strip():
            return None
        return [
            PlatformMessage(
                role="user",
                content=[TextBlock(text=f"[conversation summary]\n{summary_text}")],
            )
        ]
