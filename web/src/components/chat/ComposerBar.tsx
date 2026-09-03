"use client";

/** 输入区（落底 bar 形态；Enter 发送 / Shift+Enter 换行）。 */

import { useState, type KeyboardEvent } from "react";

import { Button } from "@/components/bui/atoms/button";

export function ComposerBar({
  disabled,
  running,
  onStop,
  onSend,
}: {
  disabled?: boolean;
  running?: boolean;
  onStop?: () => void;
  onSend: (text: string) => void;
}) {
  const [draft, setDraft] = useState("");

  const submit = () => {
    if (!draft.trim() || disabled || running) return;
    onSend(draft.trim());
    setDraft("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex items-end gap-2 border-t border-line bg-surface p-3">
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        rows={1}
        placeholder="Ask anything… (Enter to send, Shift+Enter for newline)"
        className="max-h-40 min-h-[38px] flex-1 resize-none rounded-control border border-line bg-field px-3 py-2 text-[13.5px] text-ink outline-none placeholder:text-ink-3 focus:border-accent"
      />
      {running ? (
        <Button variant="secondary" onClick={onStop}>
          Stop
        </Button>
      ) : (
        <Button onClick={submit} disabled={disabled || !draft.trim()}>
          Send
        </Button>
      )}
    </div>
  );
}
