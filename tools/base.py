"""ToolDef 契约与工具注册表（内置工具规范 §1）。

工具实现只依赖 ExecCtx（sandbox/state/cfg），不触碰 docker/langchain；
五闸门网关（pipeline）消费本注册表产出 ToolPlan。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel



@dataclass(frozen=True)
class ToolDef:
    """一个工具的完整声明。"""

    name: str
    description: str
    input_model: type[BaseModel]
    execute: Callable[[BaseModel, ExecCtx], Awaitable[ToolResult]]
    parallel_safe: bool = True
    is_read_only: Callable[[BaseModel], bool] = lambda _parsed: True
    executes_commands: bool = False  # cmd_* 规则仅对此类工具生效
    uses_path: bool = False          # 入参含路径字段（闸门④需 resolve）
    ui_kind: str | None = None       # diff | terminal | file | None

    def input_schema(self) -> dict[str, Any]:
        """Anthropic input_schema（pydantic JSON Schema 子集）。"""
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        for props in schema.get("properties", {}).values():
            props.pop("title", None)
        return schema


class ToolRegistry:
    """工具注册表：注册 / 查找 / 供应商 schema 导出。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def to_api_schema(self) -> list[dict[str, Any]]:
        """Anthropic 格式工具声明（agent 节点构造请求用）。"""
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema()}
            for t in self._tools.values()
        ]


# ---------------------------------------------------------------------------
# 工具执行契约（自 gateway/types.py 迁入，P0）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class UiPayload:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    tool_use_id: str
    content: str                      # 给模型（token 受控，可能已卸载为引用）
    is_error: bool = False
    ui: UiPayload | None = None       # 给前端，永不进模型上下文
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    kind: Literal["allow", "deny", "require_confirm"]
    reason: str = ""
    risk_level: str = "medium"

    @staticmethod
    def allow() -> "Decision":
        return Decision("allow")

    @staticmethod
    def deny(reason: str) -> "Decision":
        return Decision("deny", reason=reason)

    @staticmethod
    def require_confirm(reason: str, risk_level: str = "medium") -> "Decision":
        return Decision("require_confirm", reason=reason, risk_level=risk_level)


class SandboxFileNotFound(Exception):
    """沙箱内目标文件不存在（工具转 is_error 回执）。"""


@dataclass(frozen=True)
class ExecResult:
    """sandbox.exec 的结果（权限与沙箱设计 §2.2）。"""

    exit_code: int
    stdout: str
    stderr: str
    truncated: bool = False
    duration_ms: int = 0


class SandboxHandle(Protocol):
    """契约⑦沙箱句柄（Docker per-session，非 root / --network none / 全 jail）。

    工具实现只依赖本协议，拿不到 docker 客户端；路径参数一律为
    container_path（/workspace/...），物理映射是沙箱实现的私有细节。
    """

    @property
    def session_id(self) -> str: ...

    @property
    def root(self) -> str: ...

    async def exec(
        self,
        argv: list[str],
        *,
        cwd: str = "/workspace",
        env: dict[str, str] | None = None,
        timeout_s: float = 120.0,
        output_cap: int = 1_048_576,
    ) -> ExecResult: ...

    async def read_file(self, container_path: str, *, cap: int = 2_097_152) -> bytes: ...

    async def write_file(self, container_path: str, data: bytes) -> None: ...

    async def destroy(self) -> None: ...


@dataclass(frozen=True)
class GatewayConfig:
    inline_limit_chars: int = 8_000
    preview_chars: int = 1_500
    tool_timeout_seconds: float = 120.0


@dataclass(frozen=True)
class ExecCtx:
    tenant_id: str
    session_id: str
    run_id: str
    sandbox: SandboxHandle
    state: SessionState
    cfg: GatewayConfig


@dataclass
class PreparedCall:
    call: ToolCall
    parsed: Any = None
    resolved_path: str | None = None
    decision: Decision = field(default_factory=Decision.allow)


@dataclass
class ToolPlan:
    order: list[ToolCall]                          # 原始调用顺序（execute 出口按此装配回执）
    auto_run: list[PreparedCall] = field(default_factory=list)
    need_approval: list[PreparedCall] = field(default_factory=list)
    refused: list[ToolResult] = field(default_factory=list)   # 已是终态回执


@dataclass
class BatchResult:
    results: list[ToolResult]                      # 仅 auto_run 的执行结果
    session_state: SessionState                    # carryover 更新后的快照


class ToolGateway(Protocol):
    def tool_schemas(self) -> list[dict[str, Any]]:
        """Anthropic 格式工具声明，供 agent 节点构造请求。"""
        ...

    async def plan(self, calls: list[ToolCall], ctx: ExecCtx) -> ToolPlan:
        """闸门①②③。纯检查、可重放、无副作用。"""
        ...

    async def run(self, plan: ToolPlan, ctx: ExecCtx) -> BatchResult:
        """闸门⑤+收尾ABC。唯一副作用入口，永不 raise。"""
        ...


# ---------------------------------------------------------------------------
# 审批（契约⑤）：节点侧只依赖 payload/decision 结构与 ApprovalStore 最小面
# ---------------------------------------------------------------------------

class ApprovalItem(BaseModel):
    call_id: str
    tool_name: str
    reason: str = ""
    risk_level: str = "medium"
    input_preview: str = ""


class ApprovalPayload(BaseModel):
    ticket_id: str
    run_id: str = ""
    items: list[ApprovalItem]


class ApprovalChoice(BaseModel):
    call_id: str
    approve: bool
    reason: str = ""


class ApprovalDecision(BaseModel):
    ticket_id: str
    choices: list[ApprovalChoice]


class ApprovalStore(Protocol):
    def ensure_ticket(self, plan: ToolPlan, run_id: str) -> str:
        """幂等建单：键 = hash(run_id, sorted(call_ids))，重放返回同一 ticket_id。"""
        ...
