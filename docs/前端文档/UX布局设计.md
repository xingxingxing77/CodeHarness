# UX 布局设计

> 布局与交互决策的权威文档。参考 AgentCore《前端UX设计》的决策框架与文风，全部组件落点为本项目 BUI 组件库（`docs/前端组件/`，20 组件）。
> 权威划分：视觉令牌/色彩/动效 → [UI设计规范](UI设计规范.md)；页面清单/数据流/接口消费 → [前端设计](前端设计.md)；本文只管**布局与交互决策**。

## 权威归属表

| 主题 | 权威文档 |
|---|---|
| 设计令牌、色彩语义、动效、焦点环 | [UI设计规范](UI设计规范.md) |
| 页面路由、SSE→组件映射、状态管理、断线续传 | [前端设计](前端设计.md) |
| 全局布局、侧栏 IA、对话页、审批、右坞、工具箱、模型、搜索 | **本文** |
| SSE 事件 payload、REST schema | [接口契约](../接口文档/接口契约.md) |

心智：「**指挥一支带工具的 Agent 团队**」。原则：渐进揭示、简单任务零噪音、错误可见可逆、审批永远可达。

## 一、全局布局与侧栏

壳层 = `sidebar-nav` 固定左栏（组件内建折叠：`data-sidebar-collapsed` 驱动，展开/折叠宽度以组件为准）+ 主区自布局；无全局顶栏（会话页自带状态条）。侧栏底部固定区：审批角标（`/approvals` 未决数）· 主题切换（`.dark` 持久化）· 租户/设置入口。

**侧栏 IA 三区**（无标题，分隔线区分）：

| 区 | 内容 | 行为 |
|---|---|---|
| 顶 | **「等你」组**（有 `interrupted` run 的会话，orange 光环）+ 置顶对话 | 「等你」挤进盖过、不写回排序；决策完成后自动归位 |
| 中 | 会话分组（P2 按最近活跃日、P3 用户文件夹），Top 5/组 | 组头可拖排序；拖过后手排钉死、活动不跳组 |
| 底 | 未置顶扁平（有分组 10 条 / 无分组 15 条） | 按最近活动（`updated_at`，仅用户句/占位/助手 upsert 写入） |

列表行 = `entity-chip` 状态点（运行中=accent 脉冲 `records-pulse`、等你=orange、空闲=无）+ 标题 + `last_message_preview`（读时投影最后可见助手句，跳过空/running，禁回落用户句）。**否决**跨区「最近」重复列表、置顶与组内双显。

「对话」导航项 = 新建草稿（`/` 唯一真相）。**切会话落点**：无目的地贴最新底部，贴底时跟随异步撑高；搜索/深链命中才跳目标。**否决**记住每条对话滚动位置。

**窄屏壳（<768px）**：底栏 4-tab（对话 / 审批 / 文件 / 设置）+ 对话页 ☰ 抽屉替代侧栏 + 右坞改全屏 sheet；文件/设置走列表推进详情。

**全局协作感知**：运行中会话的状态点脉动；跨会话 run_finished → toast（`finish_reason` 语义见接口文档，`error` 非完成）。

## 二、对话页

单栏聊天；消息流 `max-w-[760px]` 居中（表格类内件不受限，对齐 BUI `records-shell` 手感）。

**输入框双形态**（FLIP 切换）：
- 空草稿居中 `card`：摊开三件——模型组合 chip、权限配方 chip、@ 引用；**否决**空草稿只留输入+发送（第一屏就要选地方）；
- 首条后落底 `bar`：`prompt-bar`（＋收纳配置 · 输入 · 发送）；`chat-composer` 作多行输入底座。**否决**「＋」改成附件入口（ChatGPT 回形针式）——附件走 @ 引用，＋只收配置。

**@ 引用**：文件(P2)/会话(P3)/技能(P4) 点选后落输入**正文药丸**（`entity-chip`），与句子同一序列、两侧可继续打字；**否决**框外芯片托盘（与正文两条路径）。输入粘贴只吃纯文本，划词复制只出纯文本。

