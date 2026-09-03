"""recover 节点：max_tokens 动态钳制的重试路径（不耗业务轮次）。

clamp_retry：agent 已把解析出的厂商上限写回 effective_max_tokens，本节点发提示、
复位 route，路由回 agent——对应 OpenHarness `turn_count -= 1; continue` 的图语义。
reactive_compact 透传给 compact 节点处理。
"""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from engine.stream_events import StatusNotice, emitter
from engine.types import AgentState


async def recover_node(state: AgentState, config: RunnableConfig) -> dict:
    if state.get("route") == "clamp_retry":
        emitter(config)(
            StatusNotice(
                message=(
                    f"Model rejected the requested max_tokens; "
                    f"retrying with provider limit {state['effective_max_tokens']}."
                )
            )
        )
        return {"route": "proceed"}
    return {}
