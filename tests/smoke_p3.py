"""P3 真库端到端冒烟：auth/凭证加密/hooks 审计/prompts 编织/pgvector 记忆。

前置：docker compose up -d（postgres+redis）。
运行：python -m tests.smoke_p3
"""

from __future__ import annotations

import asyncio
import os

import asyncpg

DSN = os.environ.get("DATABASE_URL", "postgres://postgres:codeharness@localhost:5432/codeharness")
TENANT = "00000000-0000-0000-0000-000000000001"

failures = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global failures
    if cond:
        print(f"PASS  {name}")
    else:
        failures += 1
        print(f"FAIL  {name}: {detail}")


async def main() -> int:
    import contextlib

    from auth.service import CredentialVault
    from hooks.hooks import HooksEventBus
    from memory.memory import MemoryStore
    from prompts.compose import PromptComposer
    from server.db import PgCredentialStore, setup_schema

    pool = await asyncpg.create_pool(DSN)
    await setup_schema(pool)
    vault = CredentialVault("A" * 43)

    # ---- 凭证库：加密落库 → 解密还原 → 列表不含明文 ----
    store = PgCredentialStore(pool, vault)
    await store.add(TENANT, "anthropic", "sk-ant-real-secret", label="p3")
    rows = await store.list(TENANT)
    entry = next(r for r in rows if r["provider"] == "anthropic" and r["label"] == "p3")
    raw = await pool.fetchval(
        "SELECT secret_enc FROM credentials WHERE id = $1", __import__("uuid").UUID(entry["id"])
    )
    check("credentials.encrypted_at_rest", "sk-ant-real-secret" not in raw)
    creds = await store.resolve_provider(TENANT, "anthropic")
    check("credentials.resolve", creds is not None and creds.api_key == "sk-ant-real-secret")
    await store.delete(TENANT, entry["id"])
    check("credentials.delete", await store.resolve_provider(TENANT, "anthropic") is None)

    # ---- hooks：事件 → audit_events ----
    bus = HooksEventBus(pool, tenant_id=TENANT)
    await bus.emit("pre_tool_use", {"tool_name": "bash", "run_id": "r1"})
    await bus.emit("post_tool_use", {"tool_name": "bash", "is_error": False, "run_id": "r1"})
    rows = await pool.fetch(
        "SELECT kind FROM audit_events WHERE tenant_id = $1 ORDER BY id", __import__("uuid").UUID(TENANT)
    )
    kinds = [r["kind"] for r in rows]
    check("hooks.audit_written", "pre_tool_use" in kinds and "post_tool_use" in kinds, str(kinds))

    # ---- prompts：编织 ----
    composer = PromptComposer(personalization="Tenant rule: always answer in Chinese.")
    prompt = composer.compose(None)
    check("prompts.composed", "Codeharness" in prompt and "answer in Chinese" in prompt)

    # ---- pgvector 记忆：写入 + 检索 ----
    memory = MemoryStore(pool)
    await memory.add(TENANT, "the deploy script lives in scripts/deploy.sh")
    await memory.add(TENANT, "user prefers dark mode in the web UI")
    hits = await memory.search(TENANT, "where is the deploy script?")
    check("memory.search_top1", hits and "deploy.sh" in hits[0].content, str([h.content for h in hits][:2]))
    await memory.add(TENANT, "meeting notes: quarterly planning on fridays")
    hits2 = await memory.search(TENANT, "quarterly planning schedule", k=2)
    check("memory.search_k", len(hits2) <= 2 and hits2, str(len(hits2)))

    await pool.close()
    print(f"\n{'PASS' if failures == 0 else 'FAIL'}  tests.smoke_p3 ({failures} failures)")
    return 1 if failures else 0


import selectors


def _loop_factory() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=_loop_factory)