**消息时间线（ProcessTimeline 风格）**：`thinking-state`（思考空态）→ `streaming-text`（正文流式）→ 工具行（`tool-chips` 状态 chip + `task-rows` 明细）按 SSE 到达时序**交织**，不按类型归桶；末段正文 = 答案。连续 ≥2 工具保序折叠（纯渲染，展开保留全部）；失败走红卡不叠灰标；复制两档（仅交付 / 含过程）。**否决**常驻吵闹工具卡、按类别分桶。

**流式渲染**：SSE `assistant_delta` 入 buffer + rAF 合帧上屏（≤60fps），新词 `fade-in` 入场；流末光标常显。**否决**逐 token 字级打字机（与合帧、停止诚实性冲突；BUI `streaming-text` 的 blur-in 仅作新词入场动效，非逐字动画）。

**停止与插队**：run 运行中输入框位置常显「停止生成」（run 级硬停，`POST /runs/{id}/cancel`）；**否决**把停止塞进状态条。

**用户气泡**：不渲染工具铬条；旧消息无标记；assistant 消息头部仅 stop_reason 角标（`metadata`，不参与路由语义）。

代码落点：`web/src/components/chat/ProcessTimeline.tsx`、`hooks/useChatScroll.ts`、`hooks/useComposerDockFlip.ts`、`components/chat/ComposerBar.tsx`。

## 三、审批（HITL）

`approval-card` 双入口：
1. **会话内 sticky**：interrupt 后卡置顶于时间线头部，运行区域遮罩淡灰；卡面 = 逐项 `ApprovalItem`（`tool_name` + `input_preview`（mono 块，`code-block`）+ `risk_level` 药丸 + reason）；
2. **审批中心** `/approvals`：`records-table` 跨会话待审列表（状态药丸：pending=progress、expired=failed、decided=done）。

交互：主按钮**批准**（accent，进入时 focus 落此）/ **拒绝**（red 描边，需填 reason 可空）；TTL 倒计时显式展示（默认 30min）；决策后卡折叠为结果条（含 decided_by）。决策 → `POST /runs/{rid}/approvals/{tid}/decide`，他端设备经 SSE 续播。**否决**卡内逐项二次确认；**否决**超时静默——expired 必须显式提示「已超时按拒绝处理」。

## 四、右坞 SidePanel（Web 应用内浮窗）

主坞 = 停靠条 + 右侧布局槽；关主坞 = 收起槽不销毁浮窗。顶栏 = `[内容 tabs] [+]`；tabs 多开并存、可拖排序、上限 **12**。`+` 菜单：run 详情 / 文件预览(P2) / 改动 diff(P3) / 终端(P4)。

- **run 详情**：时间线与主对话同一 stick 语义（进行中贴底跟随、上滑脱钩 + 回到底部；回看已结束 run 打开置顶）；按人干预按钮仅在 `running` 时渲染，终局整条不渲染（点不动的按钮没有下一步）；
- **改动 tab**：本会话 AI 文件改动聚合，`diff-table` 只读；行标签 = 新建/更新/删除（相对回合基线，**否决**用工具名当标签）；出现 = 用户显式打开，**否决**写盘自动挂；
- **浮窗**：Web 为应用内浮窗（几何限于客户区），上限 **8**；桌面 OS 真窗 P4 再议。**否决**覆盖式单 tab、并排双右坞、诊断/开发者模式。

## 五、首启与空态

激活 = 首个成功 run；**无接入门、无 form gate、无多步 Tour**（平台代付试用额度由运营层决定）。空草稿态 = 欢迎语 + starter chips（「读一个文件」「改一段代码」「搜索资料」，点击即填入输入框）；starter chips 仅对零 run 用户出现。列表/网格页空态统一 `shimmer` 骨架 + `EmptyHint` 式说明卡；情境提示全应用 ≤3 处。

## 六、工具箱（P4）

