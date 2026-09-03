from __future__ import annotations

from engine.messages import PlatformMessage, ImageBlock, TextBlock
from api.client import AnthropicApiClient, OAUTH_BETA_HEADER


def test_anthropic_client_adds_oauth_beta_header(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("api.client.AsyncAnthropic", _FakeAsyncAnthropic)

    AnthropicApiClient(auth_token="oauth-token")

    assert captured["auth_token"] == "oauth-token"
    assert captured["default_headers"] == {"anthropic-beta": OAUTH_BETA_HEADER}


def test_anthropic_client_uses_api_key_without_oauth_beta(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("api.client.AsyncAnthropic", _FakeAsyncAnthropic)

    AnthropicApiClient(api_key="api-key")

    assert captured["api_key"] == "api-key"
    assert "default_headers" not in captured


def test_anthropic_client_oauth_token_gets_default_beta_header(monkeypatch):
    """auth_token 默认仅注入 oauth beta 头（无订阅模拟）。"""
    captured: dict[str, object] = {}

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("api.client.AsyncAnthropic", _FakeAsyncAnthropic)

    AnthropicApiClient(auth_token="oauth-token")

    headers = captured["default_headers"]
    assert headers["anthropic-beta"] == "oauth-2025-04-20"
    assert "x-app" not in headers


def test_anthropic_client_injects_provider_headers(monkeypatch):
    """auth_header_provider 头并入默认头；provider 可覆盖 beta 值。"""
    captured: dict[str, object] = {}

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("api.client.AsyncAnthropic", _FakeAsyncAnthropic)

    AnthropicApiClient(
        auth_token="oauth-token",
        auth_header_provider=lambda: {"x-app": "codeharness", "anthropic-beta": "custom-beta"},
    )

    headers = captured["default_headers"]
    assert headers["x-app"] == "codeharness"
    assert headers["anthropic-beta"] == "custom-beta"


def test_conversation_message_serializes_image_block_for_anthropic():
    message = PlatformMessage(
        role="user",
        content=[
            TextBlock(text="Describe this."),
            ImageBlock(media_type="image/png", data="YWJj", source_path="/tmp/example.png"),
        ],
    )

    assert message.to_api_param() == {
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this."},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": "YWJj",
                },
            },
        ],
    }


def test_anthropic_client_refreshes_token_on_request(monkeypatch):
    """auth_token_resolver 返回新令牌时，下一次请求前重建客户端。"""
    captured_tokens: list[str] = []

    class _FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def __aiter__(self):
            if False:
                yield None
            return

        async def get_final_message(self):
            class _Usage:
                input_tokens = 1
                output_tokens = 1

            class _Message:
                usage = _Usage()
                stop_reason = "end_turn"
                role = "assistant"
                content = []

            return _Message()

    class _FakeMessages:
        def __init__(self):
            self.last_params = None

        def stream(self, **params):
            self.last_params = params
            return _FakeStream()

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured_tokens.append(kwargs["auth_token"])
            self.messages = _FakeMessages()

    monkeypatch.setattr("api.client.AsyncAnthropic", _FakeAsyncAnthropic)

    current_token = {"value": "initial-token"}

    client = AnthropicApiClient(
        auth_token="initial-token",
        auth_token_resolver=lambda: current_token["value"],
    )
    current_token["value"] = "refreshed-token"

    from api.client import ApiMessageRequest

    async def _run():
        events = []
        async for event in client.stream_message(
            ApiMessageRequest(
                model="claude-sonnet-4-6",
                messages=[],
                system_prompt="system prompt",
            )
        ):
            events.append(event)
        return events

    import asyncio

    events = asyncio.run(_run())

    assert captured_tokens == ["initial-token", "refreshed-token"]
    assert events
    assert "metadata" not in client._client.messages.last_params
    assert "betas" not in client._client.messages.last_params
