"""图装配：StateGraph 编排 8 节点（实现计划第四节）。

路由函数保持纯分派——预算熔断与二次压缩防护都在 agent 节点产出时判定（见 nodes/agent.py），
路由只读 route/tool_calls/pending_plan。

checkpointer 线程模型（关键决策）：thread_id = run_id，一次 run 一个线程。
会话历史的事实源是 messages 表，runner 在 run 启动时加载注入初始 state；
checkpointer 只承担 run 内挂起/恢复（审批、崩溃续跑），可丢弃可重建。
"""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from engine.budget import TurnBudget
from engine.deps import deps_from
from engine.nodes import (
    agent_node,
    compact_node,
    finalize_node,
    preprocess_node,
    recover_node,
    tools_approval_node,
    tools_execute_node,
    tools_prepare_node,
)
from utils.serde import platform_serializer
from engine.types import AgentState, last_assistant


def route_after_agent(state: AgentState) -> str:
    route = state.get("route", "proceed")
    if route == "fail":
        return "finalize"
    if route in ("clamp_retry", "reactive_compact"):
        return "recover"
    # 原则 3：收敛只看有无 tool_calls，不看 stop_reason
    last = last_assistant(state)
    if last is not None and last.tool_calls:
        return "tools_prepare"
    return "finalize"


def route_after_prepare(state: AgentState) -> str:
    plan = state.get("pending_plan")
    if plan is not None and plan.need_approval:
        return "tools_approval"
    return "tools_execute"


def route_after_recover(state: AgentState) -> str:
    # clamp_retry 已被 recover 复位为 proceed → 回 agent；
    # reactive_compact 原样透传 → 经 compact(force) 处理
    return "compact" if state.get("route") == "reactive_compact" else "agent"


def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    if checkpointer is not None:
        # 平台类型白名单：checkpoint 反序列化在严格模式下不被阻断
        checkpointer.serde = platform_serializer()
    g = StateGraph(AgentState)
    g.add_node("preprocess", preprocess_node)
    g.add_node("compact", compact_node)
    g.add_node("agent", agent_node)
    g.add_node("tools_prepare", tools_prepare_node)
    g.add_node("tools_approval", tools_approval_node)
    g.add_node("tools_execute", tools_execute_node)
    g.add_node("recover", recover_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "preprocess")
    g.add_edge("preprocess", "compact")
    g.add_edge("compact", "agent")
    g.add_conditional_edges(
        "agent", route_after_agent, ["tools_prepare", "recover", "finalize"]
    )
    g.add_conditional_edges(
        "tools_prepare", route_after_prepare, ["tools_approval", "tools_execute"]
    )
    g.add_edge("tools_approval", "tools_execute")
    g.add_edge("tools_execute", "preprocess")  # 下一轮
    g.add_conditional_edges("recover", route_after_recover, ["agent", "compact"])
    g.add_edge("finalize", END)

    return g.compile(checkpointer=checkpointer)


def with_recursion_limit(config: RunnableConfig, budget: TurnBudget | None = None) -> RunnableConfig:
    """注入 recursion_limit 保险丝（业务轮次权威判定在 agent 节点）。"""
    deps = deps_from(config)
    limit = (budget or TurnBudget(max_turns=deps.cfg.max_turns)).recursion_limit()
    merged = {**config, "recursion_limit": limit}
    return merged  # type: ignore[return-value]


async def run_graph(
    graph: CompiledStateGraph,
    state: AgentState,
    config: RunnableConfig,
    *,
    budget: TurnBudget | None = None,
) -> AgentState:
    """一次 run 的执行入口：recursion_limit 保险丝 + 终态返回。"""
    return await graph.ainvoke(state, with_recursion_limit(config, budget))  # type: ignore[return-value]
