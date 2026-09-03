"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type CredentialRow = { id: string; provider: string; label: string };

export default function CredentialsPage() {
  const [creds, setCreds] = useState<CredentialRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState({ provider: "", label: "", api_key: "" });
  const [saving, setSaving] = useState(false);

  const refresh = () =>
    api
      .listCredentials()
      .then(setCreds)
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, []);

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft.provider.trim() || !draft.api_key.trim() || saving) return;
    setSaving(true);
    api
      .addCredential({
        provider: draft.provider.trim(),
        api_key: draft.api_key,
        label: draft.label.trim() || undefined,
      })
      .then(() => {
        setDraft({ provider: "", label: "", api_key: "" });
        setError(null);
        return refresh();
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setSaving(false));
  };

  const handleDelete = (id: string) => {
    api
      .deleteCredential(id)
      .then(() => setCreds((prev) => prev.filter((c) => c.id !== id)))
      .catch((err: Error) => setError(err.message));
  };

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">API Keys &amp; Credentials</h1>
        <p className="text-sm text-ink-2">Provider tokens are encrypted at rest and never echoed back.</p>
      </div>

      <form onSubmit={handleAdd} className="rounded-card border border-line bg-surface p-4 shadow-sm">
        <h2 className="mb-3 text-[13px] font-medium text-ink">Add credential</h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
          <input
            placeholder="Provider (e.g. anthropic)"
            value={draft.provider}
            onChange={(e) => setDraft({ ...draft, provider: e.target.value })}
            className="rounded-[6px] border border-line bg-field px-3 py-2 text-[13px] text-ink outline-none focus:border-accent"
          />
          <input
            placeholder="Label (optional)"
            value={draft.label}
            onChange={(e) => setDraft({ ...draft, label: e.target.value })}
            className="rounded-[6px] border border-line bg-field px-3 py-2 text-[13px] text-ink outline-none focus:border-accent"
          />
          <input
            type="password"
            placeholder="API key"
            value={draft.api_key}
            onChange={(e) => setDraft({ ...draft, api_key: e.target.value })}
            className="rounded-[6px] border border-line bg-field px-3 py-2 text-[13px] text-ink outline-none focus:border-accent"
          />
          <button
            type="submit"
            disabled={!draft.provider.trim() || !draft.api_key.trim() || saving}
            className="rounded-full bg-accent px-4 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            Add
          </button>
        </div>
      </form>

      {error && <div className="text-[12.5px] text-red">{error}</div>}

      <div className="rounded-card border border-line bg-surface shadow-sm">
        <table className="w-full text-left text-[13px]">
          <thead className="border-b border-line bg-inset text-[11px] uppercase tracking-wide text-ink-3">
            <tr>
              <th className="px-4 py-3 font-medium">Provider</th>
              <th className="px-4 py-3 font-medium">Label</th>
              <th className="px-4 py-3 font-medium">ID</th>
              <th className="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {creds.map((c) => (
              <tr key={c.id} className="border-b border-line last:border-0 hover:bg-hover/50">
                <td className="px-4 py-3 font-medium text-ink">{c.provider}</td>
                <td className="px-4 py-3 text-ink-2">{c.label || "—"}</td>
                <td className="px-4 py-3 font-mono text-[11px] text-ink-3">{c.id.slice(0, 8)}…</td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => handleDelete(c.id)} className="text-[12px] font-medium text-red hover:underline">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {creds.length === 0 && !loading && !error && (
              <tr>
                <td colSpan={4} className="py-8 text-center text-ink-2">
                  No credentials configured.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
