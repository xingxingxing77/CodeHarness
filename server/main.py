"""本地/生产启动入口：装配 ServerComponents 并暴露 ASGI app。

用法：uvicorn server.main:app --port 8000（Windows 开发机请用 scripts/run_server.py，
其使用 Selector 事件循环以满足 psycopg 异步要求）。
环境：见 docs/配置清单；无供应商 key 时自动落入 MockChat（演示链路）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import Callable

import asyncpg
from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from api.factory import create_client
from services.session_storage import MessageStore, SessionStore
from services.runner import InMemoryRunLock, InMemoryRunQueue, RunWorker
from permissions.approval import ApprovalService
from gateway.gateway import SandboxToolGateway
from gateway.spill import InMemoryObjectStore, ObjectStore
from tools.base import SandboxHandle
from api.protocol import SupportsStreamingMessages
from permissions.engine import RulePermissionEngine, builtin_recipe_rules
from server.app import NoopPolicy, ServerComponents, create_app
from server.broker import InMemoryBroker
from server.db import PgMessageStore, PgSessionStore, setup_schema
from server.mock_chat import MockChat
from tools.builtin import create_default_registry

log = logging.getLogger(__name__)

DSN = os.environ.get("DATABASE_URL", "postgres://postgres:codeharness@localhost:5432/codeharness")

# 连接存活探针（psycopg 连接被关闭问题追踪；稳定后可关）
_PROBE = os.environ.get("CODEHARNESS_PROBE", "1") == "1"

_STACK = contextlib.AsyncExitStack()


def _default_chat_factory(model: str) -> SupportsStreamingMessages:
    """优先真实供应商（env key），否则 MockChat（演示链路）。"""
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if anthropic_key or openai_key:
        from api.factory import Credential, StaticCredentialResolver

        creds = Credential(api_key=anthropic_key or openai_key)
        return create_client(model, StaticCredentialResolver(creds).resolve(_spec_for(model)))
    return MockChat()


def _spec_for(model: str):
    from api.registry import detect_provider_from_registry

    return detect_provider_from_registry(model)


def _sandbox_factory() -> Callable[[str], SandboxHandle]:
    mode = os.environ.get("SANDBOX_BACKEND", "fake")  # fake|docker（Docker 联调后启用）
    if mode == "docker":
        from sandbox.docker import SandboxPool

        pool = SandboxPool(os.environ.get("WORKSPACE_DATA_ROOT", "./data/workspaces"))
        return pool.get
    from tests.testing import FakeSandbox

    return lambda session_id: FakeSandbox()


async def _make_components() -> ServerComponents:
    pool = await asyncpg.create_pool(DSN)
    await _STACK.enter_async_context(pool)
    await setup_schema(pool)

    checkpointer = await _STACK.enter_async_context(AsyncPostgresSaver.from_conn_string(DSN))
    await checkpointer.setup()

    async def probe(tag: str) -> None:
        conn = getattr(checkpointer, "_connection", None) or getattr(checkpointer, "conn", None)
        closed = getattr(conn, "closed", "?")
        print(f"PROBE {tag}: conn={type(conn).__name__} closed={closed}", flush=True)

    if _PROBE:
        await probe("after-setup")
        await asyncio.sleep(1.0)
        await probe("after-1s")

    broker = InMemoryBroker()  # 单进程形态；多进程换 server/broker.RedisBroker

    from auth.service import CredentialVault
    from hooks.hooks import HooksEventBus
    from memory.memory import MemoryStore
    from prompts.compose import PromptComposer

    master_key = os.environ.get("CREDENTIAL_MASTER_KEY", "")
    vault = None
    credential_store = None
    if master_key:
        vault = CredentialVault(master_key)
        credential_store = __import__("server.db", fromlist=["PgCredentialStore"]).PgCredentialStore(pool, vault)
    else:
        log.warning("CREDENTIAL_MASTER_KEY not set: credential vault disabled (MockChat/env only)")

    hooks_bus = HooksEventBus(pool, tenant_id="00000000-0000-0000-0000-000000000001")
    memory_store = MemoryStore(pool)
    prompt = PromptComposer(
        identity="You are Codeharness, a capable coding agent for this tenant.",
    )

    from skills.registry import SkillRegistry
    from tasks.service import PgTaskStore

    skill_roots = [os.environ.get("CODEHARNESS_SKILLS_ROOT", "./skills_repo")]
    task_store = PgTaskStore(pool)

    components = ServerComponents(
        message_store=PgMessageStore(pool),
        session_store=PgSessionStore(pool),
        session_admin=PgSessionStore(pool),   # create/get/list 会话
        run_store=PgSessionStore(pool),       # create/set_status/get run
        approvals=ApprovalService(),
        broker=broker,
        queue=InMemoryRunQueue(),
        locks=InMemoryRunLock(),
        registry=create_default_registry(),
        permissions=RulePermissionEngine(rules=builtin_recipe_rules("standard"), recipe="standard"),
        object_store=InMemoryObjectStore(),
        sandbox_factory=_sandbox_factory(),
        chat_factory=_default_chat_factory,
        prompt=prompt,
        policy=hooks_bus,
        credential_store=credential_store,
        memory_store=memory_store,
        skill_registry=SkillRegistry(skill_roots),
        task_store=task_store,
        auth_enabled=os.environ.get("AUTH_ENABLED", "0") == "1",
        jwt_secret=os.environ.get("JWT_SECRET", ""),
        checkpointer=checkpointer,
    )
    if _PROBE:
        components._probe = probe  # type: ignore[attr-defined]
    return components


async def _on_stop() -> None:
    await _STACK.aclose()


app = create_app(_make_components, on_stop=_on_stop)
