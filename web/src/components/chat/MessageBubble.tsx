"use client";

/** 消息气泡：user 右侧软块 / assistant Markdown；终态打字机回放 + 操作条（复制/赞/踩）。 */

import { useState } from "react";
import { Check, Copy, ThumbsDown, ThumbsUp } from "lucide-react";

import { MarkdownAnswer } from "@/components/chat/MarkdownAnswer";
import { TypewriterText } from "@/components/chat/TypewriterText";
import type { PlatformMessage } from "@/lib/types";

export function MessageBubble({
  message,
  typewriterTarget,
  onTypewriterDone,
}: {
  message: PlatformMessage;
  typewriterTarget: string | null;
  onTypewriterDone?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [vote, setVote] = useState<"up" | "down" | null>(null);
  const text = message.content
    .filter((b) => b.type === "text")
    .map((b) => (b as { text: string }).text)
    .join("");
  const toolCalls = message.content.filter((b) => b.type === "tool_call");

  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-card bg-accent-tint px-3.5 py-2.5 text-[14px] leading-[1.6] text-ink">
          {text}
        </div>
      </div>
    );
  }

  const replaying = typewriterTarget !== null && typewriterTarget === text;
  const actionBtn =
    "flex size-7 items-center justify-center rounded-[6px] text-ink-3 transition-colors hover:bg-hover hover:text-ink";

  return (
    <div className="group flex flex-col gap-1.5">
      {toolCalls.map((tc) =>
        tc.type === "tool_call" ? (
          <span
            key={tc.id}
            className="mr-1 inline-flex w-fit items-center gap-1 rounded-[5px] bg-inset px-1.5 py-0.5 text-[12px] text-ink-2"
          >
            ⚒ {tc.name}
          </span>
        ) : null,
      )}
      {replaying ? (
        <TypewriterText target={typewriterTarget} onDone={onTypewriterDone} />
      ) : (
        <MarkdownAnswer content={text} />
      )}
      {text && !replaying && (
        <div className="-ml-1 flex items-center gap-0.5">
          <button onClick={copy} className={actionBtn} aria-label="Copy" title="复制">
            {copied ? <Check className="size-3.5 text-accent-ink" /> : <Copy className="size-3.5" />}
          </button>
          <button
            onClick={() => setVote(vote === "up" ? null : "up")}
            className={`${actionBtn} ${vote === "up" ? "text-accent-ink" : ""}`}
            aria-label="Good response"
            aria-pressed={vote === "up"}
            title="有帮助"
          >
            <ThumbsUp className={`size-3.5 ${vote === "up" ? "fill-current" : ""}`} />
          </button>
          <button
            onClick={() => setVote(vote === "down" ? null : "down")}
            className={`${actionBtn} ${vote === "down" ? "text-red" : ""}`}
            aria-label="Bad response"
            aria-pressed={vote === "down"}
            title="需改进"
          >
            <ThumbsDown className={`size-3.5 ${vote === "down" ? "fill-current" : ""}`} />
          </button>
        </div>
      )}
    </div>
  );
}
