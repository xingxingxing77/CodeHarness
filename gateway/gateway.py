"""SandboxToolGateway：ToolGateway 协议的实现（后端设计 §4 / 权限与沙箱设计）。

plan() = 闸门①策略 → ②查找 → ③校验 → ④权限（resolver 围栏 + 动态只读 + 配方），
纯检查、可重放、无副作用；
run() = 闸门⑤沙箱执行（唯一副作用入口）+ 收尾 ABC（offload / carryover / post hook），
永不 raise（I-B1），回执数 == auto_run 数且按 plan.order 可完整装配（I-B2）。
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import ValidationError

from engine.deps import PolicyEngine
from gateway.resolver import PathEscape, resolve_tool_path
from state.session_state import SessionState
from gateway.spill import ObjectStore, spill_if_oversize
from tools.base import BatchResult, Decision, ExecCtx, PreparedCall, ToolCall, ToolPlan, ToolResult

from permissions.engine import EvaluateInput, RulePermissionEngine
from tools.base import ToolRegistry

log = logging.getLogger(__name__)


class SandboxToolGateway:
    def __init__(
        self,
        registry: ToolRegistry,
        permissions: RulePermissionEngine,
        *,
        policy: PolicyEngine | None = None,
        store: ObjectStore | None = None,
    ) -> None:
        self._registry = registry
        self._permissions = permissions
        self._policy = policy
        self._store = store

    def tool_schemas(self) -> list[dict]:
        """Anthropic 格式工具声明（agent 节点构造请求）。"""
        return self._registry.to_api_schema()

    # -- 闸门①②③④：纯检查（可重放） --------------------------------------

    async def plan(self, calls: list[ToolCall], ctx: ExecCtx) -> ToolPlan:
        plan = ToolPlan(order=list(calls))
        for call in calls:
            # ① 策略卡点
            if self._policy is not None:
                policy_decision = await self._policy.pre_tool_use(call, ctx)
                if policy_decision is not None and policy_decision.kind == "deny":
                    plan.refused.append(self._denied(call, policy_decision.reason))
                    continue

            # ② 查找
            tool = self._registry.get(call.name)
            if tool is None:
                plan.refused.append(_error_result(call, f"Unknown tool: {call.name}"))
                continue

            # ③ 校验（失败详情原样喂回模型）
            try:
                parsed = tool.input_model.model_validate(call.input)
            except ValidationError as exc:
                plan.refused.append(_error_result(call, f"Invalid input for {call.name}: {exc}"))
                continue

            # ④ 权限：路径解析（uses_path 工具）→ 规则引擎裁决
            resolved = None
            if tool.uses_path:
                try:
                    resolved = resolve_tool_path(call.input, parsed, ctx.sandbox)
                except PathEscape as exc:
                    plan.refused.append(
                        _error_result(call, f"Permission denied for {call.name}: {exc}")
                    )
                    continue

            decision = self._permissions.evaluate(
                EvaluateInput(
                    tool_name=call.name,
                    read_only=tool.is_read_only(parsed),
                    resolved=resolved,
                    command=call.input.get("command") if tool.executes_commands else None,
                    executes_commands=tool.executes_commands,
                )
            )
            if decision.kind == "deny":
                plan.refused.append(self._denied(call, decision.reason))
            elif decision.kind == "require_confirm":
                plan.need_approval.append(
                    PreparedCall(call=call, parsed=parsed, resolved_path=resolved.container_path if resolved else None, decision=decision)
                )
            else:
                plan.auto_run.append(
                    PreparedCall(call=call, parsed=parsed, resolved_path=resolved.container_path if resolved else None, decision=decision)
                )
        return plan

    # -- 闸门⑤ + 收尾 ABC：唯一副作用入口 ----------------------------------

    async def run(self, plan: ToolPlan, ctx: ExecCtx) -> BatchResult:
        results: dict[str, ToolResult] = {}

        index = 0
        auto = plan.auto_run
        while index < len(auto):
            pc = auto[index]
            tool = self._registry.get(pc.call.name)
            if tool is None:  # 理论不可达（plan 已过滤）；防御
                results[pc.call.id] = _error_result(pc.call, f"Unknown tool: {pc.call.name}")
                index += 1
                continue

            if tool.parallel_safe:
                group: list[PreparedCall] = []
                while index < len(auto):
                    group_tool = self._registry.get(auto[index].call.name)
                    if group_tool is None or not group_tool.parallel_safe:
                        break
                    group.append(auto[index])
                    index += 1
                gathered = await asyncio.gather(
                    *(self._execute_one(pc_, tool, ctx) for pc_ in group),
                    return_exceptions=True,
                )
                for pc_, outcome in zip(group, gathered):
                    results[pc_.call.id] = self._wrap_outcome(pc_, outcome, ctx)
            else:
                results[pc.call.id] = await self._execute_one(pc, tool, ctx)
                index += 1

        # 收尾 A：卸载 + 收尾 B：carryover（失败不记）+ 收尾 C：post hook
        ordered: list[ToolResult] = []
        for pc in auto:
            result = results.get(pc.call.id)
            if result is None:  # I-B2 兜底：缺失补占位
                result = ToolResult(
                    tool_use_id=pc.call.id,
                    content=f"Tool {pc.call.name} produced no result",
                    is_error=True,
                )
            result = await self._spill(pc, result, ctx)
            if not result.is_error:
                self._carryover(pc, result, ctx.state)
            await self._post_hook(pc, result, ctx)
            ordered.append(result)

        return BatchResult(results=ordered, session_state=ctx.state)

    # -- 内部 ---------------------------------------------------------------

    async def _execute_one(self, pc: PreparedCall, tool, ctx: ExecCtx) -> ToolResult:
        # checkpoint 往返会把 parsed 的 pydantic 模型退化为 dict：按 schema 重校验恢复
        if not isinstance(pc.parsed, tool.input_model):
            pc.parsed = tool.input_model.model_validate(pc.parsed)
        result = await tool.execute(pc.parsed, ctx)
        result.tool_use_id = pc.call.id
        return result

    def _wrap_outcome(self, pc: PreparedCall, outcome: object, ctx: ExecCtx) -> ToolResult:
        if isinstance(outcome, BaseException):
            log.exception("tool execution raised: name=%s id=%s", pc.call.name, pc.call.id, exc_info=outcome)
            return ToolResult(
                tool_use_id=pc.call.id,
                content=f"Tool {pc.call.name} failed: {type(outcome).__name__}: {outcome}",
                is_error=True,
            )
        assert isinstance(outcome, ToolResult)
        return outcome

    async def _spill(self, pc: PreparedCall, result: ToolResult, ctx: ExecCtx) -> ToolResult:
        if self._store is None or result.is_error:
            return result
        spill = await spill_if_oversize(
            self._store,
            content=result.content,
            inline_limit_chars=ctx.cfg.inline_limit_chars,
            preview_chars=ctx.cfg.preview_chars,
            key=f"{ctx.tenant_id}/{ctx.session_id}/{ctx.run_id}/{pc.call.id}.txt",
        )
        if spill.uri is None:
            return result
        result.content = spill.content
        result.metadata["artifact_uri"] = spill.uri
        ctx.state.remember_artifact(spill.uri)
        return result

    def _carryover(self, pc: PreparedCall, result: ToolResult, state: SessionState) -> None:
        # 失败不记（权限与沙箱设计 / 内置工具规范）；仅记成功观察
        state.log_work(f"{pc.call.name}: {result.content[:120]}")
        if pc.resolved_path:
            state.remember_artifact(pc.resolved_path)

    async def _post_hook(self, pc: PreparedCall, result: ToolResult, ctx: ExecCtx) -> None:
        if self._policy is None:
            return
        try:
            await self._policy.post_tool_use(pc.call, result, ctx)
        except Exception:  # noqa: BLE001 — 观察者故障不阻断执行
            log.exception("post_tool_use hook raised")

    @staticmethod
    def _denied(call: ToolCall, reason: str) -> ToolResult:
        return _error_result(call, f"Permission denied for {call.name}: {reason}")


def _error_result(call: ToolCall, content: str) -> ToolResult:
    return ToolResult(
        tool_use_id=call.id,
        content=content,
        is_error=True,
        metadata={"tool_name": call.name},
    )
