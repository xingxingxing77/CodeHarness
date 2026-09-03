"""事件总线：worker 发布 SSE 契约④事件，server 的 SSE 端点订阅。

InMemoryBroker：单进程（本地开发 / ASGI E2E），环形缓冲支持 Last-Event-ID 重放。
RedisBroker：XADD events:{session} + XREAD 重放（生产形态，联调 P2）。
entry id 单调递增（f"{seq:020d}"），作为 SSE 的 id/续传游标。
"""

from __future__ import annotations

import asyncio
import itertools
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from engine.stream_events import SSEEvent


@dataclass(frozen=True)
class BrokerMessage:
    entry_id: str
    event: SSEEvent


class EventBroker(Protocol):
    async def publish(self, session_id: str, event: SSEEvent) -> str: ...

    def subscribe(
        self, session_id: str, after: str | None = None
    ) -> AsyncIterator[BrokerMessage]: ...


class InMemoryBroker:
    BUFFER = 2_000

    def __init__(self) -> None:
        self._buffers: dict[str, deque[BrokerMessage]] = {}
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._seq = itertools.count(1)

    async def publish(self, session_id: str, event: SSEEvent) -> str:
        message = BrokerMessage(entry_id=f"{next(self._seq):020d}", event=event)
        buffer = self._buffers.setdefault(session_id, deque(maxlen=self.BUFFER))
        buffer.append(message)
        for queue in self._queues.get(session_id, []):
            queue.put_nowait(message)
        return message.entry_id

    async def subscribe(
        self, session_id: str, after: str | None = None
    ) -> AsyncIterator[BrokerMessage]:
        queue: asyncio.Queue = asyncio.Queue()
        buffer = self._buffers.setdefault(session_id, deque(maxlen=self.BUFFER))
        live_from = None
        if after is not None:
            seen = False
            for message in buffer:
                if seen:
                    yield message
                elif message.entry_id == after:
                    seen = True
            if not seen and after < f"{next(self._seq):020d}":
                live_from = None  # 游标已不在缓冲内：只给实时
        else:
            live_from = None
        self._queues.setdefault(session_id, []).append(queue)
        try:
            while True:
                message = await queue.get()
                if after is not None and message.entry_id <= after:
                    continue  # 重放段已覆盖
                yield message
        finally:
            self._queues.get(session_id, []).remove(queue)


class RedisBroker:
    """Redis Streams 实现：生产形态（XADD / XREAD BLOCK）。"""

    def __init__(self, client, *, maxlen: int = 10_000, block_ms: int = 15_000) -> None:
        self._client = client
        self._maxlen = maxlen
        self._block_ms = block_ms

    async def publish(self, session_id: str, event: SSEEvent) -> str:
        entry_id = await self._client.xadd(
            f"events:{session_id}",
            {"event": event.model_dump_json()},
            maxlen=self._maxlen,
            approximate=True,
        )
        return entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)

    async def subscribe(
        self, session_id: str, after: str | None = None
    ) -> AsyncIterator[BrokerMessage]:
        stream = f"events:{session_id}"
        cursor = after or "0"
        while True:
            rows = await self._client.xread({stream: cursor}, count=100, block=self._block_ms)
            got_any = False
            for _stream_key, entries in rows or []:
                for entry_id, fields in entries:
                    entry_id = entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)
                    cursor = entry_id
                    got_any = True
                    payload = fields["event"]
                    if isinstance(payload, bytes):
                        payload = payload.decode()
                    yield BrokerMessage(entry_id=entry_id, event=SSEEvent.model_validate_json(payload))
            if not got_any:
                # XREAD block 已等待；继续下一轮（游标推进）
                continue
