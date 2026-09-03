"""runner 端到端冒烟（第五节）：队列→锁→图执行→事件泵→写穿→收尾，含审批挂起/恢复。

运行：python -m engine.smoke_runner
"""
from __future__ import annotations

import asyncio

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from engine.graph import build_graph
from services.session_storage import InMemoryMessageStore, InMemorySessionStore
from services.runner import (
    InMemoryEventPublisher,
    InMemoryRunLock,
    InMemoryRunQueue,
    RunJob,
    RunWorker,
)
from tests.testing import (
    FakeChat,
    FakeGateway,
    build_deps,
    make_plan_auto,
    make_plan_mixed,
)
from permissions.approval import ApprovalService
from engine.messages import PlatformMessage, ToolCallBlock
from api.protocol import ApiMessageCompleteEvent, ApiTextDeltaEvent
from api.usage import UsageSnapshot


def _worker(queue, store, session_store, publisher, locks=None) -> RunWorker:
    return RunWorker(
        build_graph(MemorySaver()),
        queue=queue,
        locks=locks or InMemoryRunLock(),
        publisher=publisher,
        store=store,
        session_store=session_store,
    )


def _tool_msg(*pairs):
    return PlatformMessage(role="assistant", content=[
        ToolCallBlock(id=i, name=n, input={}) for i, n in pairs
    ])


async def case_runner_end_to_end():
    """new run 全链路：写穿 3 条新消息、SSE 事件序、session_state/usage 收尾。"""
    store = InMemoryMessageStore()
    await store.append("s1", "seed", [PlatformMessage.user("hi")])
    session_store = InMemorySessionStore()
    publisher = InMemoryEventPublisher()
    queue = InMemoryRunQueue()
    gateway = FakeGateway(make_plan_auto)

    chat = FakeChat()
    chat.scripts = [
        [ApiMessageCompleteEvent(
            message=_tool_msg(("c1", "read_file")),
            usage=UsageSnapshot(input_tokens=10, output_tokens=5),
        )],
        [ApiTextDeltaEvent(text="done "), ApiMessageCompleteEvent(
            message=PlatformMessage.assistant("done"),
            usage=UsageSnapshot(input_tokens=3, output_tokens=2),
        )],
    ]
    worker = _worker(queue, store, session_store, publisher)
    deps = build_deps(chat, gateway)
    job = RunJob(run_id="r1", session_id="s1", tenant_id="t1")

    result = await worker.execute(job, deps)
    assert not result.interrupted and result.state is not None
    assert result.state["route"] == "proceed" and result.state["turn"] == 2

    # 写穿：初始 1 条 + assistant(工具) + user(回执) + assistant(最终) = 4
    history = await store.history("s1")
    assert [m.role for m in history] == ["user", "assistant", "user", "assistant"], history
    assert history[2].tool_results and history[3].text == "done"

    # 事件流：custom 事件按序翻译，assistant_turn_complete 由写穿发布
    events = publisher.streams["s1"]
    types = [e.type for e in events]
    assert types.count("assistant_turn_complete") == 2
    assert "tool_started" in types and "tool_completed" in types
    assert types[-1] == "run_finished"
    assert events[-1].payload["usage"]["total_tokens"] == 20

    # 收尾
    assert session_store.states["s1"] is result.state["session_state"]
    assert session_store.finished[0]["run_id"] == "r1"
    assert session_store.finished[0]["usage_total"].total_tokens == 20
    assert session_store.finished[0]["error"] is None


async def case_runner_interrupt_resume():
    """审批挂起 → approval_required 事件 + 工单 pending → 决策 → resume 续跑。"""
    store = InMemoryMessageStore()
    await store.append("s2", "seed", [PlatformMessage.user("hi")])
    session_store = InMemorySessionStore()
    publisher = InMemoryEventPublisher()
    queue = InMemoryRunQueue()
    approvals = ApprovalService()
    gateway = FakeGateway(make_plan_mixed)

    chat = FakeChat()
    chat.scripts = [
        [ApiMessageCompleteEvent(
            message=_tool_msg(("a1", "bash"), ("a2", "read_file")),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
        )],
        [ApiMessageCompleteEvent(
            message=PlatformMessage.assistant("after approval"),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
        )],
    ]
    worker = _worker(queue, store, session_store, publisher)
    deps = build_deps(chat, gateway, approvals=approvals)
    job = RunJob(run_id="r2", session_id="s2", tenant_id="t1")

    result = await worker.execute(job, deps)
    assert result.interrupted, result
    assert gateway.run_calls == 0  # 挂起时不执行任何工具

    events = publisher.streams["s2"]
    approval_events = [e for e in events if e.type == "approval_required"]
    assert len(approval_events) == 1
    payload = approval_events[0].payload
    assert payload["items"][0]["call_id"] == "a1"

    ticket = approvals.get(payload["ticket_id"])
    assert ticket is not None and ticket.status == "pending"

    # 运维决策：批准 a1 → 写工单 → 入 resume 队列（REST 层职责）
    from tools.base import ApprovalDecision
    decided = approvals.decide(
        ticket.ticket_id,
        ApprovalDecision(ticket_id=ticket.ticket_id,
                         choices=[{"call_id": "a1", "approve": True}]),
        decided_by="op-1",
    )
    assert decided.status == "decided"

    resume_job = RunJob(
        run_id="r2", session_id="s2", tenant_id="t1",
        kind="resume", resume=decided.decision,
    )
    result2 = await worker.execute(resume_job, deps)
    assert not result2.interrupted and result2.state["turn"] == 2
    assert gateway.run_calls == 1  # 全程只执行一次网关

    history = await store.history("s2")
    assert [m.role for m in history] == ["user", "assistant", "user", "assistant"]
    assert {r.tool_use_id for r in history[2].tool_results} == {"a1", "a2"}
    assert chat.scripts == []


async def case_runner_lock_contention():
    """同会话已有活跃 run：抢不到锁 → job 重投队列，本次返回 None state。"""
    store = InMemoryMessageStore()
    session_store = InMemorySessionStore()
    publisher = InMemoryEventPublisher()
    queue = InMemoryRunQueue()
    locks = InMemoryRunLock()
    chat = FakeChat()
    chat.scripts = [[ApiMessageCompleteEvent(
        message=PlatformMessage.assistant("ok"), usage=UsageSnapshot(input_tokens=1, output_tokens=1)
    )]]
    worker = _worker(queue, store, session_store, publisher, locks=locks)
    deps = build_deps(chat, FakeGateway(make_plan_auto))

    assert await locks.acquire("s3", "other-run", 30.0)
    job = RunJob(run_id="r3", session_id="s3", tenant_id="t1")
    result = await worker.execute(job, deps)
    assert result.state is None
    assert queue.items and queue.items[0].run_id == "r3"  # 重投
    assert locks.held["s3"] == "other-run"  # 未被抢走

    await locks.release("s3", "other-run")
    result2 = await worker.execute(queue.items.pop(0), deps)
    assert result2.state is not None  # 空历史直接收敛（chat 脚本为空 → fail empty_stream）
    assert locks.held.get("s3") is None  # 释放归还


CASES = [case_runner_end_to_end, case_runner_interrupt_resume, case_runner_lock_contention]


async def main() -> int:
    failures = 0
    for case in CASES:
        try:
            await case()
            print(f"PASS  {case.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {case.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERROR {case.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
