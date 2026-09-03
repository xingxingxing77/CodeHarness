"""网关端到端冒烟：闸门①②③④ + run⑤ + 并行分区 + 卸载 + 记账（权限与沙箱设计验收子集）。

运行：python -m gateway.smoke_gateway
"""

from __future__ import annotations

import asyncio

from tests.testing import FakeSandbox
from gateway.gateway import SandboxToolGateway
from state.session_state import SessionState
from gateway.spill import InMemoryObjectStore
from tools.base import ExecCtx, GatewayConfig, ToolCall
from permissions.engine import RulePermissionEngine, builtin_recipe_rules
from tools.builtin import create_default_registry


def make_gateway(recipe: str = "standard", *, store=None, inline_limit: int = 8_000):
    rules = builtin_recipe_rules(recipe)
    gateway = SandboxToolGateway(
        create_default_registry(),
        RulePermissionEngine(rules=rules, recipe=recipe),
        store=store or InMemoryObjectStore(),
    )
    return gateway, GatewayConfig(inline_limit_chars=inline_limit, preview_chars=200)


def make_ctx(sandbox, cfg) -> ExecCtx:
    return ExecCtx(
        tenant_id="t",
        session_id="s",
        run_id="r",
        sandbox=sandbox,
        state=SessionState(),
        cfg=cfg,
    )


async def case_plan_all_allow_and_run():
    """闸门④配方默认：工作区写 ALLOW；run 执行 + carryover 记账。"""
    gateway, cfg = make_gateway()
    sandbox = FakeSandbox()
    ctx = make_ctx(sandbox, cfg)

    plan = await gateway.plan(
        [
            ToolCall(id="c1", name="write_file", input={"file_path": "a.py", "content": "x = 1\n"}),
            ToolCall(id="c2", name="read_file", input={"file_path": "a.py"}),
        ],
        ctx,
    )
    assert plan.need_approval == [] and plan.refused == [], (plan.need_approval, plan.refused)
    assert [pc.call.id for pc in plan.auto_run] == ["c1", "c2"]

    batch = await gateway.run(plan, ctx)
    assert [r.tool_use_id for r in batch.results] == ["c1", "c2"]  # I-B2：顺序一致
    assert not batch.results[0].is_error and "new file" in batch.results[0].content
    assert "     1\tx = 1" in batch.results[1].content
    # carryover：成功记账
    assert ctx.state.work_log and ctx.state.work_log[-1].startswith("read_file:")
    assert "/workspace/a.py" in ctx.state.active_artifacts


async def case_gate_refusals():
    """②未知工具 / ③参数非法 / ④路径围栏 —— 三类拒绝转终态回执。"""
    gateway, cfg = make_gateway()
    sandbox = FakeSandbox()
    ctx = make_ctx(sandbox, cfg)

    plan = await gateway.plan(
        [
            ToolCall(id="u1", name="no_such_tool", input={}),
            ToolCall(id="v1", name="bash", input={}),  # 缺 command
            ToolCall(id="p1", name="read_file", input={"file_path": "../../etc/passwd"}),
            ToolCall(id="ok1", name="read_file", input={"file_path": "a.py"}),
        ],
        ctx,
    )
    refused_by_id = {r.tool_use_id: r for r in plan.refused}
    assert set(refused_by_id) == {"u1", "v1", "p1"}
    assert "Unknown tool" in refused_by_id["u1"].content
    assert "Invalid input for bash" in refused_by_id["v1"].content
    assert "Permission denied for read_file" in refused_by_id["p1"].content
    assert [pc.call.id for pc in plan.auto_run] == ["ok1"]


async def case_bash_requires_approval_and_dangerous_deny():
    """标准配方：非只读命令 REQUIRE_CONFIRM；危险清单 DENY；纯读放行。"""
    gateway, cfg = make_gateway()
    sandbox = FakeSandbox()
    ctx = make_ctx(sandbox, cfg)

    plan = await gateway.plan(
        [
            ToolCall(id="r1", name="bash", input={"command": "git status"}),
            ToolCall(id="w1", name="bash", input={"command": "pip install requests"}),
            ToolCall(id="d1", name="bash", input={"command": "sudo rm -rf /"}),
        ],
        ctx,
    )
    assert [pc.call.id for pc in plan.auto_run] == ["r1"]
    assert [pc.call.id for pc in plan.need_approval] == ["w1"]
    assert plan.need_approval[0].decision.risk_level == "medium"
    refused = {r.tool_use_id: r for r in plan.refused}
    assert "d1" in refused and refused["d1"].is_error


async def case_cautious_recipe():
    """谨慎配方：非只读一律 REQUIRE_CONFIRM(high)。"""
    gateway, cfg = make_gateway(recipe="cautious")
    sandbox = FakeSandbox()
    ctx = make_ctx(sandbox, cfg)
    plan = await gateway.plan(
        [ToolCall(id="w", name="write_file", input={"file_path": "a.py", "content": "x"})],
        ctx,
    )
    assert len(plan.need_approval) == 1 and plan.need_approval[0].decision.risk_level == "high"


async def case_parallel_partition_and_order():
    """并行分区：回执按 auto_run 顺序齐全（I-B2）。"""
    gateway, cfg = make_gateway()
    sandbox = FakeSandbox()
    ctx = make_ctx(sandbox, cfg)

    plan = await gateway.plan(
        [
            ToolCall(id="g1", name="read_file", input={"file_path": "a.py"}),
            ToolCall(id="s1", name="write_file", input={"file_path": "b.py", "content": "b\n"}),
            ToolCall(id="g2", name="read_file", input={"file_path": "a.py"}),
        ],
        ctx,
    )
    # 闸门④后 a.py 尚不存在：read 失败回执，但流程语义不变
    batch = await gateway.run(plan, ctx)
    assert [r.tool_use_id for r in batch.results] == ["g1", "s1", "g2"]


async def case_spill_oversize_output():
    """bash 大输出：超 inline_limit → 卸载为 URI+预览，原文进对象存储。"""
    store = InMemoryObjectStore()
    gateway, cfg = make_gateway(store=store, inline_limit=200)
    sandbox = FakeSandbox()
    ctx = make_ctx(sandbox, cfg)

    big = "line-" + "x" * 80 + "\n" + "y" * 500
    from tools.base import ExecResult

    sandbox.canned.append(ExecResult(exit_code=0, stdout=big, stderr=""))

    plan = await gateway.plan(
        [ToolCall(id="b1", name="bash", input={"command": "cat big.txt"})], ctx
    )
    batch = await gateway.run(plan, ctx)
    result = batch.results[0]
    assert not result.is_error
    assert "Full output saved to: memory://" in result.content
    assert "chars omitted" in result.content and "Preview:" in result.content
    assert any(uri.endswith("b1.txt") for uri in store.objects)


async def case_failure_not_recorded_in_carryover():
    """carryover 失败不记：错误回执不进 work_log。"""
    gateway, cfg = make_gateway()
    sandbox = FakeSandbox()
    ctx = make_ctx(sandbox, cfg)
    plan = await gateway.plan(
        [ToolCall(id="m1", name="read_file", input={"file_path": "nope.py"})], ctx
    )
    batch = await gateway.run(plan, ctx)
    assert batch.results[0].is_error
    assert ctx.state.work_log == []


CASES = [
    case_plan_all_allow_and_run,
    case_gate_refusals,
    case_bash_requires_approval_and_dangerous_deny,
    case_cautious_recipe,
    case_parallel_partition_and_order,
    case_spill_oversize_output,
    case_failure_not_recorded_in_carryover,
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
