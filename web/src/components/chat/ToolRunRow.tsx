"use client";

/** 工具执行行（状态 chip + 输出；diff/terminal 按 ui.kind 分发）。 */

import { useState } from "react";

import { ValuePill } from "@/components/bui/atoms/entity-chip";
import type { ToolRun } from "@/hooks/useChatStream";

export function ToolRunRow({ tool }: { tool: ToolRun }) {
  const [open, setOpen] = useState(false);
  const tone = tool.status === "error" ? "red" : tool.status === "done" ? "green" : undefined;
  const diffLines = tool.ui?.kind === "diff" ? String(tool.ui.data.diff ?? "").split("\n") : null;

  return (
    <div className="flex w-full flex-col gap-1">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-control px-2 py-1 text-left transition-colors hover:bg-hover"
      >
        <span
          className="size-1.5 rounded-full"
          style={{
            background: tool.status === "running" ? "var(--accent)" : tool.status === "error" ? "var(--red)" : "var(--green)",
            animation: tool.status === "running" ? "eq-bounce 900ms ease-in-out infinite" : undefined,
          }}
        />
        <span className="text-[12.5px] font-medium text-ink">{tool.tool_name}</span>
        {tool.status === "running" && (
          <span className="text-[11.5px] text-ink-3" style={{ backgroundImage: "linear-gradient(90deg, var(--ink-3) 35%, var(--ink) 50%, var(--ink-3) 65%)", backgroundClip: "text" }}>
            running…
          </span>
        )}
        <ValuePill tone={tone === "green" ? "green" : undefined}>{tool.status}</ValuePill>
      </button>
      {open && (
        <div className="ml-4 rounded-[8px] border border-line bg-surface p-2">
          {diffLines ? (
            <pre className="overflow-x-auto font-mono text-[12px] leading-[1.55]">
              {diffLines.map((line, i) => (
                <div
                  key={i}
                  className={
                    line.startsWith("+") && !line.startsWith("+++")
                      ? "text-green"
                      : line.startsWith("-") && !line.startsWith("---")
                        ? "text-red"
                        : "text-ink-2"
                  }
                >
                  {line || " "}
                </div>
              ))}
            </pre>
          ) : (
            <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-[12px] leading-[1.55] text-ink-2">
              {tool.output ?? "(no output)"}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
