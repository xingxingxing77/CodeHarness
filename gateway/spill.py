"""大输出卸载（内置工具规范 §1 / 后端设计 §4 收尾A）。

content 超预算 → 全文落对象存储，回执保留"完整 URI + 预览 + 原始大小"
供模型回读（可恢复引用，不瞎截）；ui 通道不受截断约束。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes) -> str:
        """存储对象并返回可读 URI。"""
        ...


class InMemoryObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> str:
        self.objects[key] = data
        return f"memory://{key}"


@dataclass(frozen=True)
class SpillResult:
    content: str          # 卸载后的模型回执（引用 + 预览）
    uri: str | None       # 完整产物 URI；None = 未卸载


async def spill_if_oversize(
    store: ObjectStore,
    *,
    content: str,
    inline_limit_chars: int,
    preview_chars: int,
    key: str,
) -> SpillResult:
    if len(content) <= inline_limit_chars:
        return SpillResult(content=content, uri=None)

    uri = await store.put(key, content.encode("utf-8"))
    preview = content[:preview_chars]
    omitted = max(0, len(content) - len(preview))
    inline = (
        "[Tool output truncated]\n"
        f"Full output saved to: {uri}\n"
        f"Original size: {len(content)} chars\n"
        f"Inline preview: first {len(preview)} chars ({omitted} chars omitted)\n\n"
        f"Preview:\n{preview}"
    )
    return SpillResult(content=inline, uri=uri)
