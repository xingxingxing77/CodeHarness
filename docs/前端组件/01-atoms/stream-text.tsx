/**
 * StreamText 原子（J24 本地化）：逐字流式渲染。
 * 消费方：selection-actions 重写流（onProgress 供锚定重算，onDone 收尾）。
 */
import { useEffect, useRef, useState } from "react";

interface StreamTextProps {
  text: string;
  /** 每帧回调（selection-actions 用它重算气泡锚位） */
  onProgress?: () => void;
  /** 全文渲染完成回调 */
  onDone?: () => void;
  /** 每秒字符数 */
  cps?: number;
}

/** 逐字流式文本。 */
export function StreamText({ text, onProgress, onDone, cps = 60 }: StreamTextProps) {
  const [count, setCount] = useState(0);
  const progressRef = useRef(onProgress);
  const doneRef = useRef(onDone);
  progressRef.current = onProgress;
  doneRef.current = onDone;

  useEffect(() => {
    if (count >= text.length) {
      doneRef.current?.();
      return;
    }
    const t = setTimeout(() => {
      setCount((c) => Math.min(text.length, c + 1));
      progressRef.current?.();
    }, 1000 / cps);
    return () => clearTimeout(t);
  }, [count, text, cps]);

  return <span>{text.slice(0, count)}</span>;
}
