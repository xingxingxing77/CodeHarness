"""compact 节点：三层防御的事前层（trigger=auto）与事后层（route=reactive_compact, force）。

压缩结果不回写 messages 表——表是原始事实，压缩是 run 内视图（I-A2 派生决策）。
反应式压缩全程仅一次：route 进入即置 reactive_compact_done，第二次超长由路由函数直接 fail。
"""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from engine.deps import deps_from
from engine.stream_events import CompactProgress, emitter
from engine.types import AgentState, ReplaceMessages


async def compact_node(state: AgentState, config: RunnableConfig) -> dict:
    deps = deps_from(config)
    cfg = deps.cfg
    emit = emitter(config)
    reactive = state.get("route") == "reactive_compact"

    update: dict = {}
    if reactive:
        update.update({"reactive_compact_done": True, "route": "proceed"})

    threshold = cfg.auto_compact_threshold_tokens
    est = deps.compactor.estimate(state["messages"], state["session_state"])
    if not reactive and (threshold is None or est < threshold):
        return update

    emit(
        CompactProgress(
            stage="start",
            detail=f"estimated_tokens={est} trigger={'reactive' if reactive else 'auto'}",
        )
    )
    replaced = deps.compactor.microcompact(list(state["messages"]), state["session_state"])
    if replaced is None:
        replaced = await deps.compactor.summarize(state["messages"], state["session_state"], emit)
    if replaced is not None:
        update["messages"] = ReplaceMessages(replaced)
    emit(CompactProgress(stage="done", detail=f"compacted={replaced is not None}"))
    return update
