"use client";

/**
 * 工作区切换器（本机文件夹目录）：列出 / 选中 / 添加。
 * 数据走 GET·POST /api/v1/workspaces；选中由宿主持久化并过滤会话列表。
 */

import { useState } from "react";
import { Check, ChevronDown, FolderOpen, Plus } from "lucide-react";

import { api } from "@/lib/api";
import type { Workspace } from "@/lib/types";

export function WorkspaceSwitcher({
  workspaces,
  activeId,
  onSelect,
  onCreated,
}: {
  workspaces: Workspace[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  onCreated: (ws: Workspace) => void;
}) {
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ name: "", path: "" });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const current = workspaces.find((w) => w.id === activeId) ?? null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft.name.trim() || !draft.path.trim() || saving) return;
    setSaving(true);
    setError(null);
    try {
      const ws = await api.addWorkspace(draft.name.trim(), draft.path.trim());
      onCreated(ws);
      setDraft({ name: "", path: "" });
      setAdding(false);
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "添加失败");
    } finally {
      setSaving(false);
    }
  };

  const row =
    "relative z-10 mx-1 flex cursor-pointer items-center gap-2 rounded-[6px] px-2.5 py-2 text-left text-[13px] transition-colors";

  return (
    <div className="relative mb-1">
      <div
        onClick={() => setOpen(!open)}
        className="group mb-1 flex cursor-pointer select-none items-center justify-between rounded-[8px] px-2 py-2 transition-colors hover:bg-hover"
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-[6px] bg-accent text-[13px] font-semibold text-white shadow-card">
            {current ? current.name.charAt(0).toUpperCase() : "C"}
          </div>
          <div className="flex min-w-0 flex-col overflow-hidden">
            <span className="mb-0.5 truncate text-[13px] font-medium leading-none text-ink">
              {current ? current.name : "Codeharness"}
            </span>
            <span className="truncate text-[11px] leading-none text-ink-3">
              {current ? current.path : "所有会话"}
            </span>
          </div>
        </div>
        <ChevronDown className="size-4 shrink-0 text-ink-3 transition-colors group-hover:text-ink-2" />
      </div>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="absolute left-0 top-[54px] z-50 flex w-[260px] flex-col gap-0.5 rounded-[10px] border border-line bg-surface py-1 shadow-raised"
            style={{ animation: "pop-in 180ms cubic-bezier(0.23,1,0.32,1) both" }}
          >
            <div
              onClick={() => {
                onSelect(null);
                setOpen(false);
              }}
              className={`${row} ${activeId === null ? "bg-accent-tint font-medium text-accent-ink" : "text-ink-2 hover:bg-hover"}`}
            >
              <span className="min-w-0 flex-1 truncate">所有会话</span>
              {activeId === null && <Check className="size-3.5 shrink-0" />}
            </div>
            {workspaces.map((ws) => (
              <div
                key={ws.id}
                onClick={() => {
                  onSelect(ws.id);
                  setOpen(false);
                }}
                className={`${row} ${activeId === ws.id ? "bg-accent-tint font-medium text-accent-ink" : "text-ink-2 hover:bg-hover"}`}
                title={ws.path}
              >
                <FolderOpen className="size-3.5 shrink-0" />
                <span className="min-w-0 flex-1 truncate">{ws.name}</span>
                {activeId === ws.id && <Check className="size-3.5 shrink-0" />}
              </div>
            ))}
            <div className="mx-2 my-1 h-px bg-line" />
            {!adding ? (
              <div
                onClick={() => setAdding(true)}
                className={`${row} text-ink-2 hover:bg-hover`}
              >
                <Plus className="size-3.5 shrink-0" />
                <span>添加工作区</span>
              </div>
            ) : (
              <form onSubmit={submit} className="mx-1 flex flex-col gap-1.5 rounded-[6px] bg-inset p-2">
                <input
                  autoFocus
                  placeholder="名称"
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  className="w-full rounded-[5px] border border-line bg-surface px-2 py-1.5 text-[12px] text-ink outline-none focus:border-accent"
                />
                <input
                  placeholder="本机文件夹路径（如 G:\\projects\\demo）"
                  value={draft.path}
                  onChange={(e) => setDraft({ ...draft, path: e.target.value })}
                  className="w-full rounded-[5px] border border-line bg-surface px-2 py-1.5 text-[12px] text-ink outline-none focus:border-accent"
                />
                {error && <div className="text-[11px] text-red">{error}</div>}
                <div className="flex justify-end gap-1.5">
                  <button
                    type="button"
                    onClick={() => {
                      setAdding(false);
                      setError(null);
                    }}
                    className="rounded-full px-2.5 py-1 text-[11.5px] text-ink-2 hover:bg-hover"
                  >
                    取消
                  </button>
                  <button
                    type="submit"
                    disabled={!draft.name.trim() || !draft.path.trim() || saving}
                    className="rounded-full bg-accent px-2.5 py-1 text-[11.5px] font-medium text-white disabled:opacity-40"
                  >
                    添加
                  </button>
                </div>
              </form>
            )}
          </div>
        </>
      )}
    </div>
  );
}
