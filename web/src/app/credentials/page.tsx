"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Credential } from "@/lib/types";

export default function CredentialsPage() {
  const [creds, setCreds] = useState<Credential[]>([]);
  const [loading, setLoading] = useState(true);
  const [newCred, setNewCred] = useState({ provider: "", name: "", api_key: "" });

  useEffect(() => {
    api.listCredentials().then((rows) => {
      setCreds(rows);
      setLoading(false);
    });
  }, []);

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCred.provider || !newCred.name || !newCred.api_key) return;
    api.addCredential(newCred.provider, newCred.name, newCred.api_key).then(() => {
      setNewCred({ provider: "", name: "", api_key: "" });
      api.listCredentials().then(setCreds);
    });
  };

  const handleDelete = (id: string) => {
    if (confirm("Are you sure you want to delete this credential?")) {
      api.deleteCredential(id).then(() => setCreds((prev) => prev.filter((c) => c.id !== id)));
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">API Keys & Credentials</h1>
        <p className="text-sm text-ink-2">Manage provider authentication tokens.</p>
      </div>

      <form onSubmit={handleAdd} className="rounded-card border border-line bg-surface p-4 shadow-sm">
        <h2 className="mb-3 text-sm font-medium text-ink">Add Credential</h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
          <input
            placeholder="Provider (e.g. openai)"
            value={newCred.provider}
            onChange={(e) => setNewCred({ ...newCred, provider: e.target.value })}
            className="rounded-[6px] border border-line bg-field px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          />
          <input
            placeholder="Name / Alias"
            value={newCred.name}
            onChange={(e) => setNewCred({ ...newCred, name: e.target.value })}
            className="rounded-[6px] border border-line bg-field px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          />
          <input
            type="password"
            placeholder="API Key"
            value={newCred.api_key}
            onChange={(e) => setNewCred({ ...newCred, api_key: e.target.value })}
            className="rounded-[6px] border border-line bg-field px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          />
          <button
            type="submit"
            className="rounded-full bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
            disabled={!newCred.provider || !newCred.name || !newCred.api_key}
          >
            Add
          </button>
        </div>
      </form>

      <div className="rounded-card border border-line bg-surface shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line bg-inset text-xs uppercase text-ink-3">
            <tr>
              <th className="px-4 py-3 font-medium">Provider</th>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">ID</th>
              <th className="px-4 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {creds.map((c) => (
              <tr key={c.id} className="border-b border-line last:border-0 hover:bg-hover/50">
                <td className="px-4 py-3 font-medium text-ink">{c.provider}</td>
                <td className="px-4 py-3 text-ink-2">{c.name}</td>
                <td className="px-4 py-3 font-mono text-xs text-ink-3">{c.id.slice(0, 8)}...</td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => handleDelete(c.id)}
                    className="text-xs font-medium text-red hover:underline"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {creds.length === 0 && !loading && (
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
