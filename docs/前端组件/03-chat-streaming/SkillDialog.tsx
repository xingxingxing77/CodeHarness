/**
 * SkillDialog — Add Skill 对话框（仿 OpenHarness loader.py 布局）。
 * 表单：name / description / SKILL.md 全文 + 文件拖拽上传。
 * 成功后落盘 <skills_root>/<name>/SKILL.md 并注册。
 */
import { useRef, useState } from "react";

import { createPromptSkill, uploadPromptSkillFile } from "@/api/promptBar";

export interface SkillDialogProps {
  open: boolean;
  onClose(): void;
  onCreated?(name: string): void;
}

export default function SkillDialog({ open, onClose, onCreated }: SkillDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  if (!open) return null;

  const submit = async () => {
    setError(null);
    if (!name.trim() || !content.trim()) {
      setError("请填写 name 与 SKILL.md 全文");
      return;
    }
    setBusy(true);
    try {
      const res = await createPromptSkill({ name: name.trim(), description: description.trim() || undefined, content });
      if (res.ok) {
        onCreated?.(res.name ?? name.trim());
        setName("");
        setDescription("");
        setContent("");
        onClose();
      } else {
        setError("创建失败");
      }
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? (e as Error)?.message ?? "创建失败";
      setError(String(msg));
    } finally {
      setBusy(false);
    }
  };

  const handleFile = async (file: File) => {
    if (!file.name.endsWith(".md")) {
      setError("请上传 .md 文件");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const text = await file.text();
      setContent(text);
      // 若 name 为空则用文件名回填
      if (!name.trim()) {
        const base = file.name.replace(/\.md$/i, "").toLowerCase().replace(/\s+/g, "-");
        setName(base);
      }
      // 直接走上传接口（后端会解析 frontmatter）
      // 保留文本域内容供用户二次编辑，不自动提交
    } catch (err) {
      setError(String((err as Error)?.message ?? "读取失败"));
    } finally {
      setBusy(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) void handleFile(f);
  };

  const handleUploadViaApi = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const res = await uploadPromptSkillFile(file);
      if (res.ok) {
        onCreated?.(res.name ?? file.name);
        onClose();
      } else {
        setError("上传失败");
      }
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? (e as Error)?.message ?? "上传失败";
      setError(String(msg));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* overlay */}
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]" onClick={onClose} aria-hidden />
      {/* dialog */}
      <div className="relative w-full max-w-lg rounded-[14px] border border-line bg-surface p-5 shadow-raised">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-ink">Add Skill</h3>
          <button
            type="button"
            onClick={onClose}
            className="flex size-7 items-center justify-center rounded-[8px] text-ink-3 hover:bg-hover hover:text-ink"
            aria-label="Close"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" aria-hidden>
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <p className="mb-3 text-xs text-ink-3">
          仿 OpenHarness <code className="rounded bg-field px-1 py-0.5">{"<root>/<skill>/SKILL.md"}</code> 布局，落盘至 <code className="rounded bg-field px-1 py-0.5">data/skills</code>。支持粘贴全文或拖拽 .md。
        </p>

        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-ink">Name *</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="my-skill"
              className="rounded-[8px] border border-line bg-field px-3 py-2 text-sm text-ink outline-none focus:border-line-strong"
            />
            <span className="text-[11px] text-ink-3">2–32 位小写字母/数字/中划线，以字母数字开头</span>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-ink">Description</span>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="一句话描述"
              className="rounded-[8px] border border-line bg-field px-3 py-2 text-sm text-ink outline-none focus:border-line-strong"
            />
          </label>

          {/* 拖拽区 */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={`rounded-[8px] border border-dashed px-3 py-4 text-center text-xs transition-colors ${dragOver ? "border-accent-ink bg-accent-tint" : "border-line bg-field text-ink-3"}`}
          >
            <div className="flex flex-col items-center gap-1">
              <span>拖拽 SKILL.md 到此处，或</span>
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="rounded-[6px] bg-ink px-2.5 py-1 text-xs font-medium text-surface hover:bg-ink-2"
              >
                选择文件
              </button>
              <input ref={fileRef} type="file" accept=".md" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleFile(f); e.target.value = ""; }} />
              <span className="text-[11px]">粘贴全文可在下方编辑</span>
            </div>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-ink">SKILL.md 全文 *</span>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={"---\nname: my-skill\ndescription: demo\n---\n\n# My Skill\n..."}
              rows={10}
              className="rounded-[8px] border border-line bg-field px-3 py-2 font-mono text-xs text-ink outline-none focus:border-line-strong"
            />
          </label>

          {error && <div className="rounded-[8px] bg-red-50 px-3 py-2 text-xs text-red-600">{error}</div>}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-[8px] border border-line bg-surface px-3.5 py-1.5 text-xs font-medium text-ink-2 hover:bg-hover"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => {
                // 若用户已拖拽文件且 content 来自文件，可直接走上传接口
                const maybeFile = fileRef.current?.files?.[0];
                if (maybeFile && content) {
                  // 优先走 JSON 创建，保留 frontmatter 解析
                  void submit();
                } else {
                  void submit();
                }
              }}
              disabled={busy}
              className="rounded-[8px] bg-ink px-3.5 py-1.5 text-xs font-medium text-surface hover:bg-ink-2 disabled:opacity-40"
            >
              {busy ? "提交中…" : "创建 Skill"}
            </button>
            {/* 快捷：直接上传文件 */}
            <button
              type="button"
              onClick={() => {
                const f = fileRef.current?.files?.[0];
                if (f) void handleUploadViaApi(f);
                else setError("请先选择 .md 文件");
              }}
              className="hidden"
              aria-hidden
            >
              upload
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
