"use client";

import { useState } from "react";
import { api } from "@/lib/api";

type MemoryHit = { id: number; content: string; kind: string; score: number };

export default function MemoriesPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MemoryHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [draft, setDraft] = useState({ content: "", kind: "fact" });
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const runSearch = (q: string) => {
    if (!q.trim()) return;
    setLoading(true);
    api
      .searchMemories(q)
      .then((rows) => {
        setResults(rows);
        setSearched(true);
      })
      .catch((e: Error) => setNotice(e.message))
      .finally(() => setLoading(false));
  };

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft.content.trim() || saving) return;
    setSaving(true);
    api
      .addMemory({ content: draft.content.trim(), kind: draft.kind || "fact" })
      .then(() => {
        setDraft({ content: "", kind: draft.kind });
        setNotice("Memory saved.");
        runSearch(draft.content.trim().split(/\s+/)[0]);
      })
      .catch((err: Error) => setNotice(err.message))
      .finally(() => setSaving(false));
  };

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Memories</h1>
        <p className="text-sm text-ink-2">Semantic knowledge base for the agent.</p>
      </div>

      <form onSubmit={handleAdd} className="rounded-card border border-line bg-surface p-4 shadow-sm">
        <h2 className="mb-3 text-[13px] font-medium text-ink">Add memory</h2>
        <div className="flex flex-col gap-3">
          <textarea
            placeholder="Content to remember…"
            rows={3}
            value={draft.content}
            onChange={(e) => setDraft({ ...draft, content: e.target.value })}
            className="w-full rounded-[6px] border border-line bg-field px-3 py-2 text-[13px] text-ink outline-none focus:border-accent"
          />
          <div className="flex items-center justify-between gap-3">
            <select
              value={draft.kind}
              onChange={(e) => setDraft({ ...draft, kind: e.target.value })}
              className="rounded-[6px] border border-line bg-field px-2 py-2 text-[13px] text-ink outline-none focus:border-accent"
            >
              {["fact", "preference", "procedure", "event"].map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
            <button
              type="submit"
              disabled={!draft.content.trim() || saving}
              className="rounded-full bg-accent px-4 py-1.5 text-[13px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              Save memory
            </button>
          </div>
        </div>
      </form>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          runSearch(query);
        }}
        className="flex items-center gap-2"
      >
        <input
          placeholder="Search memories…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1 rounded-[6px] border border-line bg-field px-3 py-2 text-[13px] text-ink outline-none focus:border-accent"
        />
        <button
          type="submit"
          className="rounded-full border border-line px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:bg-hover"
        >
          Search
        </button>
      </form>

      {notice && <div className="text-[12.5px] text-ink-3">{notice}</div>}

      <div className="flex flex-col gap-3">
        {loading && <div className="text-center text-[13px] text-ink-2">Searching…</div>}
        {!loading && searched && results.length === 0 && (
          <div className="rounded-card border border-line bg-surface p-8 text-center text-ink-2">
            No memories matched “{query}”.
          </div>
        )}
        {results.map((m) => (
          <div key={m.id} className="rounded-card border border-line bg-surface p-4 shadow-sm">
            <div className="mb-1.5 flex items-center gap-2">
              <span className="rounded-full bg-accent-tint px-2 py-0.5 text-[10px] font-medium text-accent-ink">
                {m.kind}
              </span>
              <span className="text-[11px] tabular-nums text-ink-3">score {m.score.toFixed(3)}</span>
            </div>
            <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink-2">{m.content}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
