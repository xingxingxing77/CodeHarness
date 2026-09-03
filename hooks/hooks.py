"""hooks 事件总线（后端设计 §7.5，P3）：供体本地 hook 子进程的替换实现。

- 每个生命周期事件：写 Postgres audit_events（持久尾迹）+ Redis Stream hooks:{tenant}
- AuditPolicy 实现 PolicyEngine：pre/post tool use 与 post_run 三处卡点
- 观察者故障不阻断主流程（emit 内部吞错并记日志）
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Protocol

log = logging.getLogger(__name__)


class AuditSink(Protocol):
    async def execute(self, query: str, *args) -> Any: ...


class HooksEventBus:
    """事件总线：audit_events 表（事实尾迹）+ Redis Stream（实时订阅）。"""

    def __init__(self, pool, tenant_id: str, *, redis_client=None) -> None:
        self._pool = pool
        self._tenant = uuid.UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
        self._redis = redis_client

    async def emit(self, kind: str, payload: dict) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO audit_events (tenant_id, kind, payload) VALUES ($1,$2,$3::jsonb)",
                    self._tenant,
                    kind,
                    json.dumps(payload, default=str),
                )
            if self._redis is not None:
                await self._redis.xadd(
                    f"hooks:{self._tenant}",
                    {"event": json.dumps({"kind": kind, "payload": payload}, default=str)},
                    maxlen=10_000,
                    approximate=True,
                )
        except Exception:  # noqa: BLE001 — 观察链路故障不阻断执行
            log.exception("hooks emit failed: %s", kind)

    # -- PolicyEngine 卡点 ---------------------------------------------------

    async def pre_tool_use(self, call, ctx):
        await self.emit("pre_tool_use", {"tool_name": call.name, "tool_input": call.input, "run_id": ctx.run_id})
        return None  # M3：策略裁决接入（当前仅观察）

    async def post_tool_use(self, call, result, ctx):
        await self.emit(
            "post_tool_use",
            {"tool_name": call.name, "is_error": result.is_error, "run_id": ctx.run_id},
        )

    async def post_run(self, outcome) -> None:
        await self.emit(
            "post_run",
            {
                "turns": outcome.turns,
                "usage": outcome.usage_total.model_dump() if hasattr(outcome.usage_total, "model_dump") else str(outcome.usage_total),
                "stop_reason_hint": outcome.stop_reason_hint,
                "error": outcome.error.model_dump() if outcome.error else None,
            },
        )
