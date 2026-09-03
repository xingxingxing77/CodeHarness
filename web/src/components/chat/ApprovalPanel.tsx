"use client";

/** 审批面板：approval_required 事件的直接消费面（UX布局设计 §三）。 */

import { useState } from "react";

import { Button } from "@/components/bui/atoms/button";
import { ValuePill } from "@/components/bui/atoms/entity-chip";

export type ApprovalPayload = {
  ticket_id: string;
  run_id: string;
  items: { call_id: string; tool_name: string; reason: string; risk_level: string; input_preview: string }[];
};

export function ApprovalPanel({
  approval,
  onDecide,
}: {
  approval: ApprovalPayload;
  onDecide: (ticketId: string, runId: string, choices: { call_id: string; approve: boolean; reason?: string }[]) => void;
}) {
  const [busy, setBusy] = useState(false);

  const submit = (approve: boolean) => {
    setBusy(true);
    onDecide(
      approval.ticket_id,
      approval.run_id,
      approval.items.map((i) => ({ call_id: i.call_id, approve, reason: approve ? "approved in UI" : "denied in UI" })),
    );
  };

  return (
    <div className="w-full rounded-card border border-line bg-surface shadow-card" style={{ animation: "fade-up 250ms cubic-bezier(0.16,1,0.3,1) both" }}>
      <div className="primitive-card-bar flex items-center gap-2 border-b border-line">
        <span className="text-[12.5px] font-medium text-ink">Approval required</span>
        <ValuePill>{approval.items.length} item(s)</ValuePill>
      </div>
      <div className="flex flex-col gap-3 p-4">
        {approval.items.map((item) => (
          <div key={item.call_id} className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-medium text-ink">{item.tool_name}</span>
              <ValuePill>{item.risk_level}</ValuePill>
            </div>
            {item.reason && <div className="text-[12px] text-ink-2">{item.reason}</div>}
            <pre className="max-h-32 overflow-auto rounded-[6px] bg-inset p-2 font-mono text-[12px] text-ink-2">
              {item.input_preview || "(no input)"}
            </pre>
          </div>
        ))}
        <div className="flex items-center justify-end gap-2">
          <Button variant="secondary" disabled={busy} onClick={() => submit(false)}>
            Deny
          </Button>
          <Button disabled={busy} onClick={() => submit(true)}>
            Approve
          </Button>
        </div>
      </div>
    </div>
  );
}
