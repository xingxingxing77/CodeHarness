"use client";

/** 消息气泡：user 右侧软块 / assistant Markdown；终态打字机回放 + 复制按钮。 */

import { useState } from "react";

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

  return (
    <div className="group flex flex-col gap-2">
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
      {typewriterTarget !== null && typewriterTarget === text ? (
        <TypewriterText target={typewriterTarget} onDone={onTypewriterDone} />
      ) : (
        <MarkdownAnswer content={text} />
      )}
      {text && (
        <button
          onClick={copy}
          className="self-start text-[11px] text-ink-3 opacity-0 transition-opacity hover:text-ink-2 group-hover:opacity-100"
        >
          {copied ? "已复制" : "复制"}
        </button>
      )}
    </div>
  );
}
