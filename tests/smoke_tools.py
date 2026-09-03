"""工具冒烟（内置工具规范 §8 测试基线）。

运行：python -m tools.smoke_tools
"""

from __future__ import annotations

import asyncio

from state.session_state import SessionState
from tools.base import ExecCtx, GatewayConfig
from tools.builtin import create_default_registry
from tools.base import ToolRegistry


def make_registry() -> ToolRegistry:
    return create_default_registry()


async def run_tool(registry: ToolRegistry, name: str, sandbox, raw_input: dict) -> "object":
    """按工具规范执行：resolver → schema 校验 → execute（等价闸门③⑤的最小驱动）。"""
    tool = registry.get(name)
    assert tool is not None
    parsed = tool.input_model.model_validate(raw_input)
    ctx = ExecCtx(
        tenant_id="t",
        session_id="s",
        run_id="r",
        sandbox=sandbox,
        state=SessionState(),
        cfg=GatewayConfig(),
    )
    result = await tool.execute(parsed, ctx)
    # 回执 id 由网关 pipeline 以真实 tool_use_id 覆盖；此处检查占位语义即可
    result.tool_use_id = raw_input.get("_id", result.tool_use_id)
    return result


async def case_registry_schemas():
    registry = make_registry()
    assert registry.names() == ["bash", "glob", "grep", "read_file", "write_file"]
    schemas = registry.to_api_schema()
    assert all(set(s) == {"name", "description", "input_schema"} for s in schemas)
    bash = next(s for s in schemas if s["name"] == "bash")
    assert "command" in bash["input_schema"]["properties"]


async def case_read_file():
    registry = make_registry()
    sandbox = FakeSandboxShim()
    sandbox.files["/workspace/src/app.py"] = b"import os\nimport sys\nimport json\n"
    out = await run_tool(registry, "read_file", sandbox, {"file_path": "src/app.py"})
    assert not out.is_error
    assert "     1\timport os" in out.content and "     3\timport json" in out.content
    assert "truncated" not in out.content

    out2 = await run_tool(registry, "read_file", sandbox, {"file_path": "src/app.py", "offset": 1, "limit": 1})
    assert "     2\timport sys" in out2.content
    assert "[truncated: showing lines 2-2 of 3]" in out2.content

    miss = await run_tool(registry, "read_file", sandbox, {"file_path": "src/missing.py"})
    assert miss.is_error and "File not found" in miss.content


async def case_read_file_escape():
    registry = make_registry()
    sandbox = FakeSandboxShim()
    out = await run_tool(registry, "read_file", sandbox, {"file_path": "../../etc/passwd"})
    assert out.is_error and "Permission denied for read_file" in out.content
    out2 = await run_tool(registry, "read_file", sandbox, {"file_path": "/etc/passwd"})
    assert out2.is_error and "escapes workspace" in out2.content


async def case_write_file_diff():
    registry = make_registry()
    sandbox = FakeSandboxShim()
    out = await run_tool(registry, "write_file", sandbox, {"file_path": "new.py", "content": "a\nb\n"})
    assert not out.is_error and "(new file)" in out.content
    assert out.ui is not None and out.ui.kind == "diff" and "+++ b/new.py" not in out.ui.data["diff"]

    out2 = await run_tool(registry, "write_file", sandbox, {"file_path": "new.py", "content": "a\nc\n"})
    assert "(+1/-1 vs previous)" in out2.content
    assert "-b" in out2.ui.data["diff"] and "+c" in out2.ui.data["diff"]


