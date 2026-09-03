"""M1 五个内置工具（内置工具规范为唯一定义源）。

read_file / write_file / glob / grep / bash。
路径统一经 gateway.resolver 解析（权限裁决与执行共用同一次解析）；
执行全部经 SandboxHandle（S1.1）；失败转 is_error 回执喂回模型。
"""

from __future__ import annotations

import difflib
import fnmatch
import shlex
from typing import Any

from pydantic import BaseModel, Field

from gateway.resolver import PathEscape, resolve_optional_tool_path, resolve_tool_path
from tools.base import ExecCtx, ExecResult, SandboxFileNotFound, ToolResult, UiPayload

from tools.base import ToolDef, ToolRegistry

_WORKSPACE_ROOT = "/workspace"
_DEFAULT_OUTPUT_CAP = 1_048_576


def _err(tool_use_id: str, message: str) -> ToolResult:
    return ToolResult(tool_use_id=tool_use_id, content=message, is_error=True)


def _tool_use_id(ctx: ExecCtx) -> str:  # 回执 id 由 pipeline 覆盖；此处仅占位
    return ctx.run_id


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


class ReadFileInput(BaseModel):
    file_path: str
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=200, ge=1, le=1000)


async def _read_file_execute(parsed: ReadFileInput, ctx: ExecCtx) -> ToolResult:
    tid = _tool_use_id(ctx)
    try:
        resolved = resolve_tool_path(parsed.model_dump(), parsed, ctx.sandbox)
    except PathEscape as exc:
        return _err(tid, f"Permission denied for read_file: {exc}")

    try:
        data = await ctx.sandbox.read_file(resolved.container_path)
    except SandboxFileNotFound:
        return _err(tid, f"File not found: {resolved.container_path}")

    if b"\x00" in data[:8192]:
        return _err(tid, f"Binary file ({resolved.container_path}), use export instead")

    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    total = len(lines)
    window = lines[parsed.offset : parsed.offset + parsed.limit]
    rendered = "\n".join(
        f"{parsed.offset + i + 1:>6}\t{line}" for i, line in enumerate(window)
    )
    if parsed.offset + parsed.limit < total:
        rendered += (
            f"\n[truncated: showing lines {parsed.offset + 1}-{parsed.offset + len(window)} of {total}]"
        )
    return ToolResult(tool_use_id=tid, content=rendered)


def _read_file(parsed: ReadFileInput) -> bool:
    return True


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


class WriteFileInput(BaseModel):
    file_path: str
    content: str


async def _write_file_execute(parsed: WriteFileInput, ctx: ExecCtx) -> ToolResult:
    tid = _tool_use_id(ctx)
    try:
        resolved = resolve_tool_path(parsed.model_dump(), parsed, ctx.sandbox)
    except PathEscape as exc:
        return _err(tid, f"Permission denied for write_file: {exc}")

    old_bytes: bytes | None
    try:
        old_bytes = await ctx.sandbox.read_file(resolved.container_path)
    except SandboxFileNotFound:
        old_bytes = None

    await ctx.sandbox.write_file(resolved.container_path, parsed.content.encode("utf-8"))

    new_lines = parsed.content.splitlines()
    if old_bytes is None:
        summary = f"Wrote {len(new_lines)} lines to {resolved.container_path} (new file)"
        diff = "\n".join(
            difflib.unified_diff([], new_lines, fromfile="/dev/null", tofile=resolved.container_path, lineterm="")
        )
    else:
        old_lines = old_bytes.decode("utf-8", errors="replace").splitlines()
        diff = "\n".join(
            difflib.unified_diff(
                old_lines, new_lines, fromfile=f"{resolved.container_path} (old)", tofile=f"{resolved.container_path} (new)", lineterm=""
            )
        )
        added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
        summary = f"Wrote {len(new_lines)} lines to {resolved.container_path} (+{added}/-{removed} vs previous)"

    return ToolResult(
        tool_use_id=tid,
        content=summary,
        ui=UiPayload(kind="diff", data={"diff": diff}),
    )


# ---------------------------------------------------------------------------
# glob
# ---------------------------------------------------------------------------


class GlobInput(BaseModel):
    pattern: str
    path: str = "."


