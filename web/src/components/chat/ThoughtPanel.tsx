"use client";

/** 思考时间线（rag-web ThoughtPanel 对齐）：0fr→1fr 展开，流式自动展开、结束收起。 */

import { useState } from "react";

import { Shimmer } from "@/components/bui/atoms/shimmer";
import type { ThoughtStep, ToolRun } from "@/stores/chatStore";

export function ThoughtPanel({
  steps,
  tools,
  streaming,
}: {
  steps: ThoughtStep[];
  tools: ToolRun[];
  streaming: boolean;
}) {
  const [manual, setManual] = useState<boolean | null>(null);
  if (steps.length === 0 && tools.length === 0) return null;

  const expanded = manual ?? streaming;

  return (
    <div className="w-full rounded-[8px] border border-line bg-surface/60">
      <button
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left"
        onClick={() => setManual(!expanded)}
      >
        {streaming ? (
          <Shimmer className="text-[12px] font-medium">思考中…</Shimmer>
        ) : (
          <span className="text-[12px] font-medium text-ink-2">思考过程（{steps.length}）</span>
        )}
        <span className={`ml-auto text-ink-3 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}>
          ›
        </span>
      </button>

      <div
        className="grid transition-[grid-template-rows] duration-300"
        style={{ gridTemplateRows: expanded ? "1fr" : "0fr", transitionTimingFunction: "cubic-bezier(0.23,1,0.32,1)" }}
      >
        <div className="overflow-hidden">
          <div className="ml-3 flex flex-col gap-1 border-l border-line px-3 py-2">
            {steps.map((step, i) => {
              const isLast = i === steps.length - 1;
              const active = isLast && step.state === "running" && streaming;
              return (
                <div key={i} className="flex items-center gap-2 text-[12px] text-ink-2">
                  {active ? (
                    <span
                      className="size-1.5 rounded-full bg-accent"
                      style={{ animation: "eq-bounce 900ms ease-in-out infinite" }}
                    />
                  ) : (
                    <span className="text-green">✓</span>
                  )}
                  <span>{step.label}</span>
                </div>
              );
            })}
            {tools.map((tool) => (
              <div key={tool.key} className="flex items-center gap-2 text-[12px] text-ink-2">
                {tool.status === "running" ? (
                  <span
                    className="size-1.5 rounded-full bg-accent"
                    style={{ animation: "eq-bounce 900ms ease-in-out infinite" }}
                  />
                ) : tool.status === "error" ? (
                  <span className="text-red">✗</span>
                ) : (
                  <span className="text-green">✓</span>
                )}
                <span>
                  {tool.tool_name}
                  {tool.status === "running" ? "执行中…" : tool.status === "error" ? "失败" : "完成"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
