"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Memory } from "@/lib/types";

export default function MemoriesPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(false);
  const [newMemory, setNewMemory] = useState({ name: "", content: "" });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    api.searchMemories(query).then((rows) => {
      setResults(rows);
      setLoading(false);
    });
  };

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMemory.name || !newMemory.content) return;
    api.addMemory(newMemory.name, newMemory.content).then(() => {
      setNewMemory({ name: "", content: "" });
      handleSearch(e); // Refresh results
    });
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Memories</h1>
        <p className="text-sm text-ink-2">Semantic knowledge base for the agent.</p>
      </div>

      <form onSubmit={handleAdd} className="rounded-card border border-line bg-surface p-4 shadow-sm">
        <h2 className="mb-3 text-sm font-medium text-ink">Add New Memory</h2>
        <div className="space-y-3">
          <input
            placeholder="Name / Key"
            value={newMemory.name}
            onChange={(e) => setNewMemory({ ...newMemory, name: e.target.value })}
            className="w-full rounded-[6px] border border-line bg-field px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          />
          <textarea
            placeholder="Content..."
            rows={3}
            value={newMemory.content}
            onChange={(e) => setNewMemory({ ...newMemory, content: e.target.value })}
            className="w-full rounded-[6px] border border-line bg-field px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          />
          <div className="flex justify-end">
            <button
              type="submit"
              className="rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
              disabled={!newMemory.name || !newMemory.content}
            >
              Save Memory
            </button>
          </div>
        </div>
      </form>

      <form onSubmit={handleSearch} className="flex items-center gap-2">
        <input
          placeholder="Search memories..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1 rounded-[6px] border border-line bg-field px-3 py-2 text-sm text-ink outline-none focus:border-accent"
        />
        <button
          type="submit"
          className="rounded-full border border-line px-4 py-2 text-sm font-medium text-ink hover:bg-hover"
        >
          Search
        </button>
      </form>

      <div className="space-y-3">
        {loading && <div className="text-center text-sm text-ink-2">Searching...</div>}
        {!loading && results.length === 0 && query && (
          <div className="rounded-card border border-line bg-surface p-8 text-center text-ink-2">
            No memories found for "{query}".
          </div>
        )}
        {results.map((m) => (
          <div key={m.id} className="rounded-card border border-line bg-surface p-4 shadow-sm">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-medium text-ink">{m.name}</span>
              <span className="text-xs text-ink-3">{new Date(m.updated_at).toLocaleDateString()}</span>
            </div>
            <p className="whitespace-pre-wrap text-sm text-ink-2">{m.content}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
