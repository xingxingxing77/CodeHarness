"""agent 节点：一次流式模型调用。来源语义 run_query L733 流消费段 + L797 空回复保护。

重试完全下沉内核（chat.stream_message 内部退避重试、认证错误永不重试）；
本节点只处理"这一轮的结果或终态错误"，错误按类型路由，不做文本嗅探。
"""
from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from engine.budget import TurnBudget
from engine.deps import deps_from
from engine.stream_events import AssistantDelta, StatusNotice, emitter
from engine.types import AgentState, PlatformError
from api.errors import (
    ApiFailure,
    AuthenticationFailure,
    ContextOverflowFailure,
    RateLimitFailure,
    is_completion_token_limit,
    parse_completion_token_limit,
)
from api.protocol import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiRetryEvent,
    ApiTextDeltaEvent,
)
from api.usage import UsageSnapshot

log = logging.getLogger(__name__)


async def agent_node(state: AgentState, config: RunnableConfig) -> dict:
    deps = deps_from(config)
    cfg = deps.cfg
    emit = emitter(config)

    request = ApiMessageRequest(
        model=cfg.model,
        messages=state["messages"],
        system_prompt=cfg.system_prompt or None,
        max_tokens=state["effective_max_tokens"],
        tools=deps.gateway.tool_schemas(),
        effort=cfg.effort,
    )

    final = None
    usage = UsageSnapshot()
    stop_reason: str | None = None

    try:
        async for event in deps.chat.stream_message(request):
            if isinstance(event, ApiTextDeltaEvent):
                emit(AssistantDelta(text=event.text))
            elif isinstance(event, ApiRetryEvent):
                emit(
                    StatusNotice(
                        message=(
                            f"Request failed; retrying in {event.delay_seconds:.1f}s "
                            f"(attempt {event.attempt}/{event.max_attempts}): {event.message}"
                        )
                    )
                )
            elif isinstance(event, ApiMessageCompleteEvent):
                final = event.message
                usage = event.usage
                stop_reason = event.stop_reason
    except ContextOverflowFailure as exc:
        log.info("context overflow, routing to reactive compact: %s", exc)
        if state.get("reactive_compact_done"):
            return {
                "route": "fail",
                "error": PlatformError(
                    code="context_overflow",
                    message="Prompt still exceeds context after reactive compaction.",
                ),
            }
        return {"route": "reactive_compact", "error": None}
    except AuthenticationFailure as exc:
        return {"route": "fail", "error": PlatformError(code="auth", message=str(exc))}
    except RateLimitFailure as exc:
        return {"route": "fail", "error": PlatformError(code="rate_limit", message=str(exc))}
    except ApiFailure as exc:
        if is_completion_token_limit(exc):
            supported = parse_completion_token_limit(exc)
            if supported is not None and supported < state["effective_max_tokens"]:
                return {
                    "route": "clamp_retry",
                    "effective_max_tokens": supported,
                    "error": None,
                }
        return {"route": "fail", "error": PlatformError(code="upstream", message=str(exc))}
    except Exception as exc:  # noqa: BLE001 — 未归类异常一律终态，绝不吞进循环
        log.exception("agent node stream raised")
        return {
            "route": "fail",
            "error": PlatformError(code="internal", message=f"{type(exc).__name__}: {exc}"),
        }

    if final is None:
        return {
            "route": "fail",
            "error": PlatformError(code="empty_stream", message="Model stream finished without a final message"),
        }
    if final.is_effectively_empty():
        # 空回复保护：丢弃并终止，避免污染会话历史
        return {
            "route": "fail",
            "error": PlatformError(
                code="empty_response",
                message="Model returned an empty assistant message; turn ignored to keep the session healthy.",
            ),
        }

    if stop_reason:
        final.metadata["stop_reason"] = stop_reason

    new_turn = state["turn"] + 1
    if final.tool_calls and TurnBudget.exceeded(new_turn, cfg.max_turns):
        # 有工具调用但轮次预算耗尽 → 熔断；无 tool_calls 的收敛不受预算影响
        return {
            "messages": [final],
            "turn": new_turn,
            "usage_total": state["usage_total"] + usage,
            "route": "fail",
            "error": PlatformError(
                code="max_turns_exceeded",
                message=f"Exceeded maximum turn limit ({cfg.max_turns}).",
            ),
        }

    return {
        "messages": [final],
        "turn": new_turn,
        "usage_total": state["usage_total"] + usage,
        "route": "proceed",
        "error": None,
    }
