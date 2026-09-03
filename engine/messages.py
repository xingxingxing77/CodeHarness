"""契约①会话/消息模型（Anthropic 风格内容块血统，内核"内部普通话"）。

四接触面对齐内核（api/ 各客户端）所需：to_api_param / serialize_content_block /
from_api_response / reasoning 回放字段；另移植 sanitize_conversation_messages
用于恢复历史会话时修剪坏尾巴。
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImageBlock(BaseModel):
    type: Literal["image"] = "image"
    media_type: str
    data: str  # base64


class ToolCallBlock(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str = Field(default_factory=lambda: f"toolu_{uuid4().hex}")
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str
    is_error: bool = False


ContentBlock = Annotated[
    Union[TextBlock, ImageBlock, ToolCallBlock, ToolResultBlock],
    Field(discriminator="type"),
]


class PlatformMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: list[ContentBlock] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # thinking 模型的 reasoning 回放（api/openai_client 收集与回传）；
    # exclude=True：不进 checkpoint / messages 表 / SSE
    reasoning: str | None = Field(default=None, exclude=True)

    @property
    def text(self) -> str:
        return "".join(b.text for b in self.content if isinstance(b, TextBlock))

    @property
    def tool_calls(self) -> list[ToolCallBlock]:
        return [b for b in self.content if isinstance(b, ToolCallBlock)]

    @property
    def tool_results(self) -> list[ToolResultBlock]:
        return [b for b in self.content if isinstance(b, ToolResultBlock)]

    @property
    def images(self) -> list[tuple[int, ImageBlock]]:
        return [(i, b) for i, b in enumerate(self.content) if isinstance(b, ImageBlock)]

    def is_effectively_empty(self) -> bool:
        return not self.text.strip() and not self.tool_calls and not self.tool_results

    @classmethod
    def user(cls, text: str) -> "PlatformMessage":
        return cls(role="user", content=[TextBlock(text=text)])

    @classmethod
    def assistant(cls, text: str) -> "PlatformMessage":
        return cls(role="assistant", content=[TextBlock(text=text)])

    # ------------------------------------------------------------------
    # 内核接触面（对齐供体 ConversationMessage，api/ 各客户端依赖）
    # ------------------------------------------------------------------

    def to_api_param(self) -> dict[str, Any]:
        """Anthropic SDK 消息参数格式。"""
        return {
            "role": self.role,
            "content": [serialize_content_block(b) for b in self.content],
        }

    @classmethod
    def from_api_response(cls, raw_message: Any) -> "PlatformMessage":
        """Anthropic SDK 终态消息对象 → PlatformMessage（text / tool_use 两类块）。"""
        content: list[ContentBlock] = []
        for raw_block in getattr(raw_message, "content", []):
            block_type = getattr(raw_block, "type", None)
            if block_type == "text":
                content.append(TextBlock(text=getattr(raw_block, "text", "")))
            elif block_type == "tool_use":
                content.append(
                    ToolCallBlock(
                        id=getattr(raw_block, "id", f"toolu_{uuid4().hex}"),
                        name=getattr(raw_block, "name", ""),
                        input=dict(getattr(raw_block, "input", {}) or {}),
                    )
                )
        return cls(role="assistant", content=content)


def serialize_content_block(block: ContentBlock) -> dict[str, Any]:
    """本地内容块 → provider 线上格式。"""
    if isinstance(block, TextBlock):
        return {"type": "text", "text": block.text}
    if isinstance(block, ImageBlock):
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": block.media_type, "data": block.data},
        }
    if isinstance(block, ToolCallBlock):
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return {
        "type": "tool_result",
        "tool_use_id": block.tool_use_id,
        "content": block.content,
        "is_error": block.is_error,
    }


def sanitize_conversation_messages(messages: list[PlatformMessage]) -> list[PlatformMessage]:
    """恢复历史会话的规整：丢空 assistant 消息、修剪没等到 tool_result 的尾部 tool_call 轮次。

    坏尾巴会让 OpenAI 兼容接口拒绝恢复的会话（悬空 tool_use）。
    """
    sanitized: list[PlatformMessage] = []
    pending_ids: set[str] = set()
    pending_index: int | None = None

    for message in messages:
        if message.role == "assistant" and message.is_effectively_empty():
            continue

        calls = message.tool_calls if message.role == "assistant" else []
        results = message.tool_results if message.role == "user" else []

        matched = False
        if pending_ids:
            result_ids = {b.tool_use_id for b in results}
            if message.role != "user" or not pending_ids.issubset(result_ids):
                if pending_index is not None and pending_index < len(sanitized):
                    sanitized.pop(pending_index)
                pending_ids, pending_index = set(), None
            else:
                matched = True
                pending_ids, pending_index = set(), None

        if message.role == "user" and results and not matched:
            content = [b for b in message.content if not isinstance(b, ToolResultBlock)]
            if not content:
                continue
            message = PlatformMessage(role="user", content=content)

        sanitized.append(message)

        if calls:
            pending_ids = {b.id for b in calls}
            pending_index = len(sanitized) - 1

    if pending_ids and pending_index is not None and pending_index < len(sanitized):
        sanitized.pop(pending_index)

    return sanitized
