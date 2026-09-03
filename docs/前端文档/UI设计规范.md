# UI 设计规范

> 视觉语言，全部落在 `docs/前端组件/design-tokens/globals.css` 的双令牌体系上——本文不新增令牌，只规定**使用规则与语义映射**。
> 关联：[前端设计](前端设计.md)（页面与组件映射） · [UX布局设计](UX布局设计.md)（线框与交互决策）

## 1. 双令牌体系（既定，勿破坏）

- **裸 CSS 变量**（`--ink`、`--surface`…）：bui 组件内联 style 直接引用；
- **`@theme inline` 映射**（`--color-*`、`--shadow-*`、`--radius-*`）：生成工具类（`bg-ink`、`text-ink-2`、`shadow-card`、`rounded-control`…），inline 模式使工具类直引裸变量；
- **暗色**：`<html class="dark">` 整组覆盖裸变量，组件零改动。业务代码**禁止**写死 hex（R4 约定），新颜色必须先加令牌。

## 2. 色彩与语义映射

### 2.1 文字/图标灰阶（ink 三级）

| 令牌 | 用途 |
|---|---|
| `--ink` | 主文本、图标、强调数字 |
| `--ink-2` | 次要文本：表头、说明、时间戳、工具名 |
| `--ink-3` | 弱化文本：占位、行号、禁用态、辅助计数 |

正文对比度：`--ink`/`--surface` ≥ 12:1，`--ink-2` ≥ 5:1；`--ink-3` 仅用于 ≥12px 的辅助信息。

### 2.2 品牌与语义色

| 令牌 | 值(light) | 平台语义 |
|---|---|---|
| `--accent` / `--accent-tint` | `#5b5bf0` / 12% 混入 surface | 主操作、选中态、运行中脉冲（`records-pulse`）、链接（`--accent-ink`） |
| `--green` / `--green-tint` | `#25a878` / 14% | 成功：run_finished 正常结束、工具成功、status=done 药丸 |
| `--red` / `--red-tint` | `#ee5c61` / 14% | 错误：`is_error` 工具回执、error 事件、破坏性按钮 |
| `--orange` | `#f09a2f` | 警示：审批 risk_level=high、重试中 status、todo 药丸 |
| `--purple` | `#9a5cff` | 流程图条件卡（flowchart 专用，勿挪用） |

### 2.3 表面与结构（层级从低到高）

```
--page/--canvas（页面底 #f7f7f8）
  └ --surface（卡片/表格外层）
      └ --field/--inset（输入框、头像底、标签底）
分隔：--line（常规边框）、--line-strong（强边框/拖拽把手）
交互面：--hover、--hover-2（行悬停两级）
浮层：--tooltip-bg/fg/muted（深色 tooltip 三件，明暗两套均有定义）
```

规则：卡片只能落在 `--page/--canvas` 上；tooltip 恒用深底（暗色下换 `--tooltip-bg` 亮层次）；审批弹层用 `--surface` + `shadow-overlay`。

### 2.4 状态药丸（复用 filter-table 类）

| 平台状态 | 类 | 视觉 |
|---|---|---|
| 待处理 / queued | `.filter-status-todo` | orange 8% 底 + 35% 描边 |
| 运行中 / running | `.filter-status-progress` | accent 8% 底 + 脉冲点 |
| 已完成 / succeeded | `.filter-status-done` | green 10% 底 |
| 失败 / failed | 自建 `.filter-status-failed` | 按 red-tint 同构（提交令牌时一并加） |
| 挂起待审批 / interrupted | 自建 `.filter-status-approval` | orange + 图标 |

## 3. 字体与字号

- 字族：`--font-sans`（Inter 栈）/ `--font-mono`（JetBrains Mono 栈，代码、终端输出、tool input、event id）；
- 字号阶梯（沿 BUI 现值）：`11`（行号/角标）、`11.5`（tag）、`12`（说明/usage）、`12.5`（代码/表格正文）、`13`（表格/列表主文）；消息正文 **14px/1.65**（新增约定，Markdown 渲染基线）；标题 16/18/20；
- 数字场景（token 数、耗时、表格数值）一律 `tabular-nums`（`font-variant-numeric`，同 records 表）。

## 4. 圆角 / 阴影 / 间距

- 圆角：`--radius-control 8px`（按钮/输入）、`--radius-card 14px`（卡片）、`--radius-chip 9999px`（chip/药丸/头像）、小件 4~6px（checkbox 4、icon-button 6）；
- 阴影五级：`--shadow-btn`（按钮）< `--shadow-card`（卡片）< `--shadow-raised`（下拉/悬浮卡）< `--shadow-overlay`（弹层/tooltip）；`--shadow-hairline` 作 1px 描边替代（嵌套卡片用 hairline 不叠 card）；
- 间距：8px 基网；卡片三件套已内置——`primitive-card-pad 14/16`、`primitive-card-bar 9/16`、`primitive-card-footer 10/12`、表格单元格 `9/12`；区块间距 16/24/32。

## 5. 动效

| keyframes | 用途 | 平台场景 |
|---|---|---|
| `pop-in` / `pixel-on` | 卡片/弹层入场 | 工具卡完成、审批卡出现 |
| `fade-in` / `fade-up` | 列表项/面板 | 会话列表项、状态条 |
| `shimmer-text` | `shimmer` 占位微光 | 工具运行中、加载骨架 |
| `eq-bounce` | 脉冲点 | running 药丸、录音态 |
| `spin` | 旋转 loading | 全局 loading-state |

- 时长：过渡 150~200ms（悬停/选中），入场 250ms（`duration-250`），强调 400ms（`duration-400`）；easing 用组件内既定 `cubic-bezier(0.16,1,0.3,1)` / `(0.22,1,0.36,1)`；
- **流式节流**：`assistant_delta` 到达即入 buffer，渲染按 rAF 合帧（≤60fps），`streaming-text` 词级 blur-in 节奏以组件内置 WORD_MS 为准，不逐字重建 DOM；
- 动效可关：`prefers-reduced-motion` 下退化为直接呈现。

## 6. 图标与头像

- 图标统一 `lucide-react`（16px 线性，stroke 1.5~2），禁混第二套；
- 来源/会话头像用 `.source-avatar` 字母底座（`--field` 底 + `--ink-2` 字），不以图片头像为默认。

## 7. 焦点与可访问性

- 键盘焦点：交互件统一 `outline: 2px solid var(--accent); outline-offset: 2px`（未内建 focus 环的第三方处补齐）；
- 状态不裸靠颜色：失败/成功同时带图标或文案（药丸类已带边+底+文三通道）；
- 审批卡为关键操作：进入时 focus 落在主按钮（批准），Esc = 关闭（不等于拒绝，需明示"拒绝"按钮）；
- 目标热区 ≥ 24×24（tag/chip 视觉 20px 高但外包 4px 命中区）。

## 8. 新令牌申请流程

需要新颜色/新尺寸时：先在本文 §2/§4 登记语义 → `globals.css` light/dark 两组同时补 → `@theme inline` 映射 → 更新 `docs/前端组件/README.md` 依赖矩阵。禁止组件内私有 hex（流式头像、药丸类的令牌化改造是既有先例）。
