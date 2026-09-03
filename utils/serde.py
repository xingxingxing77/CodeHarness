"""checkpointer 序列化白名单：平台类型显式注册。

LangGraph 即将默认阻断 checkpoint 反序列化未注册类型（LANGGRAPH_STRICT_MSGPACK）；
build_graph 会把本模块的序列化器装到 checkpointer 上，Postgres checkpointer 同样适用。
"""
from __future__ import annotations

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from state.session_state import SessionState
from tools.base import BatchResult, Decision, PreparedCall, ToolCall, ToolPlan, ToolResult, UiPayload

from engine.messages import PlatformMessage
from api.usage import UsageSnapshot
from tools.builtin import BashInput, GlobInput, GrepInput, ReadFileInput, WriteFileInput

PLATFORM_CHECKPOINT_TYPES = [
    PlatformMessage,
    UsageSnapshot,
    SessionState,
    ToolCall,
    ToolResult,
    Decision,
    PreparedCall,
    ToolPlan,
    BatchResult,
    UiPayload,
    # 工具输入模型（checkpoint 往返后由网关重校验兜底，注册仅为免阻断）
    BashInput,
    GlobInput,
    GrepInput,
    ReadFileInput,
    WriteFileInput,
]


def platform_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=list(PLATFORM_CHECKPOINT_TYPES))
