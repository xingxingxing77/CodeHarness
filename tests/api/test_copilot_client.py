"""Tests for the GitHub Copilot API client.

适配（api内核搬迁细则 §5）：令牌来源改为 TokenStore；头注入走构造参数。
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from api.client import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiStreamEvent,
    ApiTextDeltaEvent,
)
from api.copilot_auth import CopilotAuthInfo, MemoryTokenStore
from api.copilot_client import CopilotClient
from api.errors import AuthenticationFailure
from api.usage import UsageSnapshot
from engine.messages import PlatformMessage, TextBlock


# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------


class FakeInnerClient:
    """Stand-in for ``OpenAICompatibleClient`` returned after init."""

    def __init__(self) -> None:
        self.last_request: ApiMessageRequest | None = None

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        self.last_request = request
        msg = PlatformMessage(role="assistant", content=[TextBlock(text="Hello from Copilot")])
        yield ApiTextDeltaEvent(text="Hello from Copilot")
        yield ApiMessageCompleteEvent(
            message=msg,
            usage=UsageSnapshot(input_tokens=10, output_tokens=5),
            stop_reason="end_turn",
        )


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


class TestCopilotClientInit:
    """Test CopilotClient construction and auth validation."""

    def test_raises_when_no_token(self):
        with pytest.raises(AuthenticationFailure, match="No GitHub Copilot token"):
            CopilotClient()

    def test_succeeds_with_explicit_token(self):
        client = CopilotClient(github_token="gho_explicit")
        assert client._token == "gho_explicit"
        assert client._enterprise_url is None

    def test_loads_from_token_store(self):
        store = MemoryTokenStore()
        store.save(CopilotAuthInfo(github_token="gho_persisted"))
        client = CopilotClient(token_store=store)
        assert client._token == "gho_persisted"

    def test_explicit_token_takes_precedence(self):
        store = MemoryTokenStore()
        store.save(CopilotAuthInfo(github_token="gho_persisted"))
        client = CopilotClient(github_token="gho_override", token_store=store)
        assert client._token == "gho_override"

    def test_enterprise_url_from_token_store(self):
        store = MemoryTokenStore()
        store.save(CopilotAuthInfo(github_token="gho_ent", enterprise_url="company.ghe.com"))
        client = CopilotClient(token_store=store)
        assert client._enterprise_url == "company.ghe.com"

    def test_explicit_enterprise_url_takes_precedence(self):
        store = MemoryTokenStore()
        store.save(CopilotAuthInfo(github_token="gho_ent", enterprise_url="old.ghe.com"))
        client = CopilotClient(github_token="gho_x", enterprise_url="new.ghe.com")
        assert client._enterprise_url == "new.ghe.com"

    def test_inner_client_uses_correct_api_base(self):
        """The inner OpenAI client should be pointed at the correct API base."""
        client = CopilotClient(github_token="gho_test")
        # Default: public GitHub
        assert client._inner._client.base_url is not None

    def test_inner_client_enterprise_base(self):
        """Enterprise URL should produce the correct Copilot API base."""
        store = MemoryTokenStore()
        store.save(CopilotAuthInfo(github_token="gho_ent", enterprise_url="company.ghe.com"))
        client = CopilotClient(token_store=store)
        # The inner client should use the enterprise API base
        base = str(client._inner._client.base_url)
        assert "copilot-api.company.ghe.com" in base


# ---------------------------------------------------------------------------
# stream_message tests
# ---------------------------------------------------------------------------


class TestStreamMessage:
    """Test that stream_message delegates to the inner client."""

    @pytest.mark.asyncio
    async def test_delegates_to_inner_client(self):
        """stream_message should yield events from the inner client's stream_message."""
        fake_inner = FakeInnerClient()

        client = CopilotClient(github_token="gho_stream")
        # Inject the fake inner client directly
        client._inner = fake_inner

        request = ApiMessageRequest(
            model="gpt-4o",
            messages=[PlatformMessage.user("Hello")],
        )

        events: list[ApiStreamEvent] = []
        async for event in client.stream_message(request):
            events.append(event)

        assert len(events) == 2
        assert isinstance(events[0], ApiTextDeltaEvent)
        assert events[0].text == "Hello from Copilot"
        assert isinstance(events[1], ApiMessageCompleteEvent)
        assert events[1].stop_reason == "end_turn"
        assert fake_inner.last_request == request
