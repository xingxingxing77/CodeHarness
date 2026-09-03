"""共享测试替身：节点/图冒烟共用（不进入生产导入路径）。"""
from __future__ import annotations

from typing import Any

from engine.deps import EngineConfig, EngineDeps
from engine.types import AgentState, merge_messages
from state.session_state import SessionState
from tools.base import BatchResult, Decision, ExecResult, PreparedCall, ToolCall, ToolPlan, ToolResult

from engine.messages import PlatformMessage
from api.protocol import ApiMessageRequest
from api.usage import UsageSnapshot


class FakeSandbox:
    """内存沙箱：文件系统 dict + 最小 rg 模拟 + 可编程 exec。"""

    def __init__(self) -> None:
        import tempfile

        self._root = tempfile.mkdtemp(prefix="ch-fake-sbx-")
        self.files: dict[str, bytes] = {}  # container_path(/workspace/...) → bytes
        self.canned: list[ExecResult] = []
        self.exec_handler: Any = None  # callable(argv, *, timeout_s, cwd) -> ExecResult | None
        self.exec_calls: list[list[str]] = []

    @property
    def session_id(self) -> str:
        return "sess"

    @property
    def root(self) -> str:
        return self._root

    async def read_file(self, container_path: str, *, cap: int = 2_097_152) -> bytes:
        from tools.base import SandboxFileNotFound

        if container_path not in self.files:
            raise SandboxFileNotFound(container_path)
        return self.files[container_path]

    async def write_file(self, container_path: str, data: bytes) -> None:
        self.files[container_path] = bytes(data)

    async def destroy(self) -> None:
        self.files.clear()

    async def exec(
        self,
        argv: list[str],
        *,
        cwd: str = "/workspace",
        env: dict[str, str] | None = None,
        timeout_s: float = 120.0,
        output_cap: int = 1_048_576,
    ) -> ExecResult:
        self.exec_calls.append(list(argv))
        if self.exec_handler is not None:
            scripted = self.exec_handler(argv, timeout_s=timeout_s, cwd=cwd)
            if scripted is not None:
                return scripted
        if self.canned:
            return self.canned.pop(0)
        return self._simulate(argv)

    # -- 内建最小 rg 模拟 ---------------------------------------------------
    def _simulate(self, argv: list[str]) -> ExecResult:
        import fnmatch as _fnmatch
        import re as _re

        if not argv or argv[0] != "rg":
            return ExecResult(exit_code=0, stdout="", stderr="")

        if len(argv) > 1 and argv[1] == "--files":
            rel = argv[2] if len(argv) > 2 else "."
            prefix = "" if rel in (".", "") else rel.strip("/") + "/"
            out = "\n".join(
                p for p in sorted(self.files) if p.startswith(f"/workspace/{prefix}")
            )
            return ExecResult(exit_code=0, stdout=out, stderr="")

        if len(argv) > 1 and argv[1] == "-n":
            args = argv[2:]
            glob = None
            if "--glob" in args:
                i = args.index("--glob")
                glob = args[i + 1]
                del args[i : i + 2]
            pattern = args[0] if args else ""
            path = args[1] if len(args) > 1 else "."
            try:
                rx = _re.compile(pattern)
            except _re.error as exc:
                return ExecResult(exit_code=2, stdout="", stderr=f"rg: regex error: {exc}")
            hits: list[str] = []
            for full_path, data in sorted(self.files.items()):
                rel_path = full_path.removeprefix("/workspace/")
                if path not in (".", "") and not (
                    rel_path == path or rel_path.startswith(path.rstrip("/") + "/")
                ):
                    continue
                if glob and not _fnmatch.fnmatch(rel_path, glob):
                    continue
                for lineno, line in enumerate(
                    data.decode("utf-8", errors="replace").splitlines(), 1
                ):
                    if rx.search(line):
                        hits.append(f"{rel_path}:{lineno}: {line}")
            if not hits:
                return ExecResult(exit_code=1, stdout="", stderr="")
            return ExecResult(exit_code=0, stdout="\n".join(hits[:2000]), stderr="")

        return ExecResult(exit_code=0, stdout="", stderr="")


class FakeChat:
    """脚本化：每次 stream_message 弹出一段预置事件/异常。"""

    def __init__(self) -> None:
        self.scripts: list[Any] = []
        self.requests: list[ApiMessageRequest] = []

    async def stream_message(self, request: ApiMessageRequest):
        self.requests.append(request)
        script = self.scripts.pop(0)
        if isinstance(script, Exception):
            raise script
        for event in script:
            yield event


class FakeGateway:
    def __init__(self, plan_factory) -> None:
        self._plan_factory = plan_factory
        self.run_calls = 0

    def tool_schemas(self):
        return [{"name": "read_file", "description": "", "input_schema": {}}]

    async def plan(self, calls, ctx):
        return self._plan_factory(calls)

    async def run(self, plan, ctx):
        self.run_calls += 1
        results = [
            ToolResult(tool_use_id=pc.call.id, content=f"out:{pc.call.name}", is_error=False)
            for pc in plan.auto_run
        ]
        return BatchResult(results=results, session_state=ctx.state)


class LeakGateway(FakeGateway):
    """违反 I-B2 的网关：auto_run 有多少条都只回一条，验证 execute 兜底。"""

    def __init__(self) -> None:
        super().__init__(make_plan_auto)

    async def run(self, plan, ctx):
        self.run_calls += 1
        only = plan.auto_run[0].call.id if plan.auto_run else "?"
        return BatchResult(
            results=[ToolResult(tool_use_id=only, content="only-one")],
            session_state=ctx.state,
        )


class FakeApprovals:
    def __init__(self) -> None:
        self.tickets = 0

    def ensure_ticket(self, plan, run_id):
        self.tickets += 1
        return f"ticket-{self.tickets}"


class FakeCompactor:
    def __init__(self, est=0) -> None:
        self._est = est

    def estimate(self, messages, state):
        return self._est

    def microcompact(self, messages, state):
        return None

    async def summarize(self, messages, state, emit):
        return [PlatformMessage.user("[summary]")] + messages[-1:]


class FakeVision:
    def supports(self, model):
        return False

    async def describe(self, block):
        return f"<desc {block.media_type}>"


class FakePolicy:
    def __init__(self) -> None:
        self.outcomes = []

    async def post_run(self, outcome):
        self.outcomes.append(outcome)


def build_deps(chat, gateway, approvals=None, compactor=None, vision=None, cfg=None) -> EngineDeps:
    return EngineDeps(
        chat=chat,
        gateway=gateway,
        approvals=approvals or FakeApprovals(),
        compactor=compactor or FakeCompactor(),
        policy=FakePolicy(),
        sandbox=FakeSandbox(),
        cfg=cfg or EngineConfig(model="test-model", system_prompt="sys", max_tokens=1024),
        vision=vision,
    )


def apply_update(state: AgentState, update: dict) -> AgentState:
    """reducer 模拟：脱离图直调节点时手工合并 LangGraph 状态更新。"""
    new = dict(state)
    for key, value in update.items():
        if key == "messages":
            new["messages"] = merge_messages(state["messages"], value)
        else:
            new[key] = value
    return new


def make_plan_auto(calls):
    return ToolPlan(order=calls, auto_run=[PreparedCall(call=c) for c in calls])


def make_plan_mixed(calls):
    """第一个需审批，其余自动。"""
    auto = [PreparedCall(call=c) for c in calls[1:]]
    approval = [PreparedCall(call=calls[0], decision=Decision.require_confirm("rm risky", "high"))]
    return ToolPlan(order=calls, auto_run=auto, need_approval=approval)
