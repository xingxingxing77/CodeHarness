"""图级冒烟验证（第四节）：编译后的 StateGraph + MemorySaver。

运行：python -m engine.smoke_graph
"""
from __future__ import annotations

import asyncio

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from engine.deps import EngineConfig, make_config
from engine.stream_events import RunFinished
from engine.graph import build_graph
from tests.testing import (
    FakeApprovals,
    FakeChat,
    FakeCompactor,
    FakeGateway,
    build_deps,
    make_plan_auto,
    make_plan_mixed,
)
from engine.types import make_initial_state
from engine.messages import PlatformMessage, ToolCallBlock
from api.errors import ContextOverflowFailure, RequestFailure
from api.protocol import ApiMessageCompleteEvent, ApiTextDeltaEvent
from api.usage import UsageSnapshot


def _tool_call_msg(*ids_names):
    return PlatformMessage(role="assistant", content=[
        ToolCallBlock(id=i, name=n, input={}) for i, n in ids_names
    ])


async def _run_collect(graph, state, config):
    """astream 双通道：custom 事件 + values 快照，返回 (events, final_state)。"""
    events: list = []
    final = None
    async for mode, chunk in graph.astream(state, config, stream_mode=["custom", "values"]):
        if mode == "custom":
            events.append(chunk)
        else:
            final = chunk
    return events, final


async def case_graph_converge():
    """两轮收敛：工具轮 + 文本轮；事件流以 RunFinished 结束；配对不变量。"""
    chat = FakeChat()
    chat.scripts = [
        [
            ApiTextDeltaEvent(text="thinking"),
            ApiMessageCompleteEvent(
                message=_tool_call_msg(("c1", "read_file"), ("c2", "read_file")),
                usage=UsageSnapshot(input_tokens=10, output_tokens=5),
                stop_reason="tool_use",
            ),
        ],
        [
            ApiMessageCompleteEvent(
                message=PlatformMessage.assistant("done"),
                usage=UsageSnapshot(input_tokens=3, output_tokens=2),
                stop_reason="end_turn",
            ),
        ],
    ]
    deps = build_deps(chat, FakeGateway(make_plan_auto))
    graph = build_graph(MemorySaver())
    config = make_config(deps, tenant_id="t", session_id="s", run_id="run-1")
    state = make_initial_state([PlatformMessage.user("hi")], max_tokens=1024)

    events, final = await _run_collect(graph, state, config)
    assert final["route"] == "proceed" and final["turn"] == 2, final
    msgs = final["messages"]
    call_ids = {b.id for b in msgs[1].tool_calls}
    result_ids = {b.tool_use_id for b in msgs[2].tool_results}
    assert call_ids == result_ids
    assert final["usage_total"].total_tokens == 20
    assert isinstance(events[-1], RunFinished)
    assert chat.scripts == []  # 两段脚本全部消费


async def case_graph_clamp():
    """clamp 循环在图内完成：agent(拒)→recover→agent(成)。"""
    chat = FakeChat()
    chat.scripts = [
        RequestFailure("invalid_request: max_tokens is too large; the model supports at most 2000 completion tokens"),
        [ApiMessageCompleteEvent(message=PlatformMessage.assistant("ok"), usage=UsageSnapshot(input_tokens=1, output_tokens=1))],
    ]
    deps = build_deps(chat, FakeGateway(make_plan_auto), cfg=EngineConfig(model="m", max_tokens=8000))
    graph = build_graph(MemorySaver())
    config = make_config(deps, tenant_id="t", session_id="s", run_id="run-2")
    state = make_initial_state([PlatformMessage.user("hi")], max_tokens=8000)

    _, final = await _run_collect(graph, state, config)
    assert final["route"] == "proceed", final
    assert final["effective_max_tokens"] == 2000
    assert final["turn"] == 1  # clamp 不耗轮


