/**
 * Button 原子（J24 本地化定案：官方站内部原子无源码，按消费场景反推实现）。
 * 药丸形态（rounded-full）+ 五变体：ghost/primary/accent/secondary/success。
 * 消费方：approval-card / recommendation-card / diff-table。
 */
import type { ButtonHTMLAttributes, ReactNode } from "react";

/** 按钮变体（与官方站消费口径对齐）。 */
export type ButtonVariant = "ghost" | "primary" | "accent" | "secondary" | "success";

const VARIANTS: Record<ButtonVariant, string> = {
  ghost: "text-ink-2 hover:bg-hover",
  primary: "bg-field text-ink shadow-btn hover:bg-hover-2",
  accent: "bg-ink text-surface shadow-btn hover:opacity-90",
  secondary: "border border-line text-ink hover:bg-hover",
  success: "bg-green text-white",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  children: ReactNode;
}

/** 药丸按钮原子。 */
export function Button({
  variant = "primary",
  size = "sm",
  className = "",
  children,
  ...rest
}: ButtonProps) {
  const sizeCls = size === "sm" ? "h-7 px-2.5 text-[12.5px]" : "h-8 px-3 text-[13px]";
  return (
    <button
      type="button"
      className={`inline-flex shrink-0 items-center justify-center gap-1 rounded-full
        font-medium transition-[background-color,color,opacity,transform] duration-150
        active:scale-[0.97] disabled:opacity-40 disabled:active:scale-100
        ${VARIANTS[variant]} ${sizeCls} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
