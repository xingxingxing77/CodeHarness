/**
 * GlideMenu 基元（J24 偏差落地，用户定案 2026-08-24）。
 *
 * 官方源码中 GlideMenu 并非弹出菜单，而是"卡片内联的悬停滑动高亮容器"——
 * 单个高亮药丸在行间滑动（hover 优先，回落到 aria-pressed/aria-checked 选中行）。
 * 改 shadcn Popover 会破坏 5 处内联交互，故按 J24"不引入私有依赖"的本意
 * 本地实现最小基元（约 60 行），偏差已登记 06 §10.2 / 落地方案 §2。
 *
 * 行元素须带 rowSelector 匹配属性（默认 [data-menu-row]）且自带 relative z-10。
 */
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

interface GlideMenuProps {
  children: ReactNode;
  className?: string;
  /** 高亮药丸类（含圆角/底色，如 "inset-x-0 rounded-[6px] bg-hover"） */
  highlightClassName?: string;
  /** 行选择器（默认官方约定的 data-menu-row；sidebar 用 [data-row]） */
  rowSelector?: string;
}

/** 悬停滑动高亮容器。 */
export default function GlideMenu({
  children,
  className = "",
  highlightClassName = "inset-x-1 rounded-[6px] bg-hover",
  rowSelector = "[data-menu-row]",
}: GlideMenuProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{ top: number; height: number; on: boolean }>({
    top: 0,
    height: 0,
    on: false,
  });

  useLayoutEffect(() => {
    const container = ref.current;
    if (!container) return;

    const update = () => {
      const rows = Array.from(container.querySelectorAll<HTMLElement>(rowSelector));
      const hovered = rows.find((r) => r.matches(":hover"));
      const selected = rows.find(
        (r) => r.getAttribute("aria-pressed") === "true" || r.getAttribute("aria-checked") === "true",
      );
      const target = hovered ?? selected;
      if (target) {
        setBox({ top: target.offsetTop, height: target.offsetHeight, on: true });
      } else {
        setBox((current) => ({ ...current, on: false }));
      }
    };

    update();
    container.addEventListener("mouseover", update);
    container.addEventListener("mouseleave", update);
    const observer = new MutationObserver(update);
    observer.observe(container, { attributes: true, subtree: true, attributeFilter: ["aria-pressed", "aria-checked"] });
    return () => {
      container.removeEventListener("mouseover", update);
      container.removeEventListener("mouseleave", update);
      observer.disconnect();
    };
  }, [rowSelector]);

  return (
    <div ref={ref} className={`relative ${className}`}>
      <span
        aria-hidden
        className={`pointer-events-none absolute z-0 transition-[top,height,opacity] duration-200 ${highlightClassName}`}
        style={{
          top: box.top,
          height: box.height,
          opacity: box.on ? 1 : 0,
          transitionTimingFunction: "cubic-bezier(0.23,1,0.32,1)",
        }}
      />
      {children}
    </div>
  );
}
