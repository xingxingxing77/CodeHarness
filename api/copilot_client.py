"""GitHub Copilot API client.

Wraps :class:`OpenAICompatibleClient` with Copilot-specific headers.
The Copilot chat endpoint is OpenAI-compatible, so all message/tool
conversion is delegated to the inner client.

解耦改造（api内核搬迁细则 D2）：Copilot 专属头经 OpenAICompatibleClient 的
default_headers 构造参数注入（替代供体对 _inner._client 的私有赋值）；
令牌来源 = 显式参数 → TokenStore。
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from api.copilot_auth import TokenStore, copilot_api_base
from api.errors import AuthenticationFailure
from api.openai_client import OpenAICompatibleClient
from api.protocol import ApiMessageRequest, ApiStreamEvent

log = logging.getLogger(__name__)

_VERSION = "0.1.0"  # platform version for User-Agent

# Default model for Copilot requests when the configured model is not
# available in the Copilot model catalog.
COPILOT_DEFAULT_MODEL = "gpt-4o"

_COPILOT_HEADERS = {
    "User-Agent": f"codeharness/{_VERSION}",
    "Openai-Intent": "conversation-edits",
}


class CopilotClient:
    """Copilot-aware API client implementing ``SupportsStreamingMessages``.

    Uses the GitHub OAuth token directly as a Bearer token for the
    Copilot API.  No token exchange or session management is needed.
    """

    def __init__(
        self,
        github_token: str | None = None,
        *,
        enterprise_url: str | None = None,
        model: str | None = None,
        token_store: TokenStore | None = None,
    ) -> None:
        info = token_store.load() if token_store is not None else None
        token = github_token or (info.github_token if info else None)
        if not token:
            raise AuthenticationFailure(
                "No GitHub Copilot token found. Provide github_token or a loaded token_store."
            )

        # Resolve enterprise_url: explicit arg > token store > None (public)
        ent_url = enterprise_url or (info.enterprise_url if info else None)

        self._token = token
        self._enterprise_url = ent_url
        self._model = model

        base_url = copilot_api_base(ent_url)
        self._inner = OpenAICompatibleClient(
            api_key=token,
            base_url=base_url,
            default_headers=dict(_COPILOT_HEADERS),
        )

        log.info(
            "CopilotClient initialised (api_base=%s, enterprise=%s)",
            base_url,
            ent_url or "none",
        )

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        """Stream a chat completion from the Copilot API.

        If a *model* was provided at construction time it overrides the
        model in *request*; otherwise the request model is passed through.
        """
        effective_model = self._model or request.model
        patched = ApiMessageRequest(
            model=effective_model,
            messages=request.messages,
            system_prompt=request.system_prompt,
            max_tokens=request.max_tokens,
            tools=request.tools,
        )
        async for event in self._inner.stream_message(patched):
            yield event

    async def close(self) -> None:
        """Close the underlying OpenAI-compatible client."""
        await self._inner.close()
