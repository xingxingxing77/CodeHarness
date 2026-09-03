"use client";

/** 会话列表（侧栏 IA 的最小骨架：列表 + 新建）。 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/bui/atoms/button";
import { Shimmer } from "@/components/bui/atoms/shimmer";
import { api } from "@/lib/api";
import type { Session } from "@/lib/types";

export default function SessionsPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [creating, setCreating] = useState(false);

  const load = () => {
    api.listSessions().then(setSessions).catch(() => setSessions([]));
  };

  useEffect(load, []);

  const create = async () => {
    setCreating(true);
    try {
      const { id } = await api.createSession("claude-sonnet-4-6", "New session");
      router.push(`/sessions/${id}`);
    } finally {
      setCreating(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[720px] flex-col gap-4 px-4 py-10">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[20px] font-medium text-ink">Sessions</div>
          <div className="text-[12.5px] text-ink-2">Pick up a conversation or start a new one.</div>
        </div>
        <Button size="md" disabled={creating} onClick={create}>
          {creating ? "Creating…" : "New session"}
        </Button>
      </div>

      {sessions === null ? (
        <div className="flex flex-col gap-2 pt-4">
          <Shimmer>Loading…</Shimmer>
          <Shimmer>Loading…</Shimmer>
        </div>
      ) : sessions.length === 0 ? (
        <div className="mt-16 rounded-card border border-line bg-surface p-6 text-center text-[13px] text-ink-2">
          No sessions yet — create one and say hi.
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {sessions.map((s) => (
            <li key={s.id}>
              <a
                href={`/sessions/${s.id}`}
                className="flex items-center justify-between rounded-card border border-line bg-surface px-4 py-3 shadow-card transition-colors hover:bg-hover"
              >
                <span className="text-[13px] font-medium text-ink">{s.title || s.id.slice(0, 8)}</span>
                <span className="text-[11.5px] text-ink-3">{s.model}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
