"""写穿持久化（实现计划 5.3）：messages 表是事实源，checkpointer 可丢弃可重建。

两个提交点（agent 终态后 / execute 全部回执后）由 runner 的值快照 diff 驱动：
每条新增消息 append 进 store 后，再发布 assistant_turn_complete（表→Stream 顺序，
SSE 重放不超前于事实源）。session_state 随提交点更新会话行。
"""
from __future__ import annotations

from typing import Protocol

from state.session_state import SessionState
from engine.messages import PlatformMessage
from api.usage import UsageSnapshot


class MessageStore(Protocol):
    async def history(self, session_id: str) -> list[PlatformMessage]: ...

    async def append(
        self, session_id: str, run_id: str, messages: list[PlatformMessage]
    ) -> None: ...


class SessionStore(Protocol):
    async def get_state(self, session_id: str) -> SessionState | None: ...

    async def update_state(self, session_id: str, state: SessionState) -> None: ...

    async def finish_run(
        self, run_id: str, usage_total: UsageSnapshot, error: dict | None
    ) -> None: ...


class InMemoryMessageStore:
    def __init__(self) -> None:
        self._by_session: dict[str, list[PlatformMessage]] = {}
        self.appended: list[tuple[str, str, list[PlatformMessage]]] = []

    async def history(self, session_id: str) -> list[PlatformMessage]:
        return list(self._by_session.get(session_id, []))

    async def append(
        self, session_id: str, run_id: str, messages: list[PlatformMessage]
    ) -> None:
        self._by_session.setdefault(session_id, []).extend(messages)
        self.appended.append((session_id, run_id, list(messages)))


class InMemorySessionStore:
    def __init__(self) -> None:
        self.states: dict[str, SessionState] = {}
        self.finished: list[dict] = []

    async def get_state(self, session_id: str) -> SessionState | None:
        return self.states.get(session_id)

    async def update_state(self, session_id: str, state: SessionState) -> None:
        self.states[session_id] = state

    async def finish_run(
        self, run_id: str, usage_total: UsageSnapshot, error: dict | None
    ) -> None:
        self.finished.append(
            {"run_id": run_id, "usage_total": usage_total, "error": error}
        )
