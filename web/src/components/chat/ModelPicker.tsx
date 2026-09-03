"use client";

/**
 * ModelPicker：模型厂商上拉选择器（参考件输入框底栏的模型下拉）。
 * 数据来自 GET /api/v1/models（供应商注册表 + 常用目录 + configured 标记）；
 * 选择后回调 onPick(model)，由调用方 PATCH /api/v1/sessions/{id} 落库。
 */

import * as React from "react";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { Box, Check, ChevronDown } from "lucide-react";

import { api } from "@/lib/api";
import type { ModelProviderInfo } from "@/lib/types";

function cn(...inputs: (string | false | null | undefined)[]): string {
  return inputs.filter(Boolean).join(" ");
}

export function ModelPicker({
  model,
  onPick,
  className,
}: {
  model?: string | null;
  onPick: (model: string) => void;
  className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [providers, setProviders] = React.useState<ModelProviderInfo[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    setError(null);
    api
      .listModels()
      .then(setProviders)
      .catch((e: Error) => setError(e.message));
  }, [open]);

  const trigger = (
    <PopoverPrimitive.Trigger asChild>
      <button
        type="button"
        aria-label="Select model"
        className={cn(
          "flex h-8 items-center gap-1.5 rounded-full px-2.5 text-[12.5px] text-ink transition-colors hover:bg-hover",
          className,
        )}
      >
        <Box className="size-4 text-ink-2" />
        <span className="max-w-[160px] truncate">{model || "选择模型"}</span>
        <ChevronDown className="size-3.5 text-ink-3" />
      </button>
    </PopoverPrimitive.Trigger>
  );

  return (
    <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
      {trigger}
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          side="top"
          align="start"
          sideOffset={6}
          className="z-50 w-64 rounded-[12px] border border-line bg-surface p-1.5 shadow-raised"
          style={{ animation: "pop-in 160ms cubic-bezier(0.23,1,0.32,1) both", transformOrigin: "bottom left" }}
        >
          <div className="flex max-h-[320px] flex-col overflow-y-auto">
            {error && <div className="px-2 py-3 text-[12px] text-red">{error}</div>}
            {!error && providers.length === 0 && (
              <div className="px-2 py-3 text-[12px] text-ink-3">Loading providers…</div>
            )}
            {providers.map((p) => (
              <div key={p.provider} className="flex flex-col gap-0.5">
                <div className="flex items-center justify-between px-2 pb-0.5 pt-1.5">
                  <span className="text-[10.5px] font-semibold uppercase tracking-wider text-ink-3">
                    {p.label}
                  </span>
                  {!p.configured && (
                    <span className="text-[10px] text-ink-3">未配置密钥</span>
                  )}
                </div>
                {p.models.map((m) => (
                  <button
                    key={m}
                    type="button"
                    disabled={!p.configured}
                    onClick={() => {
                      onPick(m);
                      setOpen(false);
                    }}
                    title={p.configured ? m : `${p.label} 未配置 API 密钥`}
                    className={cn(
                      "relative z-10 flex h-8 w-full items-center gap-2 rounded-[8px] px-2 text-left text-[13px]",
                      p.configured ? "text-ink hover:bg-hover" : "cursor-not-allowed text-ink-3 opacity-45",
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate">{m}</span>
                    {model === m && <Check className="size-3.5 shrink-0 text-accent-ink" />}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
