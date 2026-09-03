"""api/ —— LLM 供应商内核（自供体 openharness/api 搬迁解耦，见 api内核搬迁细则）。

合同面：protocol（请求/事件/协议）+ errors（统一异常树）+ usage。
实现面：client（Anthropic）/ openai_client / codex_client / copilot_client。
路由面：registry（供应商注册表）+ factory（ClientFactory）。
"""

from api.errors import (
    ApiFailure,
    AuthenticationFailure,
    ContextOverflowFailure,
    RateLimitFailure,
    RequestFailure,
    is_completion_token_limit,
    parse_completion_token_limit,
)
from api.protocol import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiRetryEvent,
    ApiStreamEvent,
    ApiTextDeltaEvent,
    SupportsStreamingMessages,
)
from api.usage import UsageSnapshot
from api.client import AnthropicApiClient
from api.codex_client import CodexApiClient
from api.copilot_client import CopilotClient
from api.openai_client import OpenAICompatibleClient
from api.registry import PROVIDERS, ProviderSpec, detect_provider_from_registry, register_provider
from api.factory import (
    Credential,
    CredentialResolver,
    StaticCredentialResolver,
    create_client,
)

__all__ = [
    "ApiFailure",
    "AuthenticationFailure",
    "ContextOverflowFailure",
    "RateLimitFailure",
    "RequestFailure",
    "is_completion_token_limit",
    "parse_completion_token_limit",
    "ApiMessageRequest",
    "ApiTextDeltaEvent",
    "ApiMessageCompleteEvent",
    "ApiRetryEvent",
    "ApiStreamEvent",
    "SupportsStreamingMessages",
    "UsageSnapshot",
    "AnthropicApiClient",
    "CodexApiClient",
    "CopilotClient",
    "OpenAICompatibleClient",
    "PROVIDERS",
    "ProviderSpec",
    "detect_provider_from_registry",
    "register_provider",
    "Credential",
    "CredentialResolver",
    "StaticCredentialResolver",
    "create_client",
]
