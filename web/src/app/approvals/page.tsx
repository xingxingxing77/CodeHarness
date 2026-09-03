"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ApprovalTicket } from "@/lib/types";

export default function ApprovalsPage() {
  const [tickets, setTickets] = useState<ApprovalTicket[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listApprovals().then((rows) => {
      setTickets(rows);
      setLoading(false);
    });
  }, []);

  const handleDecide = (ticketId: string, runId: string, approve: boolean) => {
    api.decide(ticketId, runId, [{ call_id: "*", approve, reason: approve ? "approved" : "denied" }])
      .then(() => setTickets((prev) => prev.filter((t) => t.ticket_id !== ticketId)))
      .catch(console.error);
  };

  if (loading) return <div className="p-4 text-ink-2">Loading approvals...</div>;

  return (
    <div className="flex flex-col gap-4 p-6">
      <h1 className="text-xl font-semibold text-ink">Inbox · Approvals</h1>
      {tickets.length === 0 ? (
        <div className="rounded-card border border-line bg-surface p-8 text-center text-ink-2">
          No pending approvals.
        </div>
      ) : (
        tickets.map((t) => (
          <div key={t.ticket_id} className="rounded-card border border-line bg-surface p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-mono text-sm text-ink">{t.run_id}</span>
              <span className="text-xs text-ink-3">{new Date(t.created_at).toLocaleString()}</span>
            </div>
            <div className="space-y-2">
              {t.items.map((item) => (
                <div key={item.call_id} className="rounded-[6px] bg-inset p-3">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-medium text-ink">{item.tool_name}</span>
                    <span className="rounded-full bg-accent/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-accent">
                      {item.risk_level}
                    </span>
                  </div>
                  <p className="text-xs text-ink-2">{item.reason}</p>
                  <pre className="mt-2 max-h-24 overflow-auto rounded bg-field p-2 font-mono text-[11px] text-ink-3">
                    {item.input_preview}
                  </pre>
                  <div className="mt-3 flex justify-end gap-2">
                    <button
                      onClick={() => handleDecide(t.ticket_id, t.run_id, false)}
                      className="rounded-full border border-line px-3 py-1 text-xs font-medium text-ink hover:bg-hover"
                    >
                      Deny
                    </button>
                    <button
                      onClick={() => handleDecide(t.ticket_id, t.run_id, true)}
                      className="rounded-full bg-accent px-3 py-1 text-xs font-medium text-white hover:opacity-90"
                    >
                      Approve
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
