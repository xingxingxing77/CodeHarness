"use client";

/**
 * useChatStream：会话 SSE 订阅 + 状态归约（前端文档 §4）。
 * EventSource 断线自动携带 Last-Event-ID 重连；历史以 GET /messages 为准。
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { ApprovalTicket, PlatformMessage, SSEEventMap, SSEEventType } from "@/lib/types";

export type ToolRun = {
  key: string;
  tool_name: string;
  status: "running" | "done" | "error";
  output?: string;
  ui?: { kind: string; data: Record<string, unknown> } | null;
};

export type ChatState = {
  messages: PlatformMessage[];
  streamingText: string;
  tools: ToolRun[];
  status: string | null;
  usage: { input_tokens: number; output_tokens: number; total_tokens: number } | null;
  finished: boolean;
  approval: { ticket_id: string; run_id: string; items: { call_id: string; tool_name: string; reason: string; risk_level: string; input_preview: string }[] } | null;
};

export function useChatStream(sessionId: string | null) {
  const [state, setState] = useState<ChatState>({
    messages: [],
    streamingText: "",
    tools: [],
    status: null,
    usage: null,
    finished: true,
    approval: null,
  });
  const esRef = useRef<EventSource | null>(null);
  const finishedRef = useRef(true);

  // 历史：进页拉一次（事实源）
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    api.listMessages(sessionId).then((data) => {
      if (!cancelled) setState((s) => ({ ...s, messages: data.messages }));
    });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // SSE 订阅（EventSource 自动重连并带 Last-Event-ID）
  useEffect(() => {
    if (!sessionId) return;
    const es = new EventSource(api.eventsUrl(sessionId));
    esRef.current = es;

    const on = <T extends SSEEventType>(type: T, fn: (payload: SSEEventMap[T]) => void) => {
      // SSE data = {type, payload}（SSEEvent 全量 JSON）；此处拆出 payload
      es.addEventListener(type, (e) => fn((JSON.parse((e as MessageEvent).data) as { type: T; payload: SSEEventMap[T] }).payload));
    };

    on("assistant_delta", (p) => {
      setState((s) => ({ ...s, streamingText: s.streamingText + p.text, finished: false }));
    });

    on("assistant_turn_complete", (p) => {
      setState((s) => ({
        ...s,
        messages: [...s.messages, p.message],
        streamingText: "",
      }));
    });

    on("tool_started", (p) => {
      setState((s) => ({
        ...s,
        tools: [...s.tools, { key: `${p.tool_name}:${s.tools.length}`, tool_name: p.tool_name, status: "running" }],
        finished: false,
      }));
    });

    on("tool_completed", (p) => {
      setState((s) => {
        const tools = [...s.tools];
        const idx = tools.findIndex((t) => t.status === "running" && t.tool_name === p.tool_name);
        if (idx >= 0) tools[idx] = { ...tools[idx], status: p.is_error ? "error" : "done", output: p.output, ui: p.ui };
        else tools.push({ key: `${p.tool_name}:done:${tools.length}`, tool_name: p.tool_name, status: p.is_error ? "error" : "done", output: p.output, ui: p.ui });
        return { ...s, tools };
      });
    });

    on("approval_required", (p) => {
      setState((s) => ({ ...s, approval: p }));
    });

    on("status", (p) => {
      setState((s) => ({ ...s, status: p.message }));
    });

    on("run_finished", (p) => {
      setState((s) => ({
        ...s,
        streamingText: "",
        status: null,
        usage: p.usage,
        finished: true,
        approval: null,
      }));
      finishedRef.current = true;
    });

    es.onerror = () => {
      // EventSource 自动重连（服务端基于 Last-Event-ID 重放），此处仅标记
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [sessionId]);

  const send = useCallback(
    async (text: string) => {
      if (!sessionId || !text.trim()) return;
      const { run_id } = await api.sendMessage(sessionId, [{ type: "text", text }]);
      setState((s) => ({
        ...s,
        messages: [...s.messages, { role: "user", content: [{ type: "text", text }] }],
        status: null,
        usage: null,
        finished: false,
      }));
      return run_id;
    },
    [sessionId],
  );

  const decide = useCallback(
    async (ticketId: string, runId: string, choices: { call_id: string; approve: boolean; reason?: string }[]) => {
      await api.decide(runId, ticketId, choices);
      setState((s) => ({ ...s, approval: null }));
    },
    [],
  );

  return { state, send, decide };
}
