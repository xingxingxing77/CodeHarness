/**
 * DesignSystemPage（06 §7，dev-only /design）：BUI 20 件预览与目视验收载体。
 * 生产构建剔除（import.meta.env.DEV 路由门控，App.tsx）。
 * 目视抽检对照 beautifului.dev（落地方案 §8：令牌为反推初版，需微调）。
 */
import ApprovalCard from "@/components/bui/approval-card";
import ChatComposer from "@/components/bui/chat-composer";
import CodeBlock from "@/components/bui/code-block";
import ContextCards from "@/components/bui/context-cards";
import DiffTable from "@/components/bui/diff-table";
import FilterTable from "@/components/bui/filter-table";
import FineTuneCard from "@/components/bui/fine-tune-card";
import Flowchart from "@/components/bui/flowchart";
import InsightCards from "@/components/bui/insight-cards";
import LoadingState from "@/components/bui/loading-state";
import PromptBar from "@/components/bui/prompt-bar";
import RecommendationCard from "@/components/bui/recommendation-card";
import RecordsTable from "@/components/bui/records-table";
import SearchList from "@/components/bui/search";
import SelectionActions from "@/components/bui/selection-actions";
import SidebarNav from "@/components/bui/sidebar-nav";
import StreamingText from "@/components/bui/streaming-text";
import TaskRows from "@/components/bui/task-rows";
import ThinkingState from "@/components/bui/thinking-state";
import ToolChips from "@/components/bui/tool-chips";

/** 预览分区（编号对照 06 §10.4 映射表）。 */
const SECTIONS: { no: string; title: string; el: React.ReactNode }[] = [
  { no: "01", title: "Loading State", el: <LoadingState label="Churning" /> },
  { no: "02", title: "Thinking", el: <ThinkingState /> },
  { no: "03", title: "Streaming Text", el: <StreamingText /> },
  { no: "04", title: "Approval Card", el: <ApprovalCard /> },
  { no: "05", title: "Tool Chips", el: <ToolChips /> },
  { no: "06", title: "Task Rows", el: <TaskRows /> },
  { no: "07", title: "Chat Composer", el: <ChatComposer /> },
  { no: "08", title: "Prompt Bar", el: <PromptBar demo tall /> },
  { no: "09", title: "Recommendation Card", el: <RecommendationCard /> },
  { no: "10", title: "Context Cards", el: <ContextCards /> },
  { no: "11", title: "Diff Table", el: <DiffTable /> },
  { no: "12", title: "Records Table", el: <RecordsTable /> },
  { no: "13", title: "Filter Table", el: <FilterTable /> },
  { no: "14", title: "Sidebar Nav", el: <SidebarNav /> },
  { no: "15", title: "Search", el: <SearchList /> },
  { no: "16", title: "Flowchart", el: <Flowchart /> },
  { no: "17", title: "Insight Cards", el: <InsightCards /> },
  { no: "18", title: "Code Block", el: <CodeBlock /> },
  { no: "19", title: "Fine-tune Card", el: <FineTuneCard /> },
  { no: "20", title: "Selection Actions", el: <SelectionActions /> },
];

export default function DesignSystemPage() {
  return (
    <div className="min-h-screen bg-canvas p-8">
      <header className="mx-auto mb-8 max-w-5xl">
        <h1 className="text-xl font-semibold text-ink">Beautiful UI · 设计系统预览</h1>
        <p className="mt-1 text-sm text-neutral-500">
          20 件 · dev-only · 目视对照 beautifului.dev 微调（落地方案 §8）
        </p>
      </header>
      <div className="mx-auto grid max-w-5xl grid-cols-1 items-start gap-6 lg:grid-cols-2">
        {SECTIONS.map((s) => (
          <section
            key={s.no}
            className="rounded-card border border-line bg-surface p-5 shadow-card"
          >
            <div className="mb-3 flex items-baseline gap-2">
              <span className="font-mono text-[11px] text-neutral-400">{s.no}</span>
              <h2 className="text-sm font-semibold text-ink">{s.title}</h2>
            </div>
            {s.el}
          </section>
        ))}
      </div>
    </div>
  );
}
