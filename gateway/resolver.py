"""唯一路径解析器（权限与沙箱设计 §六.2 / 内置工具规范 §1）。

权限裁决与工具执行共用同一次解析；工具内部不得二次解析路径。
探测顺序沿用 OpenHarness：file_path / path / root（raw dict 与 parsed 对象都查）。

容器侧一律 posixpath 语义（沙箱是 Linux 容器，/ 开头即绝对路径，
不能用宿主 os.path 判断——Windows 上 "/etc/passwd" 的 Path.is_absolute() 为 False）。
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

PATH_FIELDS = ("file_path", "path", "root")

_CONTAINER_ROOT = "/workspace"


class PathEscape(Exception):
    """解析后的路径逃出沙箱工作目录。"""


class SandboxPathView(Protocol):
    """SandboxHandle 的路径面（resolver 只需要 root）。"""

    @property
    def root(self) -> str: ...


@dataclass(frozen=True)
class ResolvedPath:
    container_path: str  # 模型/权限视角（/workspace/...）
    host_path: str       # 物理 IO 路径（bind mount 宿主侧）


def _extract_raw_path(raw_input: dict[str, Any], parsed_input: Any) -> str | None:
    for field in PATH_FIELDS:
        value = raw_input.get(field)
        if isinstance(value, str) and value.strip():
            return value
    for field in PATH_FIELDS:
        value = getattr(parsed_input, field, None)
        if isinstance(value, str) and value.strip():
            return value
    return None


def resolve_tool_path(
    raw_input: dict[str, Any],
    parsed_input: Any,
    sandbox: SandboxPathView,
) -> ResolvedPath:
    """解析工具入参中的路径：相对路径拼 /workspace，越界（normpath 后出根）即 PathEscape。"""
    raw = _extract_raw_path(raw_input, parsed_input)
    if raw is None:
        raise PathEscape("no path field found in tool input")

    raw = raw.strip()
    if not raw.startswith("/"):
        raw = f"{_CONTAINER_ROOT}/{raw}"
    container_path = posixpath.normpath(raw)  # 折叠 ../ 与 //
    if container_path == _CONTAINER_ROOT:
        rel = ""
    elif container_path.startswith(f"{_CONTAINER_ROOT}/"):
        rel = container_path[len(_CONTAINER_ROOT) + 1 :]
    else:
        raise PathEscape(f"path escapes workspace: {raw}")

    host_root = Path(sandbox.root).resolve()
    host_path = (host_root / rel).resolve() if rel else host_root
    if host_root != host_path and host_root not in host_path.parents:
        raise PathEscape(f"path escapes workspace: {raw}")

    return ResolvedPath(container_path=container_path, host_path=str(host_path))


def resolve_optional_tool_path(
    raw_input: dict[str, Any],
    parsed_input: Any,
    sandbox: SandboxPathView,
    *,
    default_container: str = _CONTAINER_ROOT,
) -> ResolvedPath | None:
    """有路径字段则解析（可能抛 PathEscape）；没有则返回默认目录。"""
    if _extract_raw_path(raw_input, parsed_input) is None:
        return ResolvedPath(container_path=default_container, host_path=str(Path(sandbox.root).resolve()))
    return resolve_tool_path(raw_input, parsed_input, sandbox)
