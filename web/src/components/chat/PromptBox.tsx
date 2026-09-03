"use client";

/**
 * PromptBox（用户提供的 ChatGPT 风格输入框，适配项目令牌体系）：
 * 圆角容器 + 图片附件（预览/大图 Dialog）+ Tools Popover（真实五工具）+ 语音位 + 发送。
 * 颜色全部走 BUI 双令牌（.dark 自动切换），无硬编码。
 */

import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Terminal, FileText, PenLine, FolderSearch, Search, ImagePlus, Mic, ArrowUp, X, Settings2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { ContentBlock } from "@/lib/types";

type ClassValue = string | number | boolean | null | undefined;
function cn(...inputs: ClassValue[]): string {
  return inputs.filter(Boolean).join(" ");
}

const TooltipProvider = TooltipPrimitive.Provider;
const Tooltip = TooltipPrimitive.Root;
const TooltipTrigger = TooltipPrimitive.Trigger;
const TooltipContent = ({ children, ...props }: React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      sideOffset={4}
      className="z-50 max-w-[280px] rounded-md bg-ink px-1.5 py-1 text-xs text-surface"
      style={{ animation: "fade-in 150ms ease both" }}
      {...props}
    >
      {children}
    </TooltipPrimitive.Content>
  </TooltipPrimitive.Portal>
);

const PopoverContent = ({ children, ...props }: React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>) => (
  <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content
      side="top"
      align="start"
      sideOffset={6}
      className="z-50 w-64 rounded-[12px] border border-line bg-surface p-1.5 text-ink shadow-raised"
      style={{ animation: "pop-in 160ms cubic-bezier(0.23,1,0.32,1) both", transformOrigin: "bottom left" }}
      {...props}
    >
      {children}
    </PopoverPrimitive.Content>
  </PopoverPrimitive.Portal>
);

// --- 工具清单（对齐 tools/builtin.py 的 M1 五工具） ---

type ToolEntry = { id: string; name: string; shortName: string; icon: LucideIcon };

const toolsList: ToolEntry[] = [
  { id: "bash", name: "Run a shell command", shortName: "Shell", icon: Terminal },
  { id: "read_file", name: "Read a file", shortName: "Read", icon: FileText },
  { id: "write_file", name: "Write a file", shortName: "Write", icon: PenLine },
  { id: "glob", name: "Find files by pattern", shortName: "Glob", icon: FolderSearch },
  { id: "grep", name: "Search file contents", shortName: "Grep", icon: Search },
];

export type PromptBoxSubmit = (blocks: ContentBlock[], toolId: string | null) => void;

type PromptBoxProps = {
  disabled?: boolean;
  running?: boolean;
  onSend: (blocks: ContentBlock[], toolId: string | null) => void;
  className?: string;
};