async def _glob_execute(parsed: GlobInput, ctx: ExecCtx) -> ToolResult:
    tid = _tool_use_id(ctx)
    try:
        resolved = resolve_optional_tool_path(parsed.model_dump(), parsed, ctx.sandbox)
    except PathEscape as exc:
        return _err(tid, f"Permission denied for glob: {exc}")

    rel = resolved.container_path.removeprefix(_WORKSPACE_ROOT).lstrip("/") or "."
    result = await ctx.sandbox.exec(["rg", "--files", rel], cwd=_WORKSPACE_ROOT)
    if result.exit_code >= 2:
        return _err(tid, f"glob failed: {result.stderr.strip() or 'rg error'}")

    matches = [
        line.strip().removeprefix(f"{_WORKSPACE_ROOT}/")
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    matched = [p for p in matches if fnmatch.fnmatch(p, parsed.pattern)]
    if not matched:
        return ToolResult(tool_use_id=tid, content=f"No files match pattern: {parsed.pattern}")

    cap = 200
    shown, extra = matched[:cap], matched[cap:]
    body = "\n".join(shown)
    if extra:
        body += f"\n(+{len(extra)} more)"
    return ToolResult(tool_use_id=tid, content=body)


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------


class GrepInput(BaseModel):
    pattern: str
    path: str = "."
    include: str | None = None
    max_results: int = Field(default=50, ge=1, le=200)


async def _grep_execute(parsed: GrepInput, ctx: ExecCtx) -> ToolResult:
    tid = _tool_use_id(ctx)
    try:
        resolved = resolve_optional_tool_path(parsed.model_dump(), parsed, ctx.sandbox)
    except PathEscape as exc:
        return _err(tid, f"Permission denied for grep: {exc}")

    rel = resolved.container_path.removeprefix(_WORKSPACE_ROOT).lstrip("/") or "."
    argv = ["rg", "-n"]
    if parsed.include:
        argv += ["--glob", parsed.include]
    argv += [parsed.pattern, rel]
    result = await ctx.sandbox.exec(argv, cwd=_WORKSPACE_ROOT)

    if result.exit_code == 1:
        return ToolResult(tool_use_id=tid, content=f"No matches for: {parsed.pattern}")
    if result.exit_code >= 2:
        detail = result.stderr.strip() or "rg error"
        if "regex" in detail.lower():
            return _err(tid, f"Invalid regex: {detail}")
        return _err(tid, f"grep failed: {detail}")

    hits = [
        line.strip().replace(f"{_WORKSPACE_ROOT}/", "")
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    shown, extra = hits[: parsed.max_results], hits[parsed.max_results :]
    body = "\n".join(shown)
    if extra:
        body += f"\n(+{len(extra)} more matches)"
    return ToolResult(tool_use_id=tid, content=body)


# ---------------------------------------------------------------------------
# bash
# ---------------------------------------------------------------------------


class BashInput(BaseModel):
    command: str
    timeout_s: int = Field(default=120, ge=1, le=300)


_BASH_READ_ONLY_FIRST_TOKENS = {"ls", "cat", "head", "tail", "wc", "find", "grep", "rg"}
_BASH_READ_ONLY_GIT = {"status", "log", "diff", "show", "branch"}


def _bash_is_read_only(parsed: BashInput) -> bool:
    """按输入动态定级：纯读白名单前缀 = 只读（内置工具规范 §6）。"""
    try:
        tokens = shlex.split(parsed.command)
    except ValueError:
        return False
    if not tokens:
        return True
    first = tokens[0]
    if first == "git":
        return len(tokens) > 1 and tokens[1] in _BASH_READ_ONLY_GIT
    return first in _BASH_READ_ONLY_FIRST_TOKENS


async def _bash_execute(parsed: BashInput, ctx: ExecCtx) -> ToolResult:
    tid = _tool_use_id(ctx)
    result = await ctx.sandbox.exec(
        ["/usr/local/bin/jail", "bash", "-c", parsed.command],
        cwd=_WORKSPACE_ROOT,
        timeout_s=float(parsed.timeout_s),
        output_cap=_DEFAULT_OUTPUT_CAP,
    )
    if result.exit_code == 124:
        return _err(tid, f"Command timed out after {parsed.timeout_s}s: {parsed.command[:120]}")

    output = (result.stdout + result.stderr).rstrip()
    if result.truncated:
        output += "\n[output truncated — see spill artifact for full capture]"
    return ToolResult(
        tool_use_id=tid,
        content=f"{output}\n<exit code: {result.exit_code}>",
        ui=UiPayload(kind="terminal", data={"exit_code": result.exit_code}),
    )


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------


def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDef(
            name="read_file",
            description="Read a line-ranged view of a text file inside the workspace, with line numbers.",
            input_model=ReadFileInput,
            execute=_read_file_execute,
            parallel_safe=True,
            is_read_only=_read_file,
            uses_path=True,
        )
    )
    registry.register(
        ToolDef(
            name="write_file",
            description="Write (create or fully overwrite) a text file inside the workspace.",
            input_model=WriteFileInput,
            execute=_write_file_execute,
            parallel_safe=False,
            is_read_only=lambda _parsed: False,
            uses_path=True,
            ui_kind="diff",
        )
    )
    registry.register(
        ToolDef(
            name="glob",
            description="List workspace files matching a glob pattern, newest first.",
            input_model=GlobInput,
            execute=_glob_execute,
            parallel_safe=True,
            uses_path=True,
        )
    )
    registry.register(
        ToolDef(
            name="grep",
            description="Search file contents with a Rust regex (ripgrep semantics).",
            input_model=GrepInput,
            execute=_grep_execute,
            parallel_safe=True,
            uses_path=True,
        )
    )
    registry.register(
        ToolDef(
            name="bash",
            description="Run a shell command inside the session sandbox (network disabled, jailed).",
            input_model=BashInput,
            execute=_bash_execute,
            parallel_safe=False,
            is_read_only=_bash_is_read_only,
            executes_commands=True,
            ui_kind="terminal",
        )
    )
    return registry
