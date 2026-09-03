"""tools_prepare 节点：网关闸门①②③（纯检查、无副作用、可重放）。

产出 ToolPlan 三段清单；refused 已是终态回执，由 execute 出口统一装配。
"""
from __future__ import annotations


from langchain_core.runnables import RunnableConfig

from engine.deps import build_exec_ctx, deps_from
from engine.types import AgentState, last_assistant
from tools.base import ToolCall



async def tools_prepare_node(state: AgentState, config: RunnableConfig) -> dict:
    deps = deps_from(config)
    last = last_assistant(state)
    calls = [
        ToolCall(id=b.id, name=b.name, input=dict(b.input))
        for b in (last.tool_calls if last else [])
    ]
    if not calls:
        return {"pending_plan": None}
    ctx = build_exec_ctx(config, state)
    plan = await deps.gateway.plan(calls, ctx)
    plan.order = calls  # 出口按原始顺序装配回执（I-A3）
    return {"pending_plan": plan}
