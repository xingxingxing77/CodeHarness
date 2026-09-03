# Beautiful UI 设计系统源码（本项目适配版）

> **来源**: RAG-v0 项目 `rag-web/src/components/bui/`（Beautiful UI 官方组件源码复制自 beautifului.dev，MIT，非 npm 包），已按 RAG-v0 架构决策 **J24** 完成依赖替换与本地化；设计令牌重建于 `design-tokens/globals.css`。
> **与官方原版差异**: 私有图标 `@central-icons-react` / `iconoir-react` → `lucide-react`；`liveline` → `recharts`；`posthog-js` 已剥离；`glimm` 仅 prompt-bar 残留；`Button`/`Shimmer`/`StreamText`/`GlideMenu` 已本地化为 `atoms/` 与 `primitives/`，**零私有依赖**。

## 目录结构

```
前端/
├── design-tokens/globals.css   # 设计令牌（Tailwind v4 @theme inline + .dark 覆盖 + keyframes），必须最先接入
├── 01-atoms/                   # 基础原子（纯 React，零外部依赖）
├── 02-primitives/              # 基础原语（纯 React，零外部依赖）
├── 03-chat-streaming/          # 聊天与流式
├── 04-cards/                   # 卡片展示
├── 05-tables/                  # 数据表格
├── 06-navigation/              # 导航与操作
├── 07-visualization/           # 可视化
└── 08-showcase/DesignSystem.tsx  # 20 组件展示场（dev-only 页面，用于目视验收）
```

## 组件清单

| 分类 | 文件 | 说明 |
|---|---|---|
| **01-atoms** | `button.tsx` | BUI 按钮（多 variant，shadcn Button 本地化） |
| | `entity-chip.tsx` | 实体/值标签（EntityChip、ValuePill） |
| | `shimmer.tsx` | 微光占位动画 |
| | `stream-text.tsx` | 打字机流式文本原子 |
| **02-primitives** | `glide-menu.tsx` | 卡片内联悬停滑动高亮容器（官方 GlideMenu 本地最小基元，非弹出菜单） |
| **03-chat-streaming** | `chat-composer.tsx` | 聊天输入框 |
| | `prompt-bar.tsx` | 输入提示条（语音/技能/文件上传）⚠️ 业务耦合 |
| | `SkillDialog.tsx` | 技能选择对话框 ⚠️ 业务耦合 |
| | `streaming-text.tsx` | 流式文本展示 |
| | `thinking-state.tsx` | 思考中状态 |
| | `loading-state.tsx` | 加载状态动效 |
| **04-cards** | `insight-cards.tsx` | 洞察卡组（内嵌 recharts 图表） |
| | `recommendation-card.tsx` | 建议卡 |
| | `fine-tune-card.tsx` | 微调配置卡（滑杆组） |
| | `approval-card.tsx` | 审批卡 |
| | `context-cards.tsx` | 上下文卡组 |
| **05-tables** | `records-table.tsx` | 记录表格 |
| | `diff-table.tsx` | 对比表 |
| | `filter-table.tsx` | 筛选表 |
| | `task-rows.tsx` | 任务行 |
| **06-navigation** | `sidebar-nav.tsx` | 侧边导航（含 portal） |
| | `search.tsx` | 搜索列表 |
| | `selection-actions.tsx` | 多选操作条 |
| | `tool-chips.tsx` | 工具标签 chips（含 portal） |
| **07-visualization** | `flowchart.tsx` | 流程图 |
| | `code-block.tsx` | 代码块 |
| **08-showcase** | `DesignSystem.tsx` | 组件展示场（引用以上 20 个组件） |

## 依赖矩阵

组件对 atoms/primitives 的内部依赖（搬运时需一并带上基础层）：

| 组件 | 依赖的基础件 |
|---|---|
| approval-card | atoms/button, primitives/glide-menu |
| diff-table | atoms/button |
| recommendation-card | atoms/button, atoms/entity-chip |
| fine-tune-card | primitives/glide-menu |
| records-table / search / sidebar-nav | primitives/glide-menu |
| selection-actions | atoms/shimmer, atoms/stream-text |

外部 npm 依赖：

| 包 | 使用组件 | 说明 |
|---|---|---|
| `react` / `react-dom` | 全部 | react-dom 仅 sidebar-nav、tool-chips 的 portal 用 |
| `lucide-react` | selection-actions、sidebar-nav | 图标 |
| `recharts` | insight-cards | 图表 |
| `glimm` | 仅 prompt-bar（彩虹扫光动效） | 可选，直接剥离不影响功能 |

⚠️ **RAG-v0 业务耦合（复用到其他项目必须剥离）**：

- `prompt-bar.tsx`：引用 `@/hooks/useChatStream`、`@/stores/chatStore`、`@/stores/configStore`、`@/api/promptBar`、`@/lib/speechRecognition`
- `SkillDialog.tsx`：引用 `@/api/promptBar`

其余组件均为纯展示件，可直接搬。

## 复用步骤（目标项目需 React 19 + Tailwind CSS 4）

1. **接入令牌**：将 `design-tokens/globals.css` 作为全局样式入口（文件内已含 `@import "tailwindcss"`；shadcn tokens 未初始化不冲突）。
2. **还原目录**：本目录的分类是为阅读组织；搬回代码时建议还原为扁平结构——`01-atoms` → `src/components/bui/atoms/`，`02-primitives` → `src/components/bui/primitives/`，其余组件平铺至 `src/components/bui/`（组件内部以 `@/components/bui/...` 相互引用）。
3. **装依赖**：`pnpm add lucide-react recharts`（`glimm` 可不装，剥离 prompt-bar 中的 3 行动效调用即可）。
4. **暗色模式**：`<html class="dark">` 切换，令牌经 `.dark` 整组覆盖，无需改组件。
5. **剥离业务耦合**：按上节清单处理 prompt-bar / SkillDialog（或首期不搬这两个）。
6. **验收**：把 `08-showcase/DesignSystem.tsx` 挂到一条 dev-only 路由，目视核对 20 个组件渲染与暗色表现。

---
*提取自 RAG-v0 @ d8a8037 · 2026-09-03*