async def case_glob_grep():
    registry = make_registry()
    sandbox = FakeSandboxShim()
    sandbox.files["/workspace/src/app.py"] = b"import os\n"
    sandbox.files["/workspace/src/util.py"] = b"def helper():\n    return 'os'\n"
    sandbox.files["/workspace/docs/readme.md"] = b"# docs\n"

    g = await run_tool(registry, "glob", sandbox, {"pattern": "src/*.py"})
    assert sorted(g.content.splitlines()) == ["src/app.py", "src/util.py"]

    g2 = await run_tool(registry, "glob", sandbox, {"pattern": "*.md", "path": "docs"})
    assert g2.content == "docs/readme.md"

    grep = await run_tool(registry, "grep", sandbox, {"pattern": "os", "include": "*.py"})
    assert "src/app.py:1: import os" in grep.content
    assert "src/util.py:2:     return 'os'" in grep.content

    nomatch = await run_tool(registry, "grep", sandbox, {"pattern": "zzz_nowhere"})
    assert not nomatch.is_error and "No matches for" in nomatch.content

    bad = await run_tool(registry, "grep", sandbox, {"pattern": "([unclosed"})
    assert bad.is_error and "Invalid regex" in bad.content


async def case_bash():
    from tools.base import ExecResult

    registry = make_registry()
    bash = registry.get("bash")
    assert bash is not None
    # 动态只读定级
    assert bash.is_read_only(bash.input_model.model_validate({"command": "ls -la"}))
    assert bash.is_read_only(bash.input_model.model_validate({"command": "git status"}))
    assert not bash.is_read_only(bash.input_model.model_validate({"command": "git push origin main"}))
    assert not bash.is_read_only(bash.input_model.model_validate({"command": "rm -rf /"}))

    sandbox = FakeSandboxShim()
    sandbox.exec_handler = lambda argv, **kw: ExecResult(
        exit_code=0, stdout="file1\nfile2\n", stderr=""
    ) if argv[:3] == ["/usr/local/bin/jail", "bash", "-c"] and "ls" in argv[3] else None

    out = await run_tool(registry, "bash", sandbox, {"command": "ls"})
    assert not out.is_error and "<exit code: 0>" in out.content and "file1" in out.content
    assert sandbox.exec_calls[0][:3] == ["/usr/local/bin/jail", "bash", "-c"]

    sandbox2 = FakeSandboxShim()
    sandbox2.exec_handler = lambda argv, **kw: ExecResult(exit_code=1, stdout="", stderr="not found")
    out2 = await run_tool(registry, "bash", sandbox2, {"command": "cat missing.txt"})
    assert not out2.is_error and "<exit code: 1>" in out2.content  # 非零退出是观察数据

    sandbox3 = FakeSandboxShim()
    sandbox3.exec_handler = lambda argv, **kw: ExecResult(exit_code=124, stdout="", stderr="")
    out3 = await run_tool(registry, "bash", sandbox3, {"command": "sleep 999"})
    assert out3.is_error and "timed out" in out3.content


class FakeSandboxShim:
    """桥接：tools 需要 ExecCtx.sandbox（含 root/exec/read/write）。属性全部委托 inner。"""

    def __init__(self) -> None:
        from tests.testing import FakeSandbox

        self._inner = FakeSandbox()

    @property
    def session_id(self) -> str:
        return self._inner.session_id

    @property
    def root(self) -> str:
        return self._inner.root

    @property
    def files(self) -> dict:
        return self._inner.files

    @property
    def canned(self) -> list:
        return self._inner.canned

    @property
    def exec_handler(self):
        return self._inner.exec_handler

    @exec_handler.setter
    def exec_handler(self, handler) -> None:
        self._inner.exec_handler = handler

    @property
    def exec_calls(self) -> list:
        return self._inner.exec_calls

    async def exec(self, argv, **kwargs):
        return await self._inner.exec(argv, **kwargs)

    async def read_file(self, container_path: str, *, cap: int = 2_097_152) -> bytes:
        return await self._inner.read_file(container_path, cap=cap)

    async def write_file(self, container_path: str, data: bytes) -> None:
        await self._inner.write_file(container_path, data)

    async def destroy(self) -> None:
        await self._inner.destroy()


CASES = [
    case_registry_schemas,
    case_read_file,
    case_read_file_escape,
    case_write_file_diff,
    case_glob_grep,
    case_bash,
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
