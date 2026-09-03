/** REST 客户端（契约⑥）。base URL 由 NEXT_PUBLIC_API_BASE 覆盖。 */

import type { ApprovalTicket, ContentBlock, ModelProviderInfo, PlatformMessage, Run, Session, Workspace } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body?.error?.message ?? `${resp.status} ${resp.statusText}`);
  }
  return resp.json();
}

export const api = {
  createSession: (model: string, title = "", workspaceId?: string | null) =>
    request<{ id: string; model: string; title: string }>("/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify({ model, title, workspace_id: workspaceId ?? null }),
    }),

  updateSession: (sessionId: string, body: { model?: string; title?: string; workspace_id?: string }) =>
    request<Session>(`/api/v1/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  listModels: () => request<ModelProviderInfo[]>("/api/v1/models"),

  listWorkspaces: () => request<Workspace[]>("/api/v1/workspaces"),

  addWorkspace: (name: string, path: string) =>
    request<Workspace>("/api/v1/workspaces", {
      method: "POST",
      body: JSON.stringify({ name, path }),
    }),

  deleteWorkspace: (workspaceId: string) =>
    request<{ deleted: boolean }>(`/api/v1/workspaces/${workspaceId}`, { method: "DELETE" }),

  listSessions: () => request<Session[]>("/api/v1/sessions"),

  getSession: (sessionId: string) => request<Session>(`/api/v1/sessions/${sessionId}`),

  listMessages: (sessionId: string) =>
    request<{ messages: PlatformMessage[] }>(`/api/v1/sessions/${sessionId}/messages`),

  sendMessage: (sessionId: string, content: ContentBlock[]) =>
    request<{ run_id: string }>(`/api/v1/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  getRun: (runId: string) => request<Run>(`/api/v1/runs/${runId}`),

  listApprovals: () => request<ApprovalTicket[]>("/api/v1/approvals"),

  decide: (runId: string, ticketId: string, choices: { call_id: string; approve: boolean; reason?: string }[]) =>
    request<{ status: string }>(`/api/v1/runs/${runId}/approvals/${ticketId}/decide`, {
      method: "POST",
      body: JSON.stringify({ choices }),
    }),

  // ---- P3/P4 扩展 ----

  listSkills: () => request<{ name: string; description: string }[]>("/api/v1/skills"),

  listCredentials: () =>
    request<{ id: string; provider: string; label: string }[]>("/api/v1/credentials"),

  addCredential: (body: { provider: string; api_key: string; label?: string; base_url?: string }) =>
    request<{ id: string; provider: string }>("/api/v1/credentials", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteCredential: (credentialId: string) =>
    request<{ deleted: boolean }>(`/api/v1/credentials/${credentialId}`, { method: "DELETE" }),

  addMemory: (body: { content: string; kind?: string; session_id?: string }) =>
    request<{ id: number; content: string; kind: string }>("/api/v1/memories", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  searchMemories: (q: string, k = 5) =>
    request<{ id: number; content: string; kind: string; score: number }[]>(
      `/api/v1/memories/search?q=${encodeURIComponent(q)}&k=${k}`,
    ),

  eventsUrl: (sessionId: string, after?: string) =>
    `${BASE}/api/v1/sessions/${sessionId}/events${after ? `?after=${encodeURIComponent(after)}` : ""}`,
};
