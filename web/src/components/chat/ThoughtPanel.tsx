"use client";

/**
 * 思考面板（用户参考件 ThinkingState + LoadingState 合并落地）：
 * 运行中 = Drive 像素网格 + shimmer 标签 + 计时器，trace 自动展开；
 * 结束 = 沉淀为 "Ran N tools / Thought for Ns"，默认收起、可展开回看。
 * 数据全部来自 chatStore（真实 thoughtSteps / tools），无演示序列。
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import type { ThoughtStep, ToolRun } from "@/stores/chatStore";

const chevron = Array.from({ length: 9 }, (_, i) => {
  const r = Math.floor(i / 3);
  const c = i % 3;
  return (c + Math.abs(r - 1)) * 90;
});

function LoaderGrid() {
  return (
    <span aria-hidden className="grid shrink-0 grid-cols-[repeat(3,4px)] gap-[1.5px]">
      {chevron.map((delay, index) => (
        <span
          key={index}
          className="size-[4px] rounded-[1px] bg-ink"
          style={{
            opacity: 0.15,
            animation: `pixel-on 650ms ease-in-out ${delay}ms infinite`,
          }}
        />
      ))}
    </span>
  );
}

function useElapsedDs(streaming: boolean) {
  const [ds, setDs] = useState(0);
  const prev = useRef(false);
  useEffect(() => {
    if (streaming && !prev.current) setDs(0);
    prev.current = streaming;
    if (!streaming) return;
    const t = setInterval(() => setDs((d) => d + 1), 100);
    return () => clearInterval(t);
  }, [streaming]);
  return ds;
}

function fmtElapsed(ds: number) {
  const total = ds / 10;
  if (total < 60) return `${total.toFixed(1)}s`;
  return `${Math.floor(total / 60)}m ${(total % 60).toFixed(1)}s`;
}

function Spinner() {
  return (
    <span
      className="size-3 shrink-0 rounded-full border-[1.5px] border-line-strong border-t-ink-2"
      style={{ animation: "spin 700ms linear infinite" }}
    />
  );
}

function Check() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--ink-3)"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
    >
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

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
  const ds = useElapsedDs(streaming);
  const traceRef = useRef<HTMLDivElement>(null);
  const [lineHeight, setLineHeight] = useState(0);

  const expanded = manual ?? streaming;

  useLayoutEffect(() => {
    if (traceRef.current) setLineHeight(traceRef.current.offsetHeight);
  }, [steps.length, tools.length, expanded]);

  if (steps.length === 0 && tools.length === 0 && !streaming) return null;

  const runningTool = tools.some((t) => t.status === "running");
  const label = streaming
    ? runningTool
      ? "Running tools"
      : "Thinking"
    : tools.length > 0
      ? tools.length === 1
        ? "Ran 1 tool"
        : `Ran ${tools.length} tools`
      : `Thought for ${(ds / 10).toFixed(1)}s`;

  // addTool 会同时压入 "调用 X" 占位 step，与 tool 行重复，跳过
  const stepRows = steps.filter((s) => !s.label.startsWith("调用 "));
  const rows: { key: string; node: React.ReactNode }[] = [
    ...stepRows.map((step, i) => ({
      key: `step:${i}`,
      node: (
        <>
          {step.state === "running" && streaming ? <Spinner /> : <Check />}
          <span className="min-w-0 truncate text-[12.5px] font-medium text-ink">{step.label}</span>
        </>
      ),
    })),
    ...tools.map((tool) => ({
      key: tool.key,
      node: (
        <>
          {tool.status === "running" ? <Spinner /> : tool.status === "error" ? (
            <span className="shrink-0 text-[12px] leading-none text-red">✗</span>
          ) : (
            <Check />
          )}
          <span className="min-w-0 truncate font-mono text-[12.5px] font-medium text-ink">{tool.tool_name}</span>
          {tool.status === "error" && <span className="shrink-0 text-[11.5px] text-red">失败</span>}
        </>
      ),
    })),
  ];

  const rowClass = "flex min-h-7 w-full items-center gap-2 rounded-[6px] px-1.5 py-0.5 text-left";

  return (
    <div className="thought-panel flex w-full max-w-[480px] flex-col">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setManual((current) => !(current ?? streaming))}
        className="-mx-1.5 flex w-fit items-center gap-2 rounded-[8px] px-1.5 py-1 transition-colors duration-100 hover:bg-hover-2"
      >
        {streaming ? (
          <LoaderGrid />
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="var(--ink-3)">
            <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z" />
          </svg>
        )}
        <span role="status" className="contents">
          {streaming ? (
            <span
              className="whitespace-nowrap bg-clip-text text-[13px] font-medium text-transparent"
              style={{
                backgroundImage:
                  "linear-gradient(90deg, var(--ink-3) 35%, var(--ink) 50%, var(--ink-3) 65%)",
                backgroundSize: "200% 100%",
                animation: "shimmer-text 1.4s linear infinite",
              }}
            >
              {label}
            </span>
          ) : (
            <span
              className="whitespace-nowrap text-[13px] font-medium text-ink-2"
              style={{ animation: "fade-in 350ms ease-out both" }}
            >
              {label}
            </span>
          )}
        </span>
        {streaming && (
          <span className="font-mono text-[12px] tabular-nums text-ink-3">{fmtElapsed(ds)}</span>
        )}
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--ink-3)"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="transition-transform duration-300"
          style={{ transform: expanded ? "rotate(180deg)" : "rotate(0)" }}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      <div
        className="grid transition-[grid-template-rows,opacity] duration-400"
        style={{
          gridTemplateRows: expanded ? "1fr" : "0fr",
          opacity: expanded ? 1 : 0,
          transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
        }}
      >
        <div className="overflow-hidden">
          <div className="relative mt-1 ml-[5px] pl-4">
            <span
              aria-hidden
              className="absolute left-[3px] top-[-8px] w-px bg-line"
              style={{
                height: lineHeight ? lineHeight - 2 : 0,
                transition: "height 500ms cubic-bezier(0.23,1,0.32,1)",
              }}
            />
            <div ref={traceRef} className="flex flex-col gap-1 py-1">
              {rows.map((row, i) => (
                <div
                  key={row.key}
                  className={rowClass}
                  style={{ animation: `fade-up 320ms cubic-bezier(0.23,1,0.32,1) ${Math.min(i, 8) * 120}ms both` }}
                >
                  {row.node}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
