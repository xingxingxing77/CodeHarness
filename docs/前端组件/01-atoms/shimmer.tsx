/**
 * Shimmer 原子（J24 本地化）：渐变扫光文字。
 * 消费方：selection-actions 忙碌态标签。
 */
import type { ReactNode } from "react";

/** 渐变扫光文本。 */
export function Shimmer({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`bg-clip-text text-transparent ${className}`}
      style={{
        backgroundImage:
          "linear-gradient(90deg, var(--ink-3) 35%, var(--ink) 50%, var(--ink-3) 65%)",
        backgroundSize: "200% 100%",
        animation: "shimmer-text 1.4s linear infinite",
      }}
    >
      {children}
    </span>
  );
}