async def case_graph_reactive():
    """reactive 压缩在图内完成：agent(溢出)→recover→compact(force)→agent(成)。"""
    chat = FakeChat()
    chat.scripts = [
        ContextOverflowFailure("prompt too long"),
        [ApiMessageCompleteEvent(message=PlatformMessage.assistant("after"), usage=UsageSnapshot(input_tokens=1, output_tokens=1))],
    ]
    deps = build_deps(
        chat, FakeGateway(make_plan_auto), compactor=FakeCompactor(est=0),
        cfg=EngineConfig(model="m", auto_compact_threshold_tokens=100),
    )
    graph = build_graph(MemorySaver())
    config = make_config(deps, tenant_id="t", session_id="s", run_id="run-3")
    state = make_initial_state([PlatformMessage.user("hi")], max_tokens=1024)

    _, final = await _run_collect(graph, state, config)
    assert final["route"] == "proceed", final
    assert final["reactive_compact_done"] is True
    assert final["messages"][0].text == "[summary]"  # 压缩替换生效
    assert final["turn"] == 1


async def case_graph_max_turns():
    """轮次熔断：max_turns=1 首轮就产工具调用 → fail(max_turns_exceeded)，工具不执行。"""
    chat = FakeChat()
    chat.scripts = [
        [ApiMessageCompleteEvent(
            message=_tool_call_msg(("c1", "read_file")),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
        )],
        # 若熔断失效会再次进入 agent，FakeChat 将弹出哨兵并使 run 报错——据此暴露
        RuntimeError("should not be consumed: graph attempted another agent turn"),
    ]
    gateway = FakeGateway(make_plan_auto)
    deps = build_deps(chat, gateway, cfg=EngineConfig(model="m", max_turns=1))
    graph = build_graph(MemorySaver())
    config = make_config(deps, tenant_id="t", session_id="s", run_id="run-4")
    state = make_initial_state([PlatformMessage.user("hi")], max_tokens=1024)

    _, final = await _run_collect(graph, state, config)
    assert final["route"] == "fail", final
    assert final["error"].code == "max_turns_exceeded"
    assert gateway.run_calls == 0  # 工具从未执行
    assert chat.scripts  # 第二段哨兵脚本未被消费


async def case_graph_interrupt_resume():
    """真实 interrupt 挂起 → Command(resume) 续跑：批准项执行、协议闭环完整。"""
    chat = FakeChat()
    chat.scripts = [
        [ApiMessageCompleteEvent(
            message=_tool_call_msg(("a1", "bash"), ("a2", "read_file")),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
        )],
        [ApiMessageCompleteEvent(
            message=PlatformMessage.assistant("finished after approval"),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
        )],
    ]
    gateway = FakeGateway(make_plan_mixed)
    deps = build_deps(chat, gateway, approvals=FakeApprovals())
    graph = build_graph(MemorySaver())
    config = make_config(deps, tenant_id="t", session_id="s", run_id="run-5")
    state = make_initial_state([PlatformMessage.user("hi")], max_tokens=1024)

    result = await graph.ainvoke(state, config)
    interrupts = result.get("__interrupt__")
    assert interrupts, f"expected interrupt, got {result.get('route')}"
    payload = interrupts[0].value
    assert payload["items"][0]["call_id"] == "a1"
    assert payload["ticket_id"] == "ticket-1"

    decision = {
        "ticket_id": payload["ticket_id"],
        "choices": [{"call_id": "a1", "approve": True, "reason": "approved by operator"}],
    }
    final = await graph.ainvoke(Command(resume=decision), config)
    assert final["route"] == "proceed" and final["turn"] == 2, final
    results = final["messages"][2].tool_results
    assert {r.tool_use_id for r in results} == {"a1", "a2"}  # 批准的 a1 与自动的 a2 都有回执
    assert gateway.run_calls == 1
    assert final["messages"][-1].text == "finished after approval"
    assert chat.scripts == []


CASES = [
    case_graph_converge,
    case_graph_clamp,
    case_graph_reactive,
    case_graph_max_turns,
    case_graph_interrupt_resume,
]


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
