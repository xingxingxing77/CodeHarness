"""tools_execute 节点：网关闸门⑤+收尾ABC 的唯一副作用入口，之后打包工具回执消息。

无 interrupt、无挂起能力（S3）；出口按 plan.order 装配全部回执（I-A3/I-B2），
对缺失回执做防御性兜底——网关契约被违反也不破坏协议闭环。
"""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from engine.deps import build_exec_ctx, deps_from
from engine.stream_events import ToolCompleted, ToolStarted, emitter
from engine.types import AgentState
from tools.base import ToolResult
from engine.messages import PlatformMessage, ToolResultBlock


async def tools_execute_node(state: AgentState, config: RunnableConfig) -> dict:
    plan = state.get("pending_plan")
    if plan is None:
        return {}
    deps = deps_from(config)
    emit = emitter(config)
    ctx = build_exec_ctx(config, state)

    for pc in plan.auto_run:
        emit(ToolStarted(tool_name=pc.call.name, tool_input=dict(pc.call.input)))

    batch = await deps.gateway.run(plan, ctx)  # I-B1：永不 raise

    by_id = {r.tool_use_id: r for r in batch.results}
    for pc in plan.auto_run:
        r = by_id.get(pc.call.id)
        if r is not None:
            emit(ToolCompleted(tool_name=pc.call.name, output=r.content, is_error=r.is_error, ui=r.ui))
    for r in plan.refused:
        emit(
            ToolCompleted(
                tool_name=str(r.metadata.get("tool_name", "?")),
                output=r.content,
                is_error=True,
            )
        )

    merged = {**{r.tool_use_id: r for r in plan.refused}, **by_id}
    blocks: list[ToolResultBlock] = []
    for call in plan.order:
        r = merged.get(call.id)
        if r is None:
            r = ToolResult(
                tool_use_id=call.id,
                content=f"Tool {call.name} produced no result",
                is_error=True,
            )
        blocks.append(ToolResultBlock(tool_use_id=r.tool_use_id, content=r.content, is_error=r.is_error))

    return {
        "messages": [PlatformMessage(role="user", content=blocks)],
        "pending_plan": None,
        "session_state": batch.session_state,
    }
