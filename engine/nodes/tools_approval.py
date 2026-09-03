"""tools_approval 节点：图内唯一 interrupt 挂起点（S3）。

拆独立节点的原因：interrupt 恢复会重跑整个节点——本节点重放只幂等建单+读决策，
真副作用全部在下游 execute 节点。决策未覆盖的调用 fail-closed 按拒绝处理。
"""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from engine.deps import deps_from, run_scope
from engine.types import AgentState
from permissions.approval import payload_for
from tools.base import ApprovalDecision
from tools.base import PreparedCall, ToolPlan, ToolResult



def _apply_decision(plan: ToolPlan, decision: ApprovalDecision) -> ToolPlan:
    choices = {c.call_id: c for c in decision.choices}
    approved: list[PreparedCall] = []
    denied: list[ToolResult] = []
    for pc in plan.need_approval:
        choice = choices.get(pc.call.id)
        if choice is not None and choice.approve:
            approved.append(pc)
        else:
            reason = choice.reason if (choice is not None and choice.reason) else "approval denied or expired"
            denied.append(
                ToolResult(
                    tool_use_id=pc.call.id,
                    content=f"Permission denied for {pc.call.name}: {reason}",
                    is_error=True,
                    metadata={"tool_name": pc.call.name},
                )
            )
    plan.auto_run = plan.auto_run + approved
    plan.refused = plan.refused + denied
    plan.need_approval = []
    return plan


async def tools_approval_node(state: AgentState, config: RunnableConfig) -> dict:
    plan = state.get("pending_plan")
    if plan is None or not plan.need_approval:
        return {}
    deps = deps_from(config)
    _, _, run_id = run_scope(config)
    ticket_id = deps.approvals.ensure_ticket(plan, run_id)  # 幂等：重放返回同一工单
    payload = payload_for(ticket_id, plan, run_id=run_id)
    raw = interrupt(payload.model_dump())
    decision = ApprovalDecision.model_validate(raw)
    return {"pending_plan": _apply_decision(plan, decision)}
