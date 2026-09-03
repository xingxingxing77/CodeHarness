"""轮次预算：max_turns 的权威判定用业务轮次计数，recursion_limit 仅作保险丝。"""
from __future__ import annotations

from dataclasses import dataclass

MAX_SAFE_COMPLETION_TOKENS = 128_000


def bounded_completion_tokens(max_tokens: int, context_window_tokens: int | None = None) -> int:
    limit = MAX_SAFE_COMPLETION_TOKENS
    if context_window_tokens is not None and context_window_tokens > 0:
        limit = min(limit, int(context_window_tokens))
    return max(1, min(int(max_tokens), limit))


@dataclass(frozen=True)
class TurnBudget:
    max_turns: int
    recover_extra: int = 8

    def recursion_limit(self) -> int:
        # 每轮最多经过 preprocess/compact/agent/prepare/approval/execute ≈ 6 个超步
        return 6 * (self.max_turns + self.recover_extra) + 10

    @staticmethod
    def exceeded(turn: int, max_turns: int) -> bool:
        return turn >= max_turns
