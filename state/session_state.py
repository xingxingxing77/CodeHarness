"""SessionState：类型化的会话工作记忆（替代 OpenHarness 的 tool_metadata dict 大杂烩）。

LRU 语义沿用 `_append_capped_unique`：去重、置新、截尾。
失败不记——只有 is_error=False 的工具结果才允许进入 verified_work/work_log。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def append_capped_unique(bucket: list[Any], value: Any, *, limit: int) -> None:
    if value in bucket:
        bucket.remove(value)
    bucket.append(value)
    if len(bucket) > limit:
        del bucket[:-limit]


@dataclass
class SessionState:
    permission_mode: str = "default"
    goal: str = ""
    recent_goals: list[str] = field(default_factory=list)
    recent_files: list[dict[str, Any]] = field(default_factory=list)
    active_artifacts: list[str] = field(default_factory=list)
    verified_work: list[str] = field(default_factory=list)
    work_log: list[str] = field(default_factory=list)
    async_tasks: list[dict[str, Any]] = field(default_factory=list)

    def remember_goal(self, summary: str, *, limit: int = 5) -> None:
        summary = summary.strip()
        if not summary:
            return
        append_capped_unique(self.recent_goals, summary[:240], limit=limit)
        self.goal = summary[:240]

    def remember_artifact(self, artifact: str, *, limit: int = 8) -> None:
        artifact = artifact.strip()
        if artifact:
            append_capped_unique(self.active_artifacts, artifact[:240], limit=limit)

    def remember_verified(self, entry: str, *, limit: int = 10) -> None:
        entry = entry.strip()
        if entry:
            append_capped_unique(self.verified_work, entry[:320], limit=limit)

    def log_work(self, entry: str, *, limit: int = 10) -> None:
        entry = entry.strip()
        if entry:
            append_capped_unique(self.work_log, entry[:320], limit=limit)
