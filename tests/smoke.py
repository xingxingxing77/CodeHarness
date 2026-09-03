"""节点级冒烟验证：用 Fake 依赖直接驱动节点，覆盖关键不变量。

图级冒烟见 smoke_graph.py。运行：python -m engine.smoke
"""
from __future__ import annotations

import asyncio

from engine.deps import EngineConfig, make_config
from engine.stream_events import RunFinished, ToolCompleted, ToolStarted
from engine.nodes.agent import agent_node
from engine.nodes.compact import compact_node
from engine.nodes.finalize import finalize_node
from engine.nodes.preprocess import preprocess_node
from engine.nodes.recover import recover_node
from engine.nodes.tools_approval import tools_approval_node
from engine.nodes.tools_execute import tools_execute_node
from engine.nodes.tools_prepare import tools_prepare_node
from tests.testing import (
    FakeApprovals,
    FakeChat,
    FakeCompactor,
    FakeGateway,
    FakePolicy,
    FakeVision,
    LeakGateway,
    apply_update,
    build_deps,
    make_plan_auto,
    make_plan_mixed,
)
from engine.types import ReplaceMessages, make_initial_state
from tools.base import ToolCall
from engine.messages import ImageBlock, PlatformMessage, TextBlock, ToolCallBlock
from api.errors import ContextOverflowFailure, RequestFailure
from api.protocol import ApiMessageCompleteEvent, ApiTextDeltaEvent
from api.usage import UsageSnapshot


# --------------------------------------------------------------------------- cases
async def case_converge_loop():
    """tool_calls 为空即收敛；I-A3 配对不变量；usage 累计。"""
    chat = FakeChat()
    chat.scripts = [
        [  # 轮1：两个工具调用
            ApiTextDeltaEvent(text="thinking"),
            ApiMessageCompleteEvent(
                message=PlatformMessage(role="assistant", content=[
                    ToolCallBlock(id="c1", name="read_file", input={"path": "a"}),
                    ToolCallBlock(id="c2", name="read_file", input={"path": "b"}),
                ]),
                usage=UsageSnapshot(input_tokens=10, output_tokens=5),
                stop_reason="tool_use",
            ),
        ],
        [  # 轮2：纯文本 → 收敛
            ApiMessageCompleteEvent(
                message=PlatformMessage.assistant("done"),
                usage=UsageSnapshot(input_tokens=3, output_tokens=2),
                stop_reason="end_turn",
            ),
        ],
    ]
    gateway = FakeGateway(make_plan_auto)
    deps = build_deps(chat, gateway)
    events: list = []
    config = make_config(deps, tenant_id="t", session_id="s", run_id="r", event_sink=events.append)

    state = make_initial_state([PlatformMessage.user("hi")], max_tokens=1024)
    state = apply_update(state, await preprocess_node(state, config))
    state = apply_update(state, await compact_node(state, config))
    state = apply_update(state, await agent_node(state, config))
    assert state["route"] == "proceed" and state["turn"] == 1, state
    assert len(state["messages"][-1].tool_calls) == 2

    state = apply_update(state, await tools_prepare_node(state, config))
    state = apply_update(state, await tools_approval_node(state, config))  # 无审批 → {}
    state = apply_update(state, await tools_execute_node(state, config))

    # I-A3：每个 tool_call 都有配对 tool_result
    last = state["messages"][-1]
    call_ids = [b.id for b in state["messages"][-2].tool_calls]
    result_ids = [b.tool_use_id for b in last.tool_results]
    assert sorted(call_ids) == sorted(result_ids), (call_ids, result_ids)
    assert last.role == "user"

    state = apply_update(state, await compact_node(state, config))
    state = apply_update(state, await agent_node(state, config))
    assert state["turn"] == 2 and state["messages"][-1].tool_calls == []
    assert state["usage_total"].total_tokens == 20  # 10+5+3+2

    state = apply_update(state, await finalize_node(state, config))
    assert isinstance(events[-1], RunFinished)
    assert any(isinstance(e, ToolStarted) for e in events)
    assert any(isinstance(e, ToolCompleted) and e.tool_name == "read_file" for e in events)
    assert isinstance(deps.policy, FakePolicy) and deps.policy.outcomes[-1].turns == 2


async def case_empty_response_guard():
    chat = FakeChat()
    chat.scripts = [[ApiMessageCompleteEvent(message=PlatformMessage(role="assistant", content=[]), usage=UsageSnapshot())]]
    deps = build_deps(chat, FakeGateway(make_plan_auto))
    config = make_config(deps, tenant_id="t", session_id="s", run_id="r")
    state = make_initial_state([PlatformMessage.user("hi")], max_tokens=1024)
    out = await agent_node(state, config)
    assert out["route"] == "fail" and out["error"].code == "empty_response", out


async def case_clamp_retry():
    chat = FakeChat()
    chat.scripts = [
        RequestFailure("invalid_request: max_tokens is too large; the model supports at most 2000 completion tokens"),
        [ApiMessageCompleteEvent(message=PlatformMessage.assistant("ok"), usage=UsageSnapshot(input_tokens=1, output_tokens=1))],
    ]
    deps = build_deps(chat, FakeGateway(make_plan_auto), cfg=EngineConfig(model="m", max_tokens=8000))
    events: list = []
    config = make_config(deps, tenant_id="t", session_id="s", run_id="r", event_sink=events.append)
    state = make_initial_state([PlatformMessage.user("hi")], max_tokens=8000)

    out = await agent_node(state, config)
    assert out["route"] == "clamp_retry" and out["effective_max_tokens"] == 2000, out
    state = apply_update(state, out)
    # 不消耗业务轮次
    assert state["turn"] == 0
    rec = await recover_node(state, config)
    assert rec["route"] == "proceed"
    state = apply_update(state, rec)
    out2 = await agent_node(state, config)
    assert out2["route"] == "proceed"
    assert any("max_tokens" in getattr(e, "message", "") for e in events)


