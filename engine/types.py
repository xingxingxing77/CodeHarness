from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel

from state.session_state import SessionState
from tools.base import ToolPlan
from engine.messages import PlatformMessage
from api.usage import UsageSnapshot

Route = Literal["proceed", "clamp_retry", "reactive_compact", "fail"]


class PlatformError(BaseModel):
    code: str
    message: str


@dataclass
class ReplaceMessages:
    """reducer 哨兵：整体替换消息列表（压缩/图片降级用），区别于默认追加。"""

    messages: list[PlatformMessage]


def merge_messages(
    current: list[PlatformMessage],
    update: list[PlatformMessage] | ReplaceMessages | None,
) -> list[PlatformMessage]:
    if update is None:
        return current
    if isinstance(update, ReplaceMessages):
        return list(update.messages)
    return [*current, *update]


@dataclass(frozen=True)
class RunOutcome:
    turns: int
    usage_total: UsageSnapshot
    stop_reason_hint: str | None
    error: PlatformError | None


class AgentState(TypedDict, total=False):
    # I-A1：state 内不出现 LangChain/LangGraph 类型
    messages: Annotated[list[PlatformMessage], merge_messages]
    turn: int
    effective_max_tokens: int
    route: Route
    reactive_compact_done: bool
    pending_plan: ToolPlan | None
    usage_total: UsageSnapshot
    session_state: SessionState
    error: PlatformError | None


def make_initial_state(
    messages: list[PlatformMessage],
    max_tokens: int,
    session_state: SessionState | None = None,
) -> AgentState:
    from engine.budget import bounded_completion_tokens

    return {
        "messages": list(messages),
        "turn": 0,
        "effective_max_tokens": bounded_completion_tokens(max_tokens),
        "route": "proceed",
        "reactive_compact_done": False,
        "pending_plan": None,
        "usage_total": UsageSnapshot(),
        "session_state": session_state or SessionState(),
        "error": None,
    }


def last_assistant(state: AgentState) -> PlatformMessage | None:
    for msg in reversed(state["messages"]):
        if msg.role == "assistant":
            return msg
    return None


def state_view(state: AgentState) -> dict[str, Any]:
    return dict(state)
