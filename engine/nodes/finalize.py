"""finalize 节点：STOP 类策略 hook + run_finished 事件。

循环收敛的唯一正常出口（tool_calls 为空 / fail 路径也汇入此节点发终态）。
"""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from engine.deps import deps_from
from engine.stream_events import RunFinished, emitter
from engine.types import AgentState, RunOutcome, last_assistant


async def finalize_node(state: AgentState, config: RunnableConfig) -> dict:
    deps = deps_from(config)
    last = last_assistant(state)
    stop_hint = last.metadata.get("stop_reason") if last else None

    outcome = RunOutcome(
        turns=state["turn"],
        usage_total=state["usage_total"],
        stop_reason_hint=stop_hint,
        error=state.get("error"),
    )
    await deps.policy.post_run(outcome)
    emitter(config)(
        RunFinished(
            usage_total=outcome.usage_total,
            stop_reason_hint=stop_hint,
            error=outcome.error,
        )
    )
    return {}
