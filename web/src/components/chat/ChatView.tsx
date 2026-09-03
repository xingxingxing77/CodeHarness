"use client";

/** 聊天页主视图：时间线（消息/工具行/流式/状态/审批）+ 输入区（前端设计 §3）。 */

import { useEffect, useRef, useState } from "react";

import { Shimmer } from "@/components/bui/atoms/shimmer";
import { ValuePill } from "@/components/bui/atoms/entity-chip";
import { ApprovalPanel } from "@/components/chat/ApprovalPanel";
import { ComposerBar } from "@/components/chat/ComposerBar";
import { ToolRunRow } from "@/components/chat/ToolRunRow";
import { useChatStream } from "@/hooks/useChatStream";

export function ChatView({ sessionId }: { sessionId: string }) {
  const { state, send, decide } = useChatStream(sessionId);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [stick, setStick] = useState(true);

  useEffect(() => {
    if (stick) bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [state.messages, state.streamingText, state.tools, state.status, stick]);

  const running = !state.finished;

  return (
    <div className="flex h-dvh flex-col bg-page">
      <header className="flex items-center gap-2 border-b border-line bg-surface px-4 py-2.5">
        <a href="/" className="text-[12.5px] text-ink-2 hover:text-ink">
          ← Sessions
        </a>
        <span className="text-[13px] font-medium text-ink">{sessionId.slice(0, 8)}</span>
        {state.status && <span className="text-[12px] text-ink-2">{state.status}</span>}
        {state.usage && (
          <span className="ml-auto text-[11.5px] tabular-nums text-ink-3">
            {state.usage.input_tokens} in / {state.usage.output_tokens} out
          </span>
        )}
      </header>

      <div
        className="flex-1 overflow-y-auto"
        onScroll={(e) => {
          const el = e.currentTarget;
          setStick(el.scrollHeight - el.scrollTop - el.clientHeight < 48);
        }}
      >
        <div className="mx-auto flex w-full max-w-[760px] flex-col gap-4 px-4 py-6">
          {state.messages.length === 0 && !running && (
            <div className="mt-24 flex flex-col items-center gap-2 text-center">
              <div className="text-[20px] font-medium text-ink">Codeharness</div>
              <div className="text-[12.5px] text-ink-2">Send a message to start the agent loop.</div>
            </div>
          )}

          {state.messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : "flex flex-col gap-2"}>
              <div
                className={
                  m.role === "user"
                    ? "max-w-[80%] rounded-card bg-accent-tint px-3.5 py-2.5 text-[14px] leading-[1.6] text-ink"
                    : "text-[14px] leading-[1.65] text-ink"
                }
              >
                {m.content.map((block, bi) => {
                  if (block.type === "text") return <span key={bi}>{block.text}</span>;
                  if (block.type === "tool_call")
                    return (
                      <span key={bi} className="mr-1 inline-flex items-center gap-1 rounded-[5px] bg-inset px-1.5 py-0.5 text-[12px] text-ink-2">
                        ⚒ {block.name}
                      </span>
                    );
                  return null;
                })}
              </div>
              {/* 工具结果紧随其 assistant 轮 */}
              {m.role === "user" &&
                state.tools
                  .filter((t) => t.status !== "running")
                  .slice(-1)
                  .map((t) => <ToolRunRow key={t.key} tool={t} />)}
            </div>
          ))}

          {state.tools.some((t) => t.status === "running") && (
            <div className="flex flex-col gap-1">
              {state.tools
                .filter((t) => t.status === "running")
                .map((t) => (
                  <ToolRunRow key={t.key} tool={t} />
                ))}
            </div>
          )}

          {state.streamingText && (
            <div className="text-[14px] leading-[1.65] text-ink">
              {state.streamingText}
              <span className="ml-0.5 inline-block h-[14px] w-[2px] translate-y-[2px] bg-accent" style={{ animation: "fade-in 300ms ease alternate infinite" }} />
            </div>
          )}

          {running && !state.streamingText && state.status && (
            <div className="text-[12.5px] text-ink-3">{state.status}</div>
          )}

          {state.approval && (
            <ApprovalPanel approval={state.approval} onDecide={decide} />
          )}

          {state.finished && state.usage && (
            <div className="text-right text-[11.5px] tabular-nums text-ink-3">
              run finished · {state.usage.total_tokens} tokens
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <div className="mx-auto w-full max-w-[760px] px-4 pb-4">
        <ComposerBar running={running} onSend={(text) => send(text)} />
      </div>
    </div>
  );
}
