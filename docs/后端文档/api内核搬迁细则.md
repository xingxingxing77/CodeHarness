# api 内核搬迁细则

> 把供体库 `E:\OpenHarness\src\openharness\api` 的 4 供应商客户端内核搬迁为本项目 `api/` 包的实施细则——逐文件处置表、解耦改造点、契约对齐、测试迁移与排期。方法论遵循 [设计计划 §三](../设计计划.md)（解耦 → 契约 → 替换 → 验收）。
> 关联：[后端设计 §3](后端设计.md) · [配置清单](../配置清单.md)（`CODEHARNESS_REQUIRE_EMPTY_REASONING_CONTENT`）

## 1. 搬迁范围与逐文件处置

供体调研结论（2026-09-01）：内核对供体其余部分为**低-中耦合**，传输层自包含；第三方依赖面干净（`anthropic`/`openai`/`httpx`/`pydantic`）。

| 源文件 | 目标 | 处置 |
|---|---|---|
| `api/client.py` | `api/client.py` | **改造**：删 `claude_oauth` 分支（或抽 `AuthHeaderProvider` 可选注入，默认 None 不启）；消息类型换 `PlatformMessage`；`_translate_api_error` 保留 |
| `api/openai_client.py` | `api/openai_client.py` | **小改**：`_reasoning` 从动态属性改为 `PlatformMessage.reasoning` 声明字段（`exclude=True`）；env 更名；其余原样（格式转换/`<think>` 剥离/`max_completion_tokens` 切换是核心资产） |
| `api/codex_client.py` | `api/codex_client.py` | **小改**：私有符号转正（见 §3-4）；每请求新建 `httpx.AsyncClient` 改为构造注入复用；JWT account_id 解析、SSE 解析、stop_reason 归一保留 |
| `api/copilot_client.py` | `api/copilot_client.py` | **改造**：删 `self._inner._client = raw_openai` 私有赋值 → `OpenAICompatibleClient.__init__` 增加 `default_headers` 参数注入 |
| `api/copilot_auth.py` | `api/copilot_auth.py` | **改造**：`save/load_copilot_auth` 的本地文件读写改为 `TokenStore` Protocol 注入（进程内实现 + P3 Postgres 实现）；device flow/轮询/enterprise URL 保留 |
| `api/errors.py` | `api/errors.py` | **增强**：+`ContextOverflowFailure`；各家 prompt-too-long 报错在客户端内归一为该类型（替代引擎文本嗅探） |
| `api/usage.py` | `api/usage.py` | 原样（与 `modelgateway/usage.py` 合一） |
| `api/registry.py` | `api/registry.py` | **改造**：静态 `PROVIDERS` 元组 → `register_provider(spec)` 可扩展注册表；三级检测（key 前缀→base_url→模型名）保留 |
| `api/provider.py` | **不迁** | 依赖 `Settings`/`auth.storage` 的 CLI 诊断（`detect_provider`/`auth_status`），平台无消费方 |
| `api/__init__.py` | 重写 | **惰性导出**（`__getattr__`），杜绝传递拉起 Settings 类依赖 |
| `engine/messages.py` | **不迁**（已有） | `PlatformMessage` 为目标消息模型，见 §2 接触面对齐 |
| `tests/test_api/*.py` | `tests/` | monkeypatch 的 import 路径改后整套迁移（§5） |

**不搬的暗依赖**：供体 `tools/image_generation_tool.py` 引用的 `_build_codex_headers`/`_resolve_codex_url`/`_normalize_openai_base_url` 是私有符号——迁移时这三个转正为 `api/` 公共函数（供未来图像工具复用），但工具本身不迁。

## 2. 消息模型接触面（供体 `ConversationMessage` → `PlatformMessage`）

两模型结构同构（Anthropic 风格内容块），直接替换类型而非写转换层。四个接触面必须在 `PlatformMessage` 上补齐：

