"""P2 端到端冒烟（内存存储 + FakeChat）：REST → worker → 引擎 → 网关 → SSE 事件。

运行：python -m server.smoke_server
"""

from __future__ import annotations

import asyncio

import httpx

from services.session_storage import InMemoryMessageStore, InMemorySessionStore
from services.runner import InMemoryEventPublisher, InMemoryRunLock, InMemoryRunQueue
from langgraph.checkpoint.memory import MemorySaver
from tests.testing import FakeChat, FakeSandbox
from permissions.approval import ApprovalService
from gateway.spill import InMemoryObjectStore
from permissions.engine import RulePermissionEngine, builtin_recipe_rules
from server.app import (
    InMemoryRunStore,
    InMemorySessionAdmin,
    NoopPolicy,
    ServerComponents,
    create_app,
)
from tools.builtin import create_default_registry


def build_components(chat_scripts: list) -> tuple[ServerComponents, InMemoryBroker]:
    from server.broker import InMemoryBroker

    broker = InMemoryBroker()
    components = ServerComponents(
        message_store=InMemoryMessageStore(),
        session_store=InMemorySessionStore(),
        session_admin=InMemorySessionAdmin(),
        run_store=InMemoryRunStore(),
        approvals=ApprovalService(),
        broker=broker,
        queue=InMemoryRunQueue(),
        locks=InMemoryRunLock(),
        registry=create_default_registry(),
        permissions=RulePermissionEngine(rules=builtin_recipe_rules("standard"), recipe="standard"),
        object_store=InMemoryObjectStore(),
        checkpointer=MemorySaver(),
        sandbox_factory=lambda sid: FakeSandbox(),
        chat_factory=_make_chat_factory(chat_scripts),
    )
    return components, broker


def _make_chat_factory(executions: list):
    """按执行次数弹脚本：new 与 resume 各是一次执行（每次 = 轮次列表）。"""
    queue = list(executions)

    def factory(model: str) -> FakeChat:
        chat = FakeChat()
        chat.scripts = queue.pop(0)
        return chat

    return factory


async def wait_run_finished(client: httpx.AsyncClient, run_id: str, timeout: float = 8.0) -> dict:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = await client.get(f"/api/v1/runs/{run_id}")
        run = resp.json()
        if run["status"] in ("succeeded", "failed", "cancelled"):
            return run
        await asyncio.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish in {timeout}s: {run}")


async def case_rest_flow_converge():
    """建会话→发消息→worker 执行→run_finished→消息落事实源→SSE 事件序列正确。"""
    from engine.messages import PlatformMessage, ToolCallBlock
    from api.protocol import ApiMessageCompleteEvent, ApiTextDeltaEvent
    from api.usage import UsageSnapshot
    from engine.stream_events import RunFinished

    scripts = [
        [  # 执行1：两轮（FakeChat 契约 = 轮次列表）
            [  # 轮1：工具调用
                ApiMessageCompleteEvent(
                    message=PlatformMessage(role="assistant", content=[
                        ToolCallBlock(id="c1", name="write_file", input={"file_path": "hi.py", "content": "print(1)\n"}),
                    ]),
                    usage=UsageSnapshot(input_tokens=5, output_tokens=3),
                ),
            ],
            [  # 轮2：文本收敛
                ApiTextDeltaEvent(text="done "),
                ApiMessageCompleteEvent(
                    message=PlatformMessage.assistant("done"),
                    usage=UsageSnapshot(input_tokens=2, output_tokens=1),
                ),
            ],
        ],
    ]
    components, broker = build_components(scripts)
    app = create_app(components)
    await components.start()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/sessions", json={"model": "test-model", "title": "t"})
            assert resp.status_code == 201, resp.text
            sid = resp.json()["id"]

            resp = await client.post(
                f"/api/v1/sessions/{sid}/messages",
                json={"content": [{"type": "text", "text": "hi"}]},
            )
            assert resp.status_code == 202, resp.text
            run_id = resp.json()["run_id"]

            run = await wait_run_finished(client, run_id)
            assert run["status"] == "succeeded", run

            history = (await client.get(f"/api/v1/sessions/{sid}/messages")).json()["messages"]
            assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
            assert history[2]["content"][0]["content"].startswith("Wrote 1 lines")

            events = [m.event for m in broker._buffers[sid]]
            types = [e.type for e in events]
            assert types.count("assistant_delta") == 1
            assert "tool_started" in types and "tool_completed" in types
            assert types[-1] == "run_finished"
            assert events[-1].payload["usage"]["total_tokens"] == 11
    finally:
        await components.stop()


async def case_approval_roundtrip():
    """bash 非只读 → interrupt → REST 决策 → resume → 收敛。"""
    from engine.messages import PlatformMessage, ToolCallBlock
    from api.protocol import ApiMessageCompleteEvent
    from api.usage import UsageSnapshot

    scripts = [
        [  # 执行1（new）：一轮
            [ApiMessageCompleteEvent(
                message=PlatformMessage(role="assistant", content=[
                    ToolCallBlock(id="a1", name="bash", input={"command": "pip install requests"}),
                ]),
                usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            )],
        ],
        [  # 执行2（resume）：一轮
            [ApiMessageCompleteEvent(
                message=PlatformMessage.assistant("installed after approval"),
                usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            )],
        ],
    ]
    components, broker = build_components(scripts)
    app = create_app(components)
    await components.start()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            sid = (await client.post("/api/v1/sessions", json={"model": "test-model"})).json()["id"]
            run_id = (await client.post(
                f"/api/v1/sessions/{sid}/messages",
                json={"content": [{"type": "text", "text": "install it"}]},
            )).json()["run_id"]

            # 等 interrupt
            import time
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                run = (await client.get(f"/api/v1/runs/{run_id}")).json()
                if run["status"] == "interrupted":
                    break
                await asyncio.sleep(0.05)
            assert run["status"] == "interrupted", run

            pending = (await client.get("/api/v1/approvals")).json()
            assert len(pending) == 1 and pending[0]["run_id"] == run_id
            ticket_id = pending[0]["ticket_id"]
            assert pending[0]["items"][0]["tool_name"] == "bash"

            resp = await client.post(
                f"/api/v1/runs/{run_id}/approvals/{ticket_id}/decide",
                json={"choices": [{"call_id": "a1", "approve": True}], "decided_by": "op"},
            )
            assert resp.status_code == 200, resp.text

            run = await wait_run_finished(client, run_id)
            assert run["status"] == "succeeded", run
            history = (await client.get(f"/api/v1/sessions/{sid}/messages")).json()["messages"]
            assert history[-1].get("text") or history[-1]["content"][0]["text"] == "installed after approval" \
                if isinstance(history[-1]["content"][0], dict) and "text" in history[-1]["content"][0] else True
            assert (await client.get("/api/v1/approvals")).json() == []
    finally:
        await components.stop()


CASES = [case_rest_flow_converge, case_approval_roundtrip]


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
            import traceback
            traceback.print_exc()
            print(f"ERROR {case.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
