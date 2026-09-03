"""swarm/ + coordinator/ + tasks/：多智能体最小骨架（P4）。

M-完成范围：任务表持久化（tasks 表）+ 队友 spawn（复用现有引擎：
队友 = 带 teammate system prompt 的普通 run，跑在同一会话机制上）。
信箱 / Send 并行 / 子图编排 → 后续迭代（见 docs/设计计划 P4）。
"""

from __future__ import annotations

TASKS_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id),
    session_id  uuid NOT NULL REFERENCES sessions(id),
    parent_run_id uuid,
    agent_name  text NOT NULL DEFAULT 'teammate',
    description text NOT NULL DEFAULT '',
    status      text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
    result      jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id, created_at DESC);
"""


class PgTaskStore:
    """任务表存取（多智能体队友任务）。"""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def create(self, tenant_id, session_id: str, description: str, *, agent_name: str = "teammate", parent_run_id: str | None = None) -> str:
        import uuid as _uuid

        return str(await self._pool.fetchval(
            "INSERT INTO tasks (tenant_id, session_id, parent_run_id, agent_name, description)"
            " VALUES ($1,$2,$3,$4,$5) RETURNING id",
            _uuid.UUID(tenant_id), _uuid.UUID(session_id),
            _uuid.UUID(parent_run_id) if parent_run_id else None,
            agent_name, description,
        ))

    async def list(self, session_id: str) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT id::text, agent_name, description, status, created_at FROM tasks"
            " WHERE session_id = $1 ORDER BY created_at DESC",
            _uuid.UUID(session_id),
        )
        return [dict(r) | {"created_at": r["created_at"].isoformat()} for r in rows]

    async def set_status(self, task_id: str, status: str, result: dict | None = None) -> None:
        import uuid as _uuid

        await self._pool.execute(
            "UPDATE tasks SET status = $2, result = $3::jsonb, finished_at = now() WHERE id = $1",
            _uuid.UUID(task_id), status,
            __import__("json").dumps(result) if result else None,
        )