export function PromptBox({ disabled, running, onSend, className }: PromptBoxProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const [value, setValue] = React.useState("");
  const [imageBlock, setImageBlock] = React.useState<ContentBlock | null>(null);
  const [imageDialog, setImageDialog] = React.useState(false);
  const [selectedTool, setSelectedTool] = React.useState<string | null>(null);
  const [popoverOpen, setPopoverOpen] = React.useState(false);

  React.useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [value]);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => setValue(e.target.value);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file && file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onloadend = () => {
        const dataUrl = reader.result as string;
        const base64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
        setImageBlock({ type: "image", media_type: file.type, data: base64 });
      };
      reader.readAsDataURL(file);
    }
    event.target.value = "";
  };

  const submit = () => {
    if (disabled || running) return;
    if (!value.trim() && !imageBlock) return;
    const blocks: ContentBlock[] = [];
    if (imageBlock) blocks.push(imageBlock);
    if (value.trim()) blocks.push({ type: "text", text: value.trim() });
    onSend(blocks, selectedTool);
    setValue("");
    setImageBlock(null);
    setSelectedTool(null);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const hasValue = value.trim().length > 0 || !!imageBlock;
  const activeTool = selectedTool ? toolsList.find((t) => t.id === selectedTool) : null;
  const ActiveToolIcon = activeTool?.icon;

  const iconBtn =
    "flex h-8 w-8 items-center justify-center rounded-full text-ink transition-colors hover:bg-hover focus-visible:outline-none disabled:opacity-40";

  return (
    <div
      className={cn(
        "flex flex-col rounded-[28px] border border-line bg-surface p-2 shadow-card transition-colors cursor-text",
        className,
      )}
    >
      <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" accept="image/*" />

      {imageBlock && imageBlock.type === "image" && (
        <DialogPrimitive.Root open={imageDialog} onOpenChange={setImageDialog}>
          <div className="relative mb-1 w-fit rounded-[1rem] px-1 pt-1">
            <button type="button" className="transition-transform" onClick={() => setImageDialog(true)}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`data:${imageBlock.media_type};base64,${imageBlock.data}`} alt="preview" className="h-14 w-14 rounded-[1rem] object-cover" />
            </button>
            <button
              onClick={() => setImageBlock(null)}
              className="absolute right-2 top-2 z-10 flex h-4 w-4 items-center justify-center rounded-full bg-surface/70 text-ink transition-colors hover:bg-hover"
              aria-label="Remove image"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <DialogPrimitive.Portal>
            <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60" style={{ animation: "fade-in 150ms ease both" }} />
            <DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2 rounded-[24px] p-1" style={{ animation: "pop-in 200ms ease both" }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`data:${imageBlock.media_type};base64,${imageBlock.data}`} alt="full" className="max-h-[90vh] max-w-[90vw] rounded-[20px] object-contain" />
              <DialogPrimitive.Close
                className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-full bg-ink text-surface"
                aria-label="Close"
              >
                <X className="h-5 w-5" />
              </DialogPrimitive.Close>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        </DialogPrimitive.Root>
      )}

      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="Message Codeharness…"
        className="min-h-12 w-full resize-none border-0 bg-transparent p-3 text-[14px] text-ink placeholder:text-ink-3 focus:outline-none"
      />

      <div className="mt-0.5 p-1 pt-0">
        <TooltipProvider delayDuration={100}>
          <div className="flex items-center gap-1.5">
            <Tooltip>
              <TooltipTrigger asChild>
                <button type="button" onClick={() => fileInputRef.current?.click()} className={iconBtn} aria-label="Attach image">
                  <ImagePlus className="h-5 w-5" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="top">Attach image</TooltipContent>
            </Tooltip>

            <PopoverPrimitive.Root open={popoverOpen} onOpenChange={setPopoverOpen}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <PopoverPrimitive.Trigger asChild>
                    <button
                      type="button"
                      className={cn(
                        "flex h-8 items-center gap-2 rounded-full px-2 text-[13px] text-ink transition-colors hover:bg-hover",
                        popoverOpen && "bg-hover",
                      )}
                      aria-label="Tools"
                    >
                      <Settings2 className="h-4 w-4" />
                      {!selectedTool && "Tools"}
                    </button>
                  </PopoverPrimitive.Trigger>
                </TooltipTrigger>
                <TooltipContent side="top">Tools</TooltipContent>
              </Tooltip>
              <PopoverContent>
                <div className="flex flex-col gap-0.5">
                  {toolsList.map((tool) => (
                    <button
                      key={tool.id}
                      onClick={() => {
                        setSelectedTool(tool.id);
                        setPopoverOpen(false);
                      }}
                      className="flex w-full items-center gap-2 rounded-[8px] p-2 text-left text-[13px] text-ink transition-colors hover:bg-hover"
                    >
                      <tool.icon className="h-4 w-4 text-ink-2" />
                      <span>{tool.name}</span>
                    </button>
                  ))}
                </div>
              </PopoverContent>
            </PopoverPrimitive.Root>

            {activeTool && ActiveToolIcon && (
              <>
                <div className="h-4 w-px bg-line-strong" />
                <button
                  onClick={() => setSelectedTool(null)}
                  className="flex h-8 items-center gap-1.5 rounded-full px-2 text-[13px] text-accent-ink transition-colors hover:bg-hover"
                >
                  <ActiveToolIcon className="h-4 w-4" />
                  {activeTool.shortName}
                  <X className="h-4 w-4" />
                </button>
              </>
            )}

            <div className="ml-auto flex items-center gap-1.5">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button type="button" className={iconBtn} aria-label="Voice (coming soon)">
                    <Mic className="h-5 w-5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top">Voice（即将上线）</TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={submit}
                    disabled={!hasValue || disabled || running}
                    className={cn(
                      "flex h-8 w-8 items-center justify-center rounded-full transition-colors disabled:opacity-40",
                      "bg-ink text-surface hover:opacity-90",
                    )}
                    aria-label="Send message"
                  >
                    <ArrowUp className="h-5 w-5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top">Send</TooltipContent>
              </Tooltip>
            </div>
          </div>
        </TooltipProvider>
      </div>
    </div>
  );
}
