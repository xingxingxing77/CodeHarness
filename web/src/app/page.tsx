"use client";

/** 首页：自动创建会话并直达聊天页（rag-web ensureThread 惰性创建模式）。 */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Shimmer } from "@/components/bui/atoms/shimmer";
import { api } from "@/lib/api";

const DRAFT_KEY = "codeharness_draft_session";

export default function HomePage() {
  const router = useRouter();
  const started = useRef(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const draft = sessionStorage.getItem(DRAFT_KEY);
    if (draft) {
      sessionStorage.removeItem(DRAFT_KEY);
      router.replace(`/sessions/${draft}`);
      return;
    }

    api
      .createSession("claude-sonnet-4-6", "New session")
      .then(({ id }) => {
        sessionStorage.setItem(DRAFT_KEY, id);
        router.replace(`/sessions/${id}`);
      })
      .catch(() => setReady(true));
  }, [router]);

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 bg-page px-4">
      <div className="text-center text-[28px] font-medium text-ink">Codeharness</div>
      {ready ? (
        <div className="rounded-card border border-line bg-surface p-6 text-center text-[13px] text-ink-2">
          Cannot reach the server. Start it with <code className="font-mono">python scripts/run_server.py</code>.
        </div>
      ) : (
        <div className="flex w-full max-w-[560px] flex-col gap-2">
          <Shimmer>Preparing your workspace…</Shimmer>
        </div>
      )}
    </main>
  );
}
