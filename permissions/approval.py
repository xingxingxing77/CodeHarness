"""审批工单（实现计划 6.4）：interrupt 的持久化载体。

幂等键 = hash(run_id, sorted(call_ids))，节点重放不重复建单；
TTL 到期未决按 expired 处理（调用方以 deny 恢复图，run 永不无限挂起）；
决策即写单，任意进程可据此构造 Command(resume) 续跑。
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from tools.base import ApprovalItem, ApprovalPayload, ToolPlan

DEFAULT_TTL_SECONDS = 30 * 60
PREVIEW_CHARS = 200

TicketStatus = Literal["pending", "decided", "expired"]


def ticket_key(run_id: str, plan: ToolPlan) -> str:
    ids = ",".join(sorted(pc.call.id for pc in plan.need_approval))
    digest = hashlib.sha256(f"{run_id}|{ids}".encode()).hexdigest()[:16]
    return f"ap-{digest}"


def payload_for(ticket_id: str, plan: ToolPlan, run_id: str = "") -> ApprovalPayload:
    return ApprovalPayload(
        ticket_id=ticket_id,
        run_id=run_id,
        items=[
            ApprovalItem(
                call_id=pc.call.id,
                tool_name=pc.call.name,
                reason=pc.decision.reason,
                risk_level=pc.decision.risk_level,
                input_preview=json.dumps(pc.call.input, ensure_ascii=False, default=str)[:PREVIEW_CHARS],
            )
            for pc in plan.need_approval
        ],
    )


@dataclass
class ApprovalTicket:
    ticket_id: str
    run_id: str
    items: list[ApprovalItem] = field(default_factory=list)
    status: TicketStatus = "pending"
    decision: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    decided_at: float | None = None
    decided_by: str | None = None

    def is_expired(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return self.status == "pending" and now > self.expires_at


class ApprovalService:
    """ApprovalStore 协议的进程内实现：幂等建单 + 决策记录 + TTL。

    生产形态为 Postgres approvals 表 + Redis approval:{session} 列表，接口面不变。
    """

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS, clock=time.time) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._by_id: dict[str, ApprovalTicket] = {}

    def ensure_ticket(self, plan: ToolPlan, run_id: str) -> str:
        key = ticket_key(run_id, plan)
        existing = self._by_id.get(key)
        now = self._clock()
        if existing is not None:
            if existing.status == "decided":
                return existing.ticket_id  # 重放读旧决策
            if existing.status == "pending" and not existing.is_expired(now):
                return existing.ticket_id
        ticket = ApprovalTicket(
            ticket_id=key,
            run_id=run_id,
            items=[i.model_copy() for i in payload_for(key, plan, run_id=run_id).items],
            created_at=now,
            expires_at=now + self._ttl,
        )
        self._by_id[key] = ticket
        return ticket.ticket_id

    def get(self, ticket_id: str) -> ApprovalTicket | None:
        ticket = self._by_id.get(ticket_id)
        if ticket is not None and ticket.is_expired():
            ticket.status = "expired"
        return ticket

    def pending(self) -> list[ApprovalTicket]:
        """待审批工单（审批中心数据源；过期即 expired）。"""
        now = self._clock()
        out: list[ApprovalTicket] = []
        for ticket in self._by_id.values():
            if ticket.status == "pending" and ticket.is_expired(now):
                ticket.status = "expired"
            if ticket.status == "pending":
                out.append(ticket)
        return sorted(out, key=lambda t: t.created_at)

    def decide(
        self, ticket_id: str, decision: ApprovalDecision, decided_by: str = ""
    ) -> ApprovalTicket:
        ticket = self._by_id.get(ticket_id)
        if ticket is None:
            raise KeyError(f"unknown ticket: {ticket_id}")
        if ticket.status == "decided":
            return ticket  # 幂等：重复决策不覆盖
        if ticket.is_expired():
            ticket.status = "expired"
            return ticket
        ticket.status = "decided"
        ticket.decision = decision.model_dump()
        ticket.decided_at = self._clock()
        ticket.decided_by = decided_by
        return ticket
