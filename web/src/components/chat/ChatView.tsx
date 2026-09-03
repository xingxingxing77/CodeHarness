"use client";

/** 聊天页主视图：chatStore 驱动；时间线/思考面板/审批/暗色切换/滚动锚定。 */

import { useEffect, useRef, useState } from "react";

import { ValuePill } from "@/components/bui/atoms/entity-chip";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { ComposerBar } from "@/components/chat/ComposerBar";
import { ThoughtPanel } from "@/components/chat/ThoughtPanel";
import { mapErrorText } from "@/lib/errors";
import { useChatStream } from "@/hooks/useChatStream";
import { useChatStore } from "@/stores/chatStore";

export function ChatView({ sessionId }: { sessionId: string }) {
  const { send, decide } = useChatStream(sessionId);
  const messages = useChatStore((s) => s.messages);
  const live = useChatStore((s) => s.live);
  const thoughtSteps = useChatStore((s) => s.thoughtSteps);
  const tools = useChatStore((s) => s.tools);
  const status = useChatStore((s) => s.status);
  const usage = useChatStore((s) => s.usage);
  const approval = useChatStore((s) => s.approval);
  const finished = useChatStore((s) => s.finished);
  const typewriterTarget = useChatStore((s) => s.typewriterTarget);
  const setTypewriterTarget = useChatStore((s) => s.setTypewriterTarget);
  const lastError = useChatStore((s) => s.lastError);

  const bottomRef = useRef<HTMLDivElement>(null);
  const [stick, setStick] = useState(true);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("codeharness_theme", next ? "dark" : "light");
  };

  useEffect(() => {
    if (stick) bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, live, tools, thoughtSteps, stick]);

  const running = !finished;
  const liveText = live?.content.find((b) => b.type === "text");
  const errorBlock =
    lastError !== null ? (
      <div className="flex items-start gap-2 rounded-card border border-line bg-red-tint px-3 py-2 text-[13px] text-ink">
        <span className="text-red">⚠</span>
        <span>{mapErrorText(lastError?.code)}{lastError?.message ? `：${lastError.message}` : ""}</span>
      </div>
    ) : null;

  return (
    <div className="flex h-dvh flex-col bg-page">
      <header className="flex items-center gap-2 border-b border-line bg-surface px-4 py-2.5">
        <a href="/" className="text-[12.5px] text-ink-2 hover:text-ink">
          ← Sessions
        </a>
        <span className="text-[13px] font-medium text-ink">{sessionId.slice(0, 8)}</span>
        {status && <span className="text-[12px] text-ink-2">{status}</span>}
        <button onClick={toggleTheme} className="ml-auto text-[12px] text-ink-3 hover:text-ink">
          {dark ? "☀" : "☾"}
        </button>
        {usage && (
          <span className="text-[11.5px] tabular-nums text-ink-3">
            {usage.input_tokens} in / {usage.output_tokens} out
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
          {messages.length === 0 && !running && !live && (
            <div className="mt-24 flex flex-col items-center gap-2 text-center">
              <div className="text-[20px] font-medium text-ink">Codeharness</div>
              <div className="text-[12.5px] text-ink-2">Send a message to start the agent loop.</div>
            </div>
          )}

          {messages.map((m, i) => {
            const isLast = i === messages.length - 1;
            const target =
              isLast && m.role === "assistant" && typewriterTarget !== null ? typewriterTarget : null;
            return (
              <MessageBubble
                key={i}
                message={m}
                typewriterTarget={target}
                onTypewriterDone={() => setTypewriterTarget(null)}
              />
            );
          })}

          <ThoughtPanel steps={thoughtSteps} tools={tools} streaming={running} />

          {live && liveText && liveText.type === "text" && (
            <div className="text-[14px] leading-[1.65] text-ink">
              {liveText.text}
              <span className="ml-0.5 inline-block h-3 w-0.5 translate-y-[2px] bg-accent" />
            </div>
          )}

          {errorBlock}

          {approval && <ApprovalDialog approval={approval} onDecide={decide} />}

          {finished && usage && (
            <div className="text-right text-[11.5px] tabular-nums text-ink-3">
              run finished · {usage.total_tokens} tokens
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

  function ApprovalDialog({
    approval,
    onDecide,
  }: {
    approval: { ticket_id: string; run_id: string; items: { call_id: string; tool_name: string; reason: string; risk_level: string; input_preview: string }[] };
    onDecide: (ticketId: string, runId: string, choices: { call_id: string; approve: boolean; reason?: string }[]) => void;
  }) {
    const [busy, setBusy] = useState(false);

    const submit = (approve: boolean) => {
      setBusy(true);
      onDecide(
        approval.ticket_id,
        approval.run_id,
        approval.items.map((i) => ({
          call_id: i.call_id,
          approve,
          reason: approve ? "approved in UI" : "denied in UI",
        })),
      );
    };

    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        style={{ background: "rgb(20 20 40 / 0.25)" }}
      >
        <div
          className="w-full max-w-[520px] rounded-card border border-line bg-surface shadow-raised"
          style={{ animation: "fade-up 250ms cubic-bezier(0.16,1,0.3,1) both" }}
        >
          <div className="primitive-card-bar flex items-center gap-2 border-b border-line">
            <span className="text-[12.5px] font-medium text-ink">Approval required</span>
            <ValuePill>{approval.items.length} item(s)</ValuePill>
          </div>
          <div className="flex flex-col gap-3 p-4">
            {approval.items.map((item) => (
              <div key={item.call_id} className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-medium text-ink">{item.tool_name}</span>
                  <ValuePill>{item.risk_level}</ValuePill>
                </div>
                {item.reason && <div className="text-[12px] text-ink-2">{item.reason}</div>}
                <pre className="max-h-32 overflow-auto rounded-[6px] bg-inset p-2 font-mono text-[12px] text-ink-2">
                  {item.input_preview || "(no input)"}
                </pre>
              </div>
            ))}
            <div className="flex items-center justify-end gap-2">
              <button
                disabled={busy}
                onClick={() => submit(false)}
                className="inline-flex h-8 items-center rounded-full border border-line px-3 text-[13px] font-medium text-ink transition-colors hover:bg-hover disabled:opacity-40"
              >
                Deny
              </button>
              <button
                disabled={busy}
                onClick={() => submit(true)}
                className="inline-flex h-8 items-center rounded-full bg-accent px-3 text-[13px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                Approve
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }
}
