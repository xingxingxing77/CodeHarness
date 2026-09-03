"""权限规则引擎（权限与沙箱设计 §一）。

匹配顺序（第一条命中即返回）：deny(priority↑) → allow(priority↑) → 配方默认 → DENY(fail-closed)。
evaluate 纯函数（同输入同输出）——节点重放安全；规则快照 run 内不变。
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any, Literal

from gateway.resolver import ResolvedPath
from tools.base import Decision

RuleKind = Literal[
    "tool_allow", "tool_deny", "path_allow", "path_deny", "cmd_allow", "cmd_deny"
]

DANGEROUS_COMMAND_PATTERNS = (
    "sudo*",
    "su *",
    "rm -rf /*",
    "rm -rf ~*",
    "mkfs*",
    "dd if=*of=/dev/*",
    "chmod 777 *",
    "curl *| *sh",
    "wget *| *sh",
    "git push --force*",
)


@dataclass(frozen=True)
class PermissionRule:
    kind: RuleKind
    pattern: str        # tool: 精确名或通配；path: 对容器路径 glob；cmd: 首 token 通配或整行通配
    risk_level: str = "medium"
    priority: int = 100
    enabled: bool = True
    rule_id: str = ""


@dataclass(frozen=True)
class EvaluateInput:
    tool_name: str
    read_only: bool
    resolved: ResolvedPath | None      # 无路径字段的工具（bash）为 None
    command: str | None = None         # executes_commands 工具的命令行
    executes_commands: bool = False


class RulePermissionEngine:
    """无状态评估器：规则快照由装配层注入（run 内不变）。"""

    def __init__(self, rules: list[PermissionRule] = (), recipe: str = "standard") -> None:
        self._rules = [r for r in rules if r.enabled]
        if recipe not in _RECIPE_DEFAULTS:
            raise ValueError(f"unknown recipe: {recipe}")
        self._recipe = recipe

    # -- 匹配器 -----------------------------------------------------------

    @staticmethod
    def _match(rule: PermissionRule, inp: EvaluateInput) -> bool:
        if rule.kind.startswith("tool_"):
            return fnmatch.fnmatch(inp.tool_name, rule.pattern)
        if rule.kind.startswith("path_"):
            if inp.resolved is None:
                return False
            return fnmatch.fnmatch(inp.resolved.container_path, rule.pattern)
        # cmd_*
        if not inp.executes_commands or inp.command is None:
            return False
        command = inp.command.strip()
        first_token = command.split(" ", 1)[0]
        return fnmatch.fnmatch(first_token, rule.pattern) or fnmatch.fnmatch(command, rule.pattern)

    # -- 评估 --------------------------------------------------------------

    def evaluate(self, inp: EvaluateInput) -> Decision:
        deny = self._best([r for r in self._rules if r.kind.endswith("_deny") and self._match(r, inp)])
        if deny is not None:
            return Decision.deny(f"denied by rule {deny.rule_id or deny.kind}: {deny.pattern}")

        allow = self._best([r for r in self._rules if r.kind.endswith("_allow") and self._match(r, inp)])
        if allow is not None:
            return Decision.allow()

        return self._recipe_default(inp)

    @staticmethod
    def _best(rules: list[PermissionRule]) -> PermissionRule | None:
        return min(rules, key=lambda r: r.priority) if rules else None

    def _recipe_default(self, inp: EvaluateInput) -> Decision:
        return _RECIPE_DEFAULTS[self._recipe](inp)


# ---------------------------------------------------------------------------
# 三配方默认（权限与沙箱设计 §1.5）
# ---------------------------------------------------------------------------


def _recipe_cautious(inp: EvaluateInput) -> Decision:
    if inp.read_only:
        return Decision.allow()
    return Decision.require_confirm("cautious recipe: all non-read-only operations require approval", "high")


def _recipe_standard(inp: EvaluateInput) -> Decision:
    if inp.read_only:
        return Decision.allow()
    if inp.executes_commands:
        # 非只读命令（git push / pip install / rm …）一律要批；危险清单经内置 cmd_deny 规则 DENY
        return Decision.require_confirm("standard recipe: non-read-only commands require approval", "medium")
    return Decision.allow()  # 工作区写：resolver 围栏兜底；租户 path_deny 可再收紧


def _recipe_unsupervised(inp: EvaluateInput) -> Decision:
    return Decision.allow()  # 只读外全批（沙箱网络/文件系统兜底）


_RECIPE_DEFAULTS: dict[str, Any] = {
    "cautious": _recipe_cautious,
    "standard": _recipe_standard,
    "unsupervised": _recipe_unsupervised,
}

RECIPE_NAMES = ("cautious", "standard", "unsupervised")


def builtin_recipe_rules(recipe: str = "standard") -> list[PermissionRule]:
    """配方内置规则（如危险命令清单）；evaluate 默认值之前生效（priority 0）。"""
    if recipe != "standard":
        return []
    return [
        PermissionRule(
            kind="cmd_deny",
            pattern=pattern,
            priority=0,
            rule_id=f"builtin-dangerous-{i}",
        )
        for i, pattern in enumerate(DANGEROUS_COMMAND_PATTERNS)
    ]