卡片网格（`recommendation-card` 骨架复用）：技能（SKILL.md）并入「AI 提示词」区，**否决**技能与插件并列竞争卡；MCP 连接器单独区（连接状态 chip）；官方模板只读，「使用」= 复制为我的再改。

## 七、模型与自主度

- **会话选组合不选裸模型**：组合 = model + effort（来自 `api/` 注册表 + 租户凭证可用集）；picker 只填目录身份；凭证管理在设置页（写入即加密、永不回显）；
- **权限配方三选一**：谨慎（全部要批）/ 标准（默认，写操作与危险命令要批）/ 托管（只读外全批）→ 映射 permissions 策略配方；会话内「＋」可切，「改某一条」才展开参数轴；**否决**账户级角色→模型矩阵、质量档、自动降级；
- Composer「＋」常显：工作区(P2) · 模型 · 权限 · @ 引用。

## 八、搜索

`Cmd+K` 全局命令板：会话/消息（P2 标题+内容匹配，P3 升级 pgvector 语义检索）；页内筛选；`Cmd+F` 页内查找。**否决**顶栏常驻全局搜索框。

## 九、多智能体（P4）

`/agents` 页：`flowchart` 协作图（节点=队员 run，边=派工/信箱）+ `task-rows` 任务清单；点节点 → 右坞开该队员 run 详情；信箱未读走侧栏角标。**否决**把协作摘要渲染进气泡顶栏铬条。

## 十、快捷键

| 键 | 行为 |
|---|---|
| `Cmd/Ctrl+K` | 全局搜索/命令板 |
| `Cmd/Ctrl+B` | 折叠/展开侧栏 |
| `Enter` / `Shift+Enter` | 发送 / 换行 |
| `Esc` | 关浮层/抽屉（≠ 拒绝审批） |
| `Cmd/Ctrl+C` 划词 | 复制（只出纯文本） |

## 十一、待定

虚拟滚动（>500 消息会话）、无障碍审计（screen reader 全链路）、移动端手势、桌面 OS 真窗、消息收藏 facet。

## 附：BUI 组件 → 使用位置总表

| BUI 组件 | 使用位置 |
|---|---|
| `button` | 全局按钮底座（批准/拒绝/发送） |
| `entity-chip` | 侧栏状态点、@ 药丸、模型/权限 chip |
| `shimmer` | 运行中占位、骨架空态 |
| `stream-text`(atom) | 流式文本原子（streaming-text 内部） |
| `glide-menu` | 卡片内联高亮（approval/表格容器） |
| `chat-composer` | 输入底座（多行） |
| `prompt-bar` | 落底 bar 形态（剥离业务耦合后接 useChatStream） |
| `SkillDialog` | 技能选择（P4，剥离后接平台 skills 接口） |
| `streaming-text` | 正文流式 |
| `thinking-state` | 思考空态 |
| `loading-state` | 全局加载动效 |
| `approval-card` | 会话内 sticky 审批卡 |
| `context-cards` | @ 引用/工作区上下文卡 |
| `insight-cards` | usage 统计卡（P3） |
| `recommendation-card` | starter chips / 工具箱卡 |
| `fine-tune-card` | 权限参数轴展开面 |
| `diff-table` | 改动 tab / 写文件类 tool ui |
| `records-table` | 审批中心 / 凭证 / 记忆列表 |
| `filter-table` | run 历史/审计筛选 |
| `task-rows` | 工具执行明细、队员任务 |
| `sidebar-nav` | 全局侧栏 |
| `search` | 审批中心/记忆页筛选列表 |
| `selection-actions` | 列表多选批量操作 |
| `tool-chips` | 工具状态 chip |
| `flowchart` | 协作图（P4） |
| `code-block` | input_preview、终端类 ui |
| `DesignSystem` | dev-only `/design` 验收路由 |

新建业务组件（`web/src/components/`）：`chat/ProcessTimeline`、`chat/MessageGroup`、`chat/ComposerBar`、`chat/RunStatusBar`、`approval/ApprovalSticky`、`panel/SidePanelHost`、`panel/RunDetailTimeline`、`EmptyHint`。
