"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ApprovalTicket } from "@/lib/types";

export default function ApprovalsPage() {
  const [tickets, setTickets] = useState<ApprovalTicket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    api
      .listApprovals()
      .then(setTickets)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleDecide = (ticket: ApprovalTicket, approve: boolean) => {
    setBusyId(ticket.ticket_id);
    api
      .decide(
        ticket.run_id,
        ticket.ticket_id,
        ticket.items.map((i) => ({
          call_id: i.call_id,
          approve,
          reason: approve ? "approved in inbox" : "denied in inbox",
        })),
      )
      .then(() => setTickets((prev) => prev.filter((t) => t.ticket_id !== ticket.ticket_id)))
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusyId(null));
  };

  if (loading) return <div className="p-6 text-[13px] text-ink-2">Loading approvals…</div>;

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Inbox · Approvals</h1>
        <p className="text-sm text-ink-2">Tool calls waiting for your decision.</p>
      </div>

      {error && <div className="text-[12.5px] text-red">{error}</div>}

      {tickets.length === 0 ? (
        <div className="rounded-card border border-line bg-surface p-8 text-center text-ink-2">
          No pending approvals.
        </div>
      ) : (
        tickets.map((t) => (
          <div key={t.ticket_id} className="rounded-card border border-line bg-surface p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-mono text-[12px] text-ink-3">run {t.run_id.slice(0, 8)}…</span>
              <span className="text-[11px] text-ink-3">
                expires {new Date(t.expires_at * 1000).toLocaleTimeString()}
              </span>
            </div>
            <div className="flex flex-col gap-2">
              {t.items.map((item) => (
                <div key={item.call_id} className="rounded-[6px] bg-inset p-3">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="text-[13px] font-medium text-ink">{item.tool_name}</span>
                    <span className="rounded-full bg-accent-tint px-1.5 py-0.5 text-[10px] font-semibold uppercase text-accent-ink">
                      {item.risk_level}
                    </span>
                  </div>
                  {item.reason && <p className="text-[12px] text-ink-2">{item.reason}</p>}
                  <pre className="mt-2 max-h-24 overflow-auto rounded bg-field p-2 font-mono text-[11px] text-ink-2">
                    {item.input_preview || "(no input)"}
                  </pre>
                </div>
              ))}
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button
                disabled={busyId === t.ticket_id}
                onClick={() => handleDecide(t, false)}
                className="rounded-full border border-line px-3 py-1 text-[12px] font-medium text-ink transition-colors hover:bg-hover disabled:opacity-40"
              >
                Deny all
              </button>
              <button
                disabled={busyId === t.ticket_id}
                onClick={() => handleDecide(t, true)}
                className="rounded-full bg-accent px-3 py-1 text-[12px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                Approve all
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
