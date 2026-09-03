"""内核统一异常树（契约面）。

ContextOverflowFailure 为新增类型，替代 OpenHarness 的 prompt-too-long 文本嗅探；
内核搬迁（api 实现方）必须把各家的超长报错归一化到这个类型再抛。
"""
from __future__ import annotations

import re


class ApiFailure(RuntimeError):
    pass


class AuthenticationFailure(ApiFailure):
    """401/403/凭证被拒。永不重试。"""


class RateLimitFailure(ApiFailure):
    """429。内核重试耗尽后抛出。"""


class ContextOverflowFailure(ApiFailure):
    """prompt 超出上下文窗口。引擎路由到反应式压缩。"""


class RequestFailure(ApiFailure):
    """其余传输/请求失败。"""


_COMPLETION_LIMIT_PATTERNS = (
    r"supports at most\s+(\d+)\s+completion tokens",
    r"at most\s+(\d+)\s+completion tokens",
    r"max(?:imum)?(?:_completion)?[_\s-]tokens.*?(?:<=|less than or equal to|at most)\s+(\d+)",
)


def is_completion_token_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return ("max_tokens" in text or "max_completion_tokens" in text) and (
        "too large" in text or "at most" in text or "completion tokens" in text
    )


def parse_completion_token_limit(exc: Exception) -> int | None:
    text = str(exc).lower().replace(",", "")
    for pattern in _COMPLETION_LIMIT_PATTERNS:
        match = re.search(pattern, text)
        if match:
            try:
                return max(1, int(match.group(1)))
            except ValueError:
                return None
    return None


# 供体代码兼容别名（内核客户端 import 此名；规范名是 ApiFailure）
OpenHarnessApiError = ApiFailure
