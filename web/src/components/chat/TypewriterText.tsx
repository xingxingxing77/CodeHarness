"use client";

/** 终态打字机回放组件：块状光标 + 「立即显示全部」skip。 */

import { useEffect } from "react";

import { useTypewriter } from "@/hooks/useTypewriter";

export function TypewriterText({ target, onDone }: { target: string; onDone?: () => void }) {
  const { shown, done, skip } = useTypewriter(target);

  useEffect(() => {
    if (done) onDone?.();
  }, [done, onDone]);

  return (
    <div className="flex flex-col gap-1">
      <div className="text-[14px] leading-[1.65] text-ink">
        {shown}
        {!done && <span className="ml-0.5 inline-block h-3 w-0.5 translate-y-[2px] bg-ink" />}
      </div>
      {!done && (
        <button
          onClick={() => {
            skip();
            onDone?.();
          }}
          className="self-start text-[11.5px] text-ink-3 hover:text-ink-2"
        >
          立即显示全部
        </button>
      )}
    </div>
  );
}
