"use client";

/** 终态打字机回放（rag-web 范式）：rAF 48cps 分片，卸载快进防截断。 */

import { useEffect, useState } from "react";

export function useTypewriter(target: string | null, cps = 48) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    setCount(0);
    if (!target) return;

    let shown = 0;
    let acc = 0;
    let last: number | null = null;
    let raf = 0;

    const tick = (now: number) => {
      if (last === null) last = now;
      acc += ((now - last) / 1000) * cps;
      last = now;
      const step = Math.floor(acc);
      if (step > 0) {
        acc -= step;
        shown = Math.min(shown + step, target.length);
        setCount(shown);
      }
      if (shown < target.length) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      setCount(target.length); // 卸载快进：防止展示被截断
    };
  }, [target, cps]);

  const shown = target ? target.slice(0, count) : "";
  const done = !target || count >= target.length;
  const skip = () => setCount(target?.length ?? 0);

  return { shown, done, skip };
}
