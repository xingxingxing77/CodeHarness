"""EngineDeps：节点的唯一依赖注入面（沿用 OpenHarness QueryContext 的单点注入模式）。

runner 在 config.configurable["deps"] 放入实例；节点经 deps_from() 取用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from langchain_core.runnables import RunnableConfig

from engine.types import AgentState, RunOutcome
from state.session_state import SessionState
from tools.base import ApprovalStore
from tools.base import ExecCtx, GatewayConfig, SandboxHandle, ToolGateway

from engine.messages import ImageBlock, PlatformMessage
from api.protocol import SupportsStreamingMessages


@dataclass(frozen=True)
class EngineConfig:
    model: str
    system_prompt: str = ""
    max_tokens: int = 8192
    max_turns: int = 200
    effort: str | None = None
    context_window_tokens: int | None = None
    auto_compact_threshold_tokens: int | None = None


class Compactor(Protocol):
    """三层上下文防御的事前/事后压缩策略（实现在 services，节点只依赖本面）。"""

    def estimate(self, messages: list[PlatformMessage], state: SessionState) -> int: ...

    def microcompact(
        self, messages: list[PlatformMessage], state: SessionState
    ) -> list[PlatformMessage] | None: ...

    async def summarize(
        self,
        messages: list[PlatformMessage],
        state: SessionState,
        emit: Callable[[Any], None],
    ) -> list[PlatformMessage] | None: ...


class VisionBridge(Protocol):
    """非视觉模型的图片降级通道（内部走 image_to_text 工具）。"""

    def supports(self, model: str) -> bool: ...

    async def describe(self, block: ImageBlock) -> str: ...


class PolicyEngine(Protocol):
    """平台策略引擎（替代 OpenHarness 本地 hook 子进程）。

    pre_tool_use = 网关闸门①（返回 Decision 即一票否决，None 放行）；
    post_tool_use = 收尾C（观察不改变结果）；post_run = STOP 类收尾。
    """

    async def pre_tool_use(self, call, ctx) -> object | None: ...

    async def post_tool_use(self, call, result, ctx) -> None: ...

    async def post_run(self, outcome: RunOutcome) -> None: ...


@dataclass
class EngineDeps:
    chat: SupportsStreamingMessages
    gateway: ToolGateway
    approvals: ApprovalStore
    compactor: Compactor
    policy: PolicyEngine
    sandbox: SandboxHandle
    cfg: EngineConfig
    gateway_cfg: GatewayConfig = field(default_factory=GatewayConfig)
    vision: VisionBridge | None = None


def make_config(
    deps: EngineDeps,
    *,
    tenant_id: str,
    session_id: str,
    run_id: str,
    event_sink: Callable[[Any], None] | None = None,
    thread_id: str | None = None,
) -> RunnableConfig:
    """thread_id 默认 = run_id：一次 run 一个 checkpointer 线程（图装配决策）。"""
    configurable: dict[str, Any] = {
        "deps": deps,
        "tenant_id": tenant_id,
        "session_id": session_id,
        "run_id": run_id,
        "thread_id": thread_id or run_id,
    }
    if event_sink is not None:
        configurable["event_sink"] = event_sink
    return {"configurable": configurable}


def deps_from(config: RunnableConfig | None) -> EngineDeps:
    return config["configurable"]["deps"]  # type: ignore[index]


def run_scope(config: RunnableConfig | None) -> tuple[str, str, str]:
    c = config["configurable"]  # type: ignore[index]
    return str(c["tenant_id"]), str(c["session_id"]), str(c["run_id"])


def build_exec_ctx(config: RunnableConfig | None, state: AgentState) -> ExecCtx:
    deps = deps_from(config)
    tenant_id, session_id, run_id = run_scope(config)
    return ExecCtx(
        tenant_id=tenant_id,
        session_id=session_id,
        run_id=run_id,
        sandbox=deps.sandbox,
        state=state["session_state"],
        cfg=deps.gateway_cfg,
    )
