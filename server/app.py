"""FastAPI 服务装配（接口契约⑥ + SSE 契约④；P2）。

ServerComponents：存储（PG 或内存）+ 事件总线 + run 队列 + worker；
依赖注入到底层引擎（EngineDeps 单点注入模式）。鉴权（JWT）P3 接入。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Protocol

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from engine.deps import EngineConfig, EngineDeps
from engine.stream_events import SSE_EVENT_TYPES, SSEEvent
from engine.graph import build_graph
from services.session_storage import InMemoryMessageStore, MessageStore, SessionStore
from services.runner import InMemoryEventPublisher, InMemoryRunLock, InMemoryRunQueue, RunJob, RunWorker
from engine.types import RunOutcome
from permissions.approval import ApprovalService
from gateway.gateway import SandboxToolGateway
from gateway.spill import InMemoryObjectStore, ObjectStore
from tools.base import SandboxHandle
from api.protocol import SupportsStreamingMessages
from permissions.engine import RulePermissionEngine, builtin_recipe_rules
from services.compact import BasicCompactor
from tools.base import ToolRegistry

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 会话管理协议（PG 实现在 server/db.py；内存实现在此）
# ---------------------------------------------------------------------------


class SessionAdmin(Protocol):
    async def create_session(self, model: str, title: str = "") -> str: ...

    async def get_session(self, session_id: str) -> dict[str, Any] | None: ...

    async def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]: ...


class RunStore(Protocol):
    async def create_run(
        self, run_id: str, session_id: str, *, kind: str = "new", max_turns: int = 200
    ) -> None: ...

    async def set_run_status(self, run_id: str, status: str) -> None: ...

    async def get_run(self, run_id: str) -> dict[str, Any] | None: ...


class InMemorySessionAdmin:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}

    async def create_session(self, model: str, title: str = "") -> str:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "id": session_id,
            "title": title,
            "model": model,
            "archived": False,
        }
        return session_id

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self.sessions.get(session_id)

    async def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = [dict(s) for s in self.sessions.values() if not s["archived"]]
        return rows[:limit]


class InMemoryRunStore:
    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}

    async def create_run(
        self, run_id: str, session_id: str, *, kind: str = "new", max_turns: int = 200
    ) -> None:
        self.runs[run_id] = {
            "id": run_id,
            "session_id": session_id,
            "kind": kind,
            "status": "queued",
            "usage": None,
            "error": None,
            "max_turns": max_turns,
        }

    async def set_run_status(self, run_id: str, status: str) -> None:
        if run_id in self.runs:
            self.runs[run_id]["status"] = status

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.runs.get(run_id)


class NoopPolicy:
    """M1 默认策略引擎：无否决、无观察动作。"""

    async def pre_tool_use(self, call, ctx):
        return None

    async def post_tool_use(self, call, result, ctx):
        return None

    async def post_run(self, outcome: RunOutcome) -> None:
        return None


# ---------------------------------------------------------------------------
# 组件容器
# ---------------------------------------------------------------------------


@dataclass
class ServerComponents:
    message_store: MessageStore
    session_store: SessionStore
    session_admin: SessionAdmin
    run_store: RunStore
    approvals: ApprovalService
    broker: Any                                   # EventBroker：publish + subscribe
    queue: InMemoryRunQueue
    locks: InMemoryRunLock
    registry: ToolRegistry
    permissions: RulePermissionEngine
    object_store: ObjectStore
    sandbox_factory: Callable[[str], SandboxHandle]
    chat_factory: Callable[[str], SupportsStreamingMessages]
    recipe: str = "standard"
    system_prompt: str = "You are Codeharness, a helpful coding agent."
    max_tokens: int = 8192
    max_turns: int = 200
    policy: Any = None                               # PolicyEngine；None → NoopPolicy
    checkpointer: Any = None                         # BaseCheckpointSaver；PG 形态传 AsyncPostgresSaver
    _worker: RunWorker | None = field(default=None, repr=False)
    _worker_task: asyncio.Task | None = field(default=None, repr=False)

    # -- worker ---------------------------------------------------------------

    def build_worker(self) -> RunWorker:
        if self._worker is None:
            self._worker = RunWorker(
                build_graph(self.checkpointer),
                queue=self.queue,
                locks=self.locks,
                publisher=_BrokerPublisher(self.broker),
                store=self.message_store,
                session_store=self.session_store,
            )
        return self._worker

    async def build_deps(self, job: RunJob) -> EngineDeps:
        session = await self.session_admin.get_session(job.session_id)
        model = (session or {}).get("model") or "claude-sonnet-4-6"
        chat = self.chat_factory(model)
        policy = self.policy or NoopPolicy()
        gateway = SandboxToolGateway(
            self.registry,
            self.permissions,
            policy=policy,
            store=self.object_store,
        )
        return EngineDeps(
            chat=chat,
            gateway=gateway,
            approvals=self.approvals,
            compactor=BasicCompactor(chat, model),
            policy=policy,
            sandbox=self.sandbox_factory(job.session_id),
            cfg=EngineConfig(
                model=model,
                system_prompt=self.system_prompt,
                max_tokens=self.max_tokens,
                max_turns=self.max_turns,
            ),
        )

    async def _execute_job(self, job: RunJob) -> None:
        await self.run_store.set_run_status(job.run_id, "running")
        probe = getattr(self, "_probe", None)
        if probe is not None:
            await probe("before-run")
        deps = await self.build_deps(job)
        result = await self.build_worker().execute(job, deps)
        if result.interrupted:
            await self.run_store.set_run_status(job.run_id, "interrupted")
        else:
            error = (result.state or {}).get("error")
            await self.run_store.set_run_status(
                job.run_id, "failed" if error else "succeeded"
            )

    async def _worker_loop(self) -> None:
        while True:
            job = await self.queue.fetch()
            if job is None:
                await asyncio.sleep(0.05)
                continue
            try:
                await self._execute_job(job)
            except Exception:  # noqa: BLE001 — worker 循环必须存活
                log.exception("run %s crashed", job.run_id)
                await self.run_store.set_run_status(job.run_id, "failed")

    async def start(self) -> None:
        self.build_worker()
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None


class _BrokerPublisher(InMemoryEventPublisher):
    """把 RunWorker 的 EventPublisher 协议接到 broker（publish 签名一致）。"""

    def __init__(self, broker) -> None:
        self._broker = broker
        super().__init__()

    async def publish(self, session_id: str, event: SSEEvent) -> None:
        await self._broker.publish(session_id, event)


# ---------------------------------------------------------------------------
# 请求/响应模型（契约⑥）
# ---------------------------------------------------------------------------


class CreateSessionBody(BaseModel):
    model: str
    title: str = ""


class SendMessageBody(BaseModel):
    content: list[dict[str, Any]]


class DecideBody(BaseModel):
    choices: list[dict[str, Any]]
    decided_by: str = ""


# ---------------------------------------------------------------------------
# 应用装配
# ---------------------------------------------------------------------------


class _LazyComponents:
    """组件工厂模式：lifespan 装配前转发属性访问。"""

    def __init__(self, holder: dict[str, ServerComponents]) -> None:
        self._holder = holder

    def __getattr__(self, name: str) -> Any:
        try:
            components = self._holder["components"]
        except KeyError as exc:
            raise RuntimeError("server components not initialised (lifespan not started?)") from exc
        return getattr(components, name)


def create_app(
    components: ServerComponents | Callable[[], Any],
    *,
    manage_lifecycle: bool = True,
    on_stop: Callable[[], Any] | None = None,
) -> FastAPI:
    """components 可传实例，或异步工厂（lifespan 内解析；stop 时回调 on_stop）。"""
    holder: dict[str, ServerComponents] = {}
    proxy = _LazyComponents(holder)
    factory = None if isinstance(components, ServerComponents) else components
    if factory is None:
        holder["components"] = components

    @asynccontextmanager_app_lifespan
    async def lifespan(_app: FastAPI):
        if factory is not None:
            holder["components"] = await factory()
        await proxy.start()
        yield
        await proxy.stop()
        if on_stop is not None:
            await on_stop()

    app = FastAPI(
        title="Codeharness",
        version="0.2.0",
        lifespan=lifespan if manage_lifecycle else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    async def _require_session(session_id: str) -> dict[str, Any]:
        session = await proxy.session_admin.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    # -- 会话 ----------------------------------------------------------------

    @app.post("/api/v1/sessions", status_code=201)
    async def create_session(body: CreateSessionBody):
        session_id = await proxy.session_admin.create_session(body.model, body.title)
        return {"id": session_id, "model": body.model, "title": body.title}

    @app.get("/api/v1/sessions")
    async def list_sessions(limit: int = 50):
        return await proxy.session_admin.list_sessions(limit)

    @app.get("/api/v1/sessions/{session_id}")
    async def get_session(session_id: str):
        session = await proxy.session_admin.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    # -- 消息与 run ------------------------------------------------------------

    @app.get("/api/v1/sessions/{session_id}/messages")
    async def list_messages(session_id: str):
        await _require_session(session_id)
        history = await proxy.message_store.history(session_id)
        return {
            "messages": [
                {
                    "role": m.role,
                    "content": m.model_dump(mode="json")["content"],
                    "metadata": m.metadata,
                }
                for m in history
            ]
        }

    @app.post("/api/v1/sessions/{session_id}/messages", status_code=202)
    async def send_message(session_id: str, body: SendMessageBody):
        await _require_session(session_id)
        if not body.content:
            raise HTTPException(status_code=422, detail="content must not be empty")
        from engine.messages import PlatformMessage

        user_message = PlatformMessage(role="user", content=body.content)
        run_id = str(uuid.uuid4())
        await proxy.run_store.create_run(run_id, session_id, max_turns=proxy.max_turns)
        # 用户消息立即落事实源（写穿提交点只覆盖引擎产出；用户输入由 REST 落）
        await proxy.message_store.append(
            session_id, run_id, [user_message]
        )
        job = RunJob(run_id=run_id, session_id=session_id, tenant_id="default", kind="new")
        await proxy.queue.enqueue(job)
        return {"run_id": run_id}

    @app.get("/api/v1/runs/{run_id}")
    async def get_run(run_id: str):
        run = await proxy.run_store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    # -- 审批 ----------------------------------------------------------------

    @app.get("/api/v1/approvals")
    async def list_approvals():
        return [
            {
                "ticket_id": t.ticket_id,
                "run_id": t.run_id,
                "items": [i.model_dump() for i in t.items],
                "status": t.status,
                "expires_at": t.expires_at,
            }
            for t in proxy.approvals.pending()
        ]

    @app.post("/api/v1/runs/{run_id}/approvals/{ticket_id}/decide")
    async def decide(run_id: str, ticket_id: str, body: DecideBody):
        ticket = proxy.approvals.get(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="ticket not found")
        if ticket.run_id != run_id:
            raise HTTPException(status_code=409, detail="ticket does not belong to run")
        from tools.base import ApprovalDecision

        decision = ApprovalDecision.model_validate(
            {"ticket_id": ticket_id, "choices": body.choices}
        )
        decided = proxy.approvals.decide(ticket_id, decision, decided_by=body.decided_by)
        if decided.status == "expired":
            raise HTTPException(status_code=410, detail="ticket expired")
        run = await proxy.run_store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        resume_job = RunJob(
            run_id=run_id,
            session_id=run["session_id"],
            tenant_id="default",
            kind="resume",
            resume=decided.decision,
        )
        await proxy.queue.enqueue(resume_job)
        return {"status": "queued", "ticket_status": decided.status}

    # -- SSE（契约④） ----------------------------------------------------------

    @app.get("/api/v1/sessions/{session_id}/events")
    async def events(
        session_id: str,
        after: str | None = Query(default=None),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ):
        cursor = after or last_event_id

        async def stream() -> AsyncIterator[str]:
            async for message in proxy.broker.subscribe(session_id, cursor):
                if message.event.type not in SSE_EVENT_TYPES:
                    continue
                yield (
                    f"id: {message.entry_id}\n"
                    f"event: {message.event.type}\n"
                    f"data: {message.event.model_dump_json()}\n\n"
                )

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def asynccontextmanager_app_lifespan(fn):
    """小包装：避免额外 import asgi_lifespan。"""
    from contextlib import asynccontextmanager

    return asynccontextmanager(fn)
