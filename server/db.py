"""Postgres 落库层（数据库设计 DDL 的实现面；P2）。

实现 engine/persistence.py 的 MessageStore / SessionStore 协议与 runs 状态机；
messages 表是事实源；checkpoint 可丢弃可重建。
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg

from state.session_state import SessionState
from engine.messages import PlatformMessage
from api.usage import UsageSnapshot
DDL = """
CREATE TABLE IF NOT EXISTS tenants (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    quotas      jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO tenants (id, name)
VALUES ('00000000-0000-0000-0000-000000000001', 'default')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS sessions (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL REFERENCES tenants(id),
    title        text NOT NULL DEFAULT '',
    model        text NOT NULL,
    sandbox_image text,
    archived     boolean NOT NULL DEFAULT false,
    session_state jsonb NOT NULL DEFAULT '{}',
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions(tenant_id, updated_at DESC) WHERE archived = false;

CREATE TABLE IF NOT EXISTS messages (
    id          bigserial PRIMARY KEY,
    session_id  uuid NOT NULL REFERENCES sessions(id),
    run_id      uuid NOT NULL,
    role        text NOT NULL CHECK (role IN ('user','assistant')),
    content     jsonb NOT NULL,
    metadata    jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS runs (
    id          uuid PRIMARY KEY,
    session_id  uuid NOT NULL REFERENCES sessions(id),
    tenant_id   uuid NOT NULL REFERENCES tenants(id),
    kind        text NOT NULL DEFAULT 'new' CHECK (kind IN ('new','resume')),
    status      text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','interrupted','succeeded','failed','cancelled')),
    usage_input  bigint NOT NULL DEFAULT 0,
    usage_output bigint NOT NULL DEFAULT 0,
    error        jsonb,
    max_turns    int NOT NULL DEFAULT 200,
    created_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_active ON runs(session_id) WHERE status IN ('queued','running','interrupted');

CREATE TABLE IF NOT EXISTS approvals (
    ticket_id   text PRIMARY KEY,
    run_id      uuid NOT NULL REFERENCES runs(id),
    session_id  uuid NOT NULL REFERENCES sessions(id),
    items       jsonb NOT NULL,
    status      text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','decided','expired')),
    decision    jsonb,
    decided_by  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    decided_at  timestamptz
);
CREATE INDEX IF NOT EXISTS idx_approvals_pending ON approvals(session_id, created_at DESC) WHERE status = 'pending';
"""

DEFAULT_TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def setup_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)


def _dump_message(m: PlatformMessage) -> tuple[str, str, str]:
    dumped = m.model_dump(mode="json", exclude_none=True)
    return (
        m.role,
        json.dumps(dumped["content"]),
        json.dumps(dumped.get("metadata", {})),
    )


def _load_message(row: asyncpg.Record) -> PlatformMessage:
    return PlatformMessage.model_validate(
        {
            "role": row["role"],
            "content": json.loads(row["content"]),
            "metadata": json.loads(row["metadata"]),
        }
    )


# ---------------------------------------------------------------------------
# 消息（事实源）—— MessageStore 协议
# ---------------------------------------------------------------------------


class PgMessageStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def history(self, session_id: str) -> list[PlatformMessage]:
        rows = await self._pool.fetch(
            "SELECT role, content, metadata FROM messages WHERE session_id = $1 ORDER BY id",
            uuid.UUID(session_id),
        )
        return [_load_message(r) for r in rows]

    async def append(
        self, session_id: str, run_id: str, messages: list[PlatformMessage]
    ) -> None:
        if not messages:
            return
        rows = [
            (uuid.UUID(session_id), uuid.UUID(run_id), *_dump_message(m))
            for m in messages
        ]
        await self._pool.executemany(
            "INSERT INTO messages (session_id, run_id, role, content, metadata)"
            " VALUES ($1,$2,$3,$4::jsonb,$5::jsonb)",
            rows,
        )


# ---------------------------------------------------------------------------
# 会话状态 / run 收尾 —— SessionStore 协议
# ---------------------------------------------------------------------------


class PgSessionStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_state(self, session_id: str) -> SessionState | None:
        raw = await self._pool.fetchval(
            "SELECT session_state FROM sessions WHERE id = $1",
            uuid.UUID(session_id),
        )
        if raw is None:
            return None
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        return SessionState(**data)

    async def update_state(self, session_id: str, state: SessionState) -> None:
        await self._pool.execute(
            "UPDATE sessions SET session_state = $2::jsonb, updated_at = now() WHERE id = $1",
            uuid.UUID(session_id),
            json.dumps(_state_dict(state)),
        )

    async def finish_run(
        self, run_id: str, usage_total: UsageSnapshot, error: dict | None
    ) -> None:
        status = "failed" if error else "succeeded"
        await self._pool.execute(
            "UPDATE runs SET status = $2, usage_input = $3, usage_output = $4,"
            " error = $5::jsonb, finished_at = now() WHERE id = $1",
            uuid.UUID(run_id),
            status,
            usage_total.input_tokens,
            usage_total.output_tokens,
            json.dumps(error) if error else None,
        )

    # -- 会话与 run 的创建/查询（REST 层用） ---------------------------------

    async def create_session(
        self, model: str, title: str = "", tenant_id: uuid.UUID = DEFAULT_TENANT
    ) -> str:
        sid = await self._pool.fetchval(
            "INSERT INTO sessions (tenant_id, title, model) VALUES ($1,$2,$3) RETURNING id",
            tenant_id,
            title,
            model,
        )
        return str(sid)

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT id::text, tenant_id::text, title, model, archived, session_state,"
            " created_at, updated_at FROM sessions WHERE id = $1",
            uuid.UUID(session_id),
        )
        if row is None:
            return None
        d = dict(row)
        d["session_state"] = json.loads(d["session_state"]) if isinstance(d["session_state"], str) else d["session_state"]
        d["created_at"] = d["created_at"].isoformat()
        d["updated_at"] = d["updated_at"].isoformat()
        return d

    async def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            "SELECT id::text, title, model, archived, updated_at FROM sessions"
            " WHERE archived = false ORDER BY updated_at DESC LIMIT $1",
            limit,
        )
        out = []
        for r in rows:
            d = dict(r)
            d["updated_at"] = d["updated_at"].isoformat()
            out.append(d)
        return out

    async def create_run(
        self,
        run_id: str,
        session_id: str,
        *,
        kind: str = "new",
        max_turns: int = 200,
        tenant_id: uuid.UUID = DEFAULT_TENANT,
    ) -> None:
        await self._pool.execute(
            "INSERT INTO runs (id, session_id, tenant_id, kind, max_turns) VALUES ($1,$2,$3,$4,$5)",
            uuid.UUID(run_id),
            uuid.UUID(session_id),
            tenant_id,
            kind,
            max_turns,
        )

    async def set_run_status(self, run_id: str, status: str) -> None:
        await self._pool.execute(
            "UPDATE runs SET status = $2 WHERE id = $1", uuid.UUID(run_id), status
        )

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT id::text, session_id::text, kind, status, usage_input, usage_output,"
            " error, created_at, finished_at FROM runs WHERE id = $1",
            uuid.UUID(run_id),
        )
        if row is None:
            return None
        d = dict(row)
        d["error"] = json.loads(d["error"]) if isinstance(d["error"], str) else d["error"]
        d["created_at"] = d["created_at"].isoformat()
        d["finished_at"] = d["finished_at"].isoformat() if d["finished_at"] else None
        return d


def _state_dict(state: SessionState) -> dict[str, Any]:
    """SessionState（纯 JSON 标量/列表字段）→ 可序列化 dict。"""
    return {
        "permission_mode": state.permission_mode,
        "goal": state.goal,
        "recent_goals": list(state.recent_goals),
        "recent_files": list(state.recent_files),
        "active_artifacts": list(state.active_artifacts),
        "verified_work": list(state.verified_work),
        "work_log": list(state.work_log),
        "async_tasks": list(state.async_tasks),
    }
