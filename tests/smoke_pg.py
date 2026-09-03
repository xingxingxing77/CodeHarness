"""P2 真库端到端冒烟：compose Postgres（真实 DDL + Pg 存储层 + AsyncPostgresSaver）。

运行：docker compose up -d && python -m server.smoke_pg
"""

from __future__ import annotations

import asyncio
import os

import asyncpg
import httpx
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from api.usage import UsageSnapshot

from services.runner import InMemoryRunLock, InMemoryRunQueue
from tests.testing import FakeSandbox
from permissions.approval import ApprovalService
from gateway.spill import InMemoryObjectStore
from permissions.engine import RulePermissionEngine, builtin_recipe_rules
from server.app import ServerComponents, create_app
from server.broker import InMemoryBroker
from server.db import PgMessageStore, PgSessionStore, setup_schema
from tools.builtin import create_default_registry

DSN = os.environ.get("DATABASE_URL", "postgres://postgres:codeharness@localhost:5432/codeharness")


async def main() -> int:
    import contextlib

    pool = await asyncpg.create_pool(DSN)
    await setup_schema(pool)

    # 每次冒烟用全新 schema 状态：清空业务表（不动结构）
    async with pool.acquire() as conn:
        for table in ("messages", "approvals", "runs", "sessions"):
            await conn.execute(f"DELETE FROM {table}")

    message_store = PgMessageStore(pool)
    session_store = PgSessionStore(pool)  # MessageStore/SessionStore/SessionAdmin/RunStore 四合一

    failures = 0
    async with contextlib.AsyncExitStack() as stack:
        checkpointer = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(DSN))
        components = ServerComponents(
            message_store=message_store,
            session_store=session_store,
            session_admin=session_store,   # create/get/list 会话
            run_store=session_store,       # create/set_status/get run
            approvals=ApprovalService(),
            broker=InMemoryBroker(),
            queue=InMemoryRunQueue(),
            locks=InMemoryRunLock(),
            registry=create_default_registry(),
            permissions=RulePermissionEngine(rules=builtin_recipe_rules("standard"), recipe="standard"),
            object_store=InMemoryObjectStore(),
            sandbox_factory=lambda sid: FakeSandbox(),
            chat_factory=lambda model: _fake_chat(),
            checkpointer=checkpointer,
        )
        app = create_app(components)

        from tests.testing import FakeChat
        from engine.messages import PlatformMessage, ToolCallBlock
        from api.protocol import ApiMessageCompleteEvent

        def _fake_chat():
            chat = FakeChat()
            chat.scripts = [
                [ApiMessageCompleteEvent(
                    message=PlatformMessage(role="assistant", content=[
                        ToolCallBlock(id="c1", name="write_file", input={"file_path": "hello.py", "content": "print('hi')\n"}),
                    ]),
                    usage=UsageSnapshot(input_tokens=4, output_tokens=2),
                )],
                [ApiMessageCompleteEvent(
                    message=PlatformMessage.assistant("done"),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                )],
            ]
            return chat

        await checkpointer.setup()
        await components.start()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
                sid = (await client.post("/api/v1/sessions", json={"model": "test-model"})).json()["id"]
                run_id = (await client.post(
                    f"/api/v1/sessions/{sid}/messages",
                    json={"content": [{"type": "text", "text": "hi"}]},
                )).json()["run_id"]
                for _ in range(100):
                    run = (await client.get(f"/api/v1/runs/{run_id}")).json()
                    if run["status"] in ("succeeded", "failed"):
                        break
                    await asyncio.sleep(0.05)
                print("run:", run["status"])
                history = (await client.get(f"/api/v1/sessions/{sid}/messages")).json()["messages"]
                ok_roles = [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
                print("history ok:", ok_roles, "| status:", run["status"])
                if not (ok_roles and run["status"] == "succeeded"):
                    failures += 1
        finally:
            await components.stop()
            await pool.close()

    print(f"\n{'PASS' if failures == 0 else 'FAIL'}  server.smoke_pg")
    return 1 if failures else 0


if __name__ == "__main__":
    # psycopg 异步模式在 Windows 上要求 Selector 事件循环（生产 Linux 无此限制）
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