async def case_reactive_compact_once():
    chat = FakeChat()
    chat.scripts = [
        ContextOverflowFailure("prompt too long"),
        [ApiMessageCompleteEvent(message=PlatformMessage.assistant("after"), usage=UsageSnapshot(input_tokens=1, output_tokens=1))],
    ]
    compactor = FakeCompactor(est=999)
    deps = build_deps(chat, FakeGateway(make_plan_auto), compactor=compactor,
                      cfg=EngineConfig(model="m", auto_compact_threshold_tokens=100))
    config = make_config(deps, tenant_id="t", session_id="s", run_id="r")
    state = make_initial_state([PlatformMessage.user("hi")], max_tokens=1024)

    out = await agent_node(state, config)
    assert out["route"] == "reactive_compact", out
    state = apply_update(state, out)
    cout = await compact_node(state, config)  # force：即便未过阈值也压缩
    assert cout["reactive_compact_done"] is True and cout["route"] == "proceed"
    assert isinstance(cout["messages"], ReplaceMessages)
    assert cout["messages"].messages[0].text == "[summary]"


async def case_approval_flow():
    """prepare→approval(interrupt)→execute：批准项并入 auto，拒绝项转回执。"""
    from engine.nodes import tools_approval as ta

    calls = [
        ToolCall(id="a1", name="bash", input={"command": "rm -rf /"}),
        ToolCall(id="a2", name="read_file", input={"path": "x"}),
    ]
    gateway = FakeGateway(make_plan_mixed)
    chat = FakeChat()
    deps = build_deps(chat, gateway, approvals=FakeApprovals())
    config = make_config(deps, tenant_id="t", session_id="s", run_id="r")

    state = make_initial_state([
        PlatformMessage(role="assistant", content=[
            ToolCallBlock(id="a1", name="bash", input={"command": "rm -rf /"}),
            ToolCallBlock(id="a2", name="read_file", input={"path": "x"}),
        ])
    ], max_tokens=1024)

    state = apply_update(state, await tools_prepare_node(state, config))
    assert len(state["pending_plan"].need_approval) == 1

    # 模拟 interrupt 恢复：批准 a1
    captured: dict = {}

    def fake_interrupt(payload):
        captured["payload"] = payload
        return {"ticket_id": payload["ticket_id"], "choices": [{"call_id": "a1", "approve": True}]}

    orig = ta.interrupt
    ta.interrupt = fake_interrupt
    try:
        aout = await tools_approval_node(state, config)
    finally:
        ta.interrupt = orig
    assert captured["payload"]["items"][0]["tool_name"] == "bash"
    assert captured["payload"]["items"][0]["risk_level"] == "high"
    plan = aout["pending_plan"]
    assert len(plan.auto_run) == 2 and plan.need_approval == []  # a1 批准后并入 auto

    state = apply_update(state, aout)
    state = apply_update(state, await tools_execute_node(state, config))
    results = state["messages"][-1].tool_results
    assert {r.tool_use_id for r in results} == {"a1", "a2"}
    assert gateway.run_calls == 1

    # 拒绝路径：a1 不批 → 转 refused 回执，run 不执行它
    def fake_interrupt_deny(payload):
        return {"ticket_id": payload["ticket_id"], "choices": [{"call_id": "a1", "approve": False, "reason": "nope"}]}

    state2 = make_initial_state(state["messages"][:1], max_tokens=1024)
    state2 = apply_update(state2, await tools_prepare_node(state2, config))
    ta.interrupt = fake_interrupt_deny
    try:
        aout2 = await tools_approval_node(state2, config)
    finally:
        ta.interrupt = orig
    plan2 = aout2["pending_plan"]
    assert len(plan2.auto_run) == 1 and len(plan2.refused) == 1
    assert plan2.refused[0].is_error and "nope" in plan2.refused[0].content


async def case_image_preprocess():
    vision = FakeVision()
    chat = FakeChat()
    deps = build_deps(chat, FakeGateway(make_plan_auto), vision=vision)
    config = make_config(deps, tenant_id="t", session_id="s", run_id="r")
    state = make_initial_state([
        PlatformMessage(role="user", content=[TextBlock(text="look"), ImageBlock(media_type="image/png", data="AAA")])
    ], max_tokens=1024)
    out = await preprocess_node(state, config)
    replaced = out["messages"].messages[0]
    assert isinstance(replaced.content[1], TextBlock)
    assert replaced.content[1].text == "<desc image/png>"


async def case_i_b2_missing_result_backfill():
    """网关契约被违反（少回一条）时，execute 仍按 order 补齐，不破配对闭环。"""
    chat = FakeChat()
    deps = build_deps(chat, LeakGateway())
    config = make_config(deps, tenant_id="t", session_id="s", run_id="r")
    state = make_initial_state([
        PlatformMessage(role="assistant", content=[
            ToolCallBlock(id="m1", name="read_file", input={}),
            ToolCallBlock(id="m2", name="read_file", input={}),
        ])
    ], max_tokens=1024)
    state = apply_update(state, await tools_prepare_node(state, config))
    state = apply_update(state, await tools_execute_node(state, config))
    results = state["messages"][-1].tool_results
    assert [r.tool_use_id for r in results] == ["m1", "m2"]
    assert results[1].is_error and "no result" in results[1].content


CASES = [
    case_converge_loop,
    case_empty_response_guard,
    case_clamp_retry,
    case_reactive_compact_once,
    case_approval_flow,
    case_image_preprocess,
    case_i_b2_missing_result_backfill,
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
