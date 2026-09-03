"""run 生命周期（实现计划第五节）：队列消费 → 会话锁 → 图执行/事件泵 → 写穿 → 收尾。

事件泵：astream 双通道（custom=图内事件翻译为 SSE 契约④；values=写穿 diff +
approval_required 提取）。崩溃恢复：resume job 以同一 thread_id 重入，
有 checkpoint 从断点续，无 checkpoint 由调用方重建初始 state。

Redis 实现为薄封装，联调在 M1 集成测试；进程内实现供测试与单机部署。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Callable, Literal, Protocol

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel

from engine.deps import EngineDeps, make_config
from engine.stream_events import SSEEvent, translate
from services.session_storage import MessageStore, SessionStore
from engine.types import AgentState, make_initial_state
from engine.messages import PlatformMessage
from api.usage import UsageSnapshot


# ---------------------------------------------------------------------------
# 基础设施协议与实现
# ---------------------------------------------------------------------------


class RunJob(BaseModel):
    run_id: str
    session_id: str
    tenant_id: str
    kind: Literal["new", "resume"] = "new"
    resume: dict | None = None  # ApprovalDecision payload（resume 用）


class RunQueue(Protocol):
    async def enqueue(self, job: RunJob) -> None: ...

    async def fetch(self) -> RunJob | None: ...


class RunLock(Protocol):
    async def acquire(self, session_id: str, owner: str, ttl_seconds: float) -> bool: ...

    async def release(self, session_id: str, owner: str) -> None: ...


class EventPublisher(Protocol):
    async def publish(self, session_id: str, event: SSEEvent) -> None: ...


class InMemoryRunQueue:
    def __init__(self) -> None:
        self.items: list[RunJob] = []

    async def enqueue(self, job: RunJob) -> None:
        self.items.append(job)

    async def fetch(self) -> RunJob | None:
        return self.items.pop(0) if self.items else None


class InMemoryRunLock:
    def __init__(self) -> None:
        self.held: dict[str, str] = {}

    async def acquire(self, session_id: str, owner: str, ttl_seconds: float) -> bool:
        current = self.held.get(session_id)
        if current is None or current == owner:
            self.held[session_id] = owner
            return True
        return False

    async def release(self, session_id: str, owner: str) -> None:
        if self.held.get(session_id) == owner:
            del self.held[session_id]


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self.streams: dict[str, list[SSEEvent]] = {}

    async def publish(self, session_id: str, event: SSEEvent) -> None:
        self.streams.setdefault(session_id, []).append(event)


class RedisRunQueue:
    """Redis Streams 消费组队列（薄封装；联调见 M1）。"""

    def __init__(self, client, stream: str = "run:queue", group: str = "workers", consumer: str = "w0") -> None:
        self._client = client
        self._stream = stream
        self._group = group
        self._consumer = consumer

    async def enqueue(self, job: RunJob) -> None:
        await self._client.xadd(self._stream, {"job": job.model_dump_json()})

    async def fetch(self) -> RunJob | None:
        try:
            await self._client.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except Exception:  # noqa: BLE001 — 组已存在
            pass
        rows = await self._client.xreadgroup(self._group, self._consumer, {self._stream: ">"}, count=1, block=1000)
        for _stream, entries in rows or []:
            for _entry_id, fields in entries:
                return RunJob.model_validate_json(fields["job"])
        return None


class RedisRunLock:
    def __init__(self, client) -> None:
        self._client = client

    async def acquire(self, session_id: str, owner: str, ttl_seconds: float) -> bool:
        return bool(
            await self._client.set(
                f"lock:run:{session_id}", owner, nx=True, ex=max(1, int(ttl_seconds))
            )
        )

    async def release(self, session_id: str, owner: str) -> None:
        current = await self._client.get(f"lock:run:{session_id}")
        if current and current.decode() == owner:
            await self._client.delete(f"lock:run:{session_id}")


class RedisEventPublisher:
    def __init__(self, client) -> None:
        self._client = client

    async def publish(self, session_id: str, event: SSEEvent) -> None:
        await self._client.xadd(f"events:{session_id}", {"event": event.model_dump_json()})


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    state: AgentState | None
    interrupted: bool
    job: RunJob


class RunWorker:
    def __init__(
        self,
        graph: CompiledStateGraph,
        *,
        queue: RunQueue,
        locks: RunLock,
        publisher: EventPublisher,
        store: MessageStore,
        session_store: SessionStore,
        lock_ttl_seconds: float = 30.0,
    ) -> None:
        self._graph = graph
        self._queue = queue
        self._locks = locks
        self._publisher = publisher
        self._store = store
        self._session_store = session_store
        self._lock_ttl = lock_ttl_seconds
        self._persisted: dict[str, int] = {}  # run_id → 已写穿消息数

    async def serve_once(self, deps_for: Callable[[RunJob], EngineDeps]) -> RunResult | None:
        """取一个 job 并执行到底（含 resume）。生产部署换成常驻消费循环。"""
        job = await self._queue.fetch()
        if job is None:
            return None
        return await self.execute(job, deps_for(job))

    async def execute(self, job: RunJob, deps: EngineDeps) -> RunResult:
        # 一会话一活跃 run：抢不到锁就让位重投
        if not await self._locks.acquire(job.session_id, job.run_id, self._lock_ttl):
            await self._queue.enqueue(job)
            return RunResult(state=None, interrupted=False, job=job)

        try:
            # 写穿指针 = store 已有历史长度：new 不重写初始历史；
            # resume 时 checkpoint 领先 store 的缺口由首次 diff 补写
            self._persisted[job.run_id] = len(await self._store.history(job.session_id))
            config = make_config(
                deps,
                tenant_id=job.tenant_id,
                session_id=job.session_id,
                run_id=job.run_id,
                thread_id=job.run_id,
            )
            if job.kind == "resume":
                graph_input: dict | Command = Command(resume=job.resume)
            else:
                graph_input = await self._initial_state(job, deps)

            interrupted = False
            final: AgentState | None = None
            async for mode, chunk in self._graph.astream(
                graph_input, config, stream_mode=["values", "custom"]
            ):
                if mode == "custom":
                    sse = translate(chunk)
                    if sse is not None:
                        await self._publisher.publish(job.session_id, sse)
                    continue
                final = chunk
                await self._write_through(job, chunk)
                for payload in self._interrupt_payloads(chunk):
                    interrupted = True
                    await self._publisher.publish(
                        job.session_id,
                        SSEEvent(type="approval_required", payload=payload),
                    )

            if final is not None and not interrupted:
                await self._session_store.update_state(job.session_id, final["session_state"])
                error = final.get("error")
                await self._session_store.finish_run(
                    job.run_id,
                    final.get("usage_total") or UsageSnapshot(),
                    {"code": error.code, "message": error.message} if error else None,
                )
            return RunResult(state=final, interrupted=interrupted, job=job)
        finally:
            await self._locks.release(job.session_id, job.run_id)

    async def _initial_state(self, job: RunJob, deps: EngineDeps) -> AgentState:
        history = await self._store.history(job.session_id)
        session_state = await self._session_store.get_state(job.session_id)
        return make_initial_state(history, deps.cfg.max_tokens, session_state)

    async def _write_through(self, job: RunJob, snapshot: dict) -> None:
        messages = snapshot.get("messages") or []
        pointer = self._persisted.get(job.run_id, 0)
        if len(messages) <= pointer:
            return
        new: list[PlatformMessage] = messages[pointer:]
        self._persisted[job.run_id] = len(messages)
        # 表 → Stream 顺序：先落事实源，再发 assistant 终态事件
        await self._store.append(job.session_id, job.run_id, new)
        for msg in new:
            if msg.role == "assistant":
                await self._publisher.publish(
                    job.session_id,
                    SSEEvent(
                        type="assistant_turn_complete",
                        payload={"message": msg.model_dump(mode="json")},
                    ),
                )

    @staticmethod
    def _interrupt_payloads(chunk: dict) -> list[dict]:
        raw = chunk.get("__interrupt__") or []
        payloads = []
        for item in raw:
            value = getattr(item, "value", item)
            payloads.append(value if isinstance(value, dict) else dict(value))
        return payloads
