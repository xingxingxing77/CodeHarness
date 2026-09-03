"""preprocess 节点：非视觉模型的图片降级（并发图转文，原地替换内容块）。

来源语义 run_query L568。缺 vision 通道或模型本身支持视觉则整段跳过。
"""
from __future__ import annotations

import asyncio
import logging

from langchain_core.runnables import RunnableConfig

from engine.deps import deps_from
from engine.stream_events import StatusNotice, emitter
from engine.types import AgentState, ReplaceMessages
from engine.messages import PlatformMessage, TextBlock

log = logging.getLogger(__name__)


async def preprocess_node(state: AgentState, config: RunnableConfig) -> dict:
    deps = deps_from(config)
    if deps.vision is None or deps.vision.supports(deps.cfg.model):
        return {}

    pending = [
        (msg_idx, blk_idx, block)
        for msg_idx, msg in enumerate(state["messages"])
        if msg.role == "user"
        for blk_idx, block in msg.images
    ]
    if not pending:
        return {}

    emitter(config)(StatusNotice(message="Converting image to text description via vision model…"))

    async def _describe(msg_idx: int, blk_idx: int, block) -> tuple[int, int, TextBlock]:
        try:
            return msg_idx, blk_idx, TextBlock(text=await deps.vision.describe(block))  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 — 单图失败不拖垮整批
            log.warning("image describe failed msg=%d blk=%d: %s", msg_idx, blk_idx, exc)
            return msg_idx, blk_idx, TextBlock(text=f"[Image: could not describe — {exc}]")

    results = await asyncio.gather(*[_describe(*p) for p in pending])

    new_messages: list[PlatformMessage] = [m.model_copy(deep=True) for m in state["messages"]]
    for msg_idx, blk_idx, text_block in results:
        new_messages[msg_idx].content[blk_idx] = text_block
    return {"messages": ReplaceMessages(new_messages)}
