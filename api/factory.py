"""注册表驱动的客户端工厂（api内核搬迁细则 §4）。

替代供体 ui/runtime.py 的 5 分支 if：模型串+凭证 → detect → backend_type → 构造。
LangGraph 侧经 OpenHarnessChatModel 桥接调用本工厂产物。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from api.client import AnthropicApiClient
from api.codex_client import CodexApiClient
from api.copilot_client import CopilotClient
from api.errors import RequestFailure
from api.openai_client import OpenAICompatibleClient
from api.protocol import SupportsStreamingMessages
from api.registry import ProviderSpec, detect_provider_from_registry


@dataclass(frozen=True)
class Credential:
    """一次调用的凭证（来自租户凭证库 / bootstrap env）。"""

    api_key: str | None = None
    auth_token: str | None = None  # OAuth bearer（codex / claude oauth）

    def primary(self) -> str:
        return self.auth_token or self.api_key or ""


class CredentialResolver(Protocol):
    """凭证解析协议：平台侧实现 = 会话指定 → 租户凭证表 → bootstrap env。"""

    def resolve(self, spec: ProviderSpec, *, session_id: str | None = None) -> Credential: ...


class StaticCredentialResolver:
    """进程内固定凭证（CLI / 测试 / 单租户自部署）。"""

    def __init__(self, credential: Credential) -> None:
        self._credential = credential

    def resolve(self, spec: ProviderSpec, *, session_id: str | None = None) -> Credential:
        return self._credential


def create_client(
    model: str,
    creds: Credential,
    *,
    base_url: str | None = None,
    timeout: float | None = None,
    token_store: object | None = None,
) -> SupportsStreamingMessages:
    """按注册表检测结果构造客户端实例。检测失败 = RequestFailure（fail-closed）。"""
    spec = detect_provider_from_registry(model, creds.primary(), base_url)
    if spec is None:
        raise RequestFailure(f"No provider registered for model: {model}")

    if spec.backend_type == "anthropic":
        return AnthropicApiClient(api_key=creds.api_key, auth_token=creds.auth_token, base_url=base_url or None)
    if spec.backend_type == "openai_compat":
        return OpenAICompatibleClient(
            api_key=creds.primary(),
            base_url=base_url or spec.default_base_url or None,
            timeout=timeout,
        )
    if spec.backend_type == "codex":
        return CodexApiClient(auth_token=creds.primary(), base_url=base_url or spec.default_base_url)
    if spec.backend_type == "copilot":
        return CopilotClient(
            github_token=creds.primary(),
            enterprise_url=None,
            token_store=token_store,  # type: ignore[arg-type]
        )
    raise RequestFailure(f"Unknown backend_type: {spec.backend_type}")