| 接触面 | 供体位置 | 平台落点 |
|---|---|---|
| `to_api_param()` | engine/messages.py | `PlatformMessage.to_api_param()`：产出 Anthropic API dict（text/image/tool_use/tool_result 块序列化） |
| `serialize_content_block()` | 同上 | 各块 `model_dump` 的规范化入口，to_api_param 内部复用 |
| `assistant_message_from_api()` | engine/messages.py | `PlatformMessage.from_api_response()` 类方法：Anthropic 终态响应 → PlatformMessage（tool_use 块、usage 不在此） |
| `_reasoning` 动态属性 | openai_client.py | `PlatformMessage.reasoning: str | None = Field(default=None, exclude=True)`——流式收集、回放使用，序列化/checkpoint/表均不含 |

## 3. 解耦改造清单（搬迁同批完成）

1. **去 Settings**：内核不读配置对象；构造参数已干净（`api_key/base_url/auth_token/timeout`），`provider.py` 不迁即切断主耦合；
2. **去 auth.external**：`claude_oauth` 头注入/计费归属/betas 整段删除（`AuthHeaderProvider` Protocol 留扩展点）；
3. **copilot_auth 存储注入**：`TokenStore` Protocol `{load/save/clear}`；
4. **`__init__` 惰性导出**：`import api` 不得连带任何装配层模块；
5. **异常树对齐**：四类 + 新增 `ContextOverflowFailure`；`is_completion_token_limit`/`parse_completion_token_limit` 保留在 `api/errors.py`（引擎已按类型消费）；
6. **env 更名**：`OPENHARNESS_REQUIRE_EMPTY_REASONING_CONTENT` → `CODEHARNESS_REQUIRE_EMPTY_REASONING_CONTENT`（语义不变，见配置清单）；
7. **registry 可扩展**：`register_provider(spec)`；平台私有供应商经此接入，不改内核。

## 4. ClientFactory（"替换框架"的落点）

```python
class CredentialResolver(Protocol):
    def resolve(self, spec: ProviderSpec, ctx: ExecCtx) -> Credential: ...   # tenant 凭证表 → bootstrap env 兜底

def create_client(model: str, creds: Credential, *, base_url: str | None,
                  timeout: float | None) -> SupportsStreamingMessages:
    spec = detect_provider_from_registry(model, creds.api_key, base_url)
    return CLIENT_BUILDERS[spec.backend_type](creds, spec, ...)   # anthropic|openai_compat|codex|copilot
```

- 路由以 `backend_type` 驱动（替代供体 `ui/runtime.py` 的 5 分支 if）；
- client 按 `(backend_type, credential id)` 缓存复用（SDK 客户端带连接池）；
- LangGraph 侧桥接：`OpenHarnessChatModel` 薄壳把 chat 请求转 `ApiMessageRequest` 调内核 `stream_message`——**内核是我们要保留的资产**（Codex/Copilot 通道无现成 LangChain 集成），框架替换发生在桥接层。

## 5. 测试迁移

| 供体测试 | 迁移后 | 适配点 |
|---|---|---|
| `tests/test_api/test_client.py` | `tests/api/test_client.py` | import 路径；OAuth 用例改为"默认不注入、显式注入生效"两条 |
| `test_openai_client.py` | 同目录 | `_reasoning` 断言改 `msg.reasoning` 字段；env 名更新 |
| `test_codex_client.py` | 同目录 | httpx client 注入后的复用断言（`client.aclose` 不再每请求新建） |
| `test_copilot_client.py` / `test_copilot_auth.py` | 同目录 | headers 构造注入断言；TokenStore 用内存 fake |

## 6. 验收

1. 内核自身测试（§5 迁移后）全绿；
2. 平台三套冒烟不回归（`engine.smoke / smoke_graph / smoke_runner`，15 用例）——内核类型已在 serde 白名单；
3. `OpenHarnessChatModel` 桥接冒烟：Fake 网关换真内核客户端跑通一轮流式对话（dev 直连 key，见配置清单）；
4. 严格 msgpack 无新警告。

## 7. 排期（P1 内三步）

| 步 | 内容 | 退出条件 |
|---|---|---|
| D1 原样搬迁 | 拷贝 8 文件 + 改 import + 消息类型替换 + 测试迁移 | 内核测试全绿（无解耦改动） |
| D2 解耦改造 | §3 七项 + ClientFactory/registry | §6.1/6.2 全绿；`grep -r "Settings\|openharness" api/` 零命中 |
| D3 桥接联调 | OpenHarnessChatModel + 真供应商一轮流式 | §6.3 通过；run 级 usage 与事件映射正确 |
