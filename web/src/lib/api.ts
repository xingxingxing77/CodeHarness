/** REST 客户端（契约⑥）。base URL 由 NEXT_PUBLIC_API_BASE 覆盖。 */

import type { ApprovalTicket, ContentBlock, PlatformMessage, Run, Session } from "./types";

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
  createSession: (model: string, title = "") =>
    request<{ id: string; model: string; title: string }>("/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify({ model, title }),
    }),

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

  eventsUrl: (sessionId: string, after?: string) =>
    `${BASE}/api/v1/sessions/${sessionId}/events${after ? `?after=${encodeURIComponent(after)}` : ""}`,
};
