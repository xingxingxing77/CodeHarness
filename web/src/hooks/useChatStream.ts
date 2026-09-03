"use client";

/**
 * useChatStream：SSE 订阅（EventSource + Last-Event-ID 续传）→ chatStore 归约。
 * 状态本体在 zustand store；本 hook 只做连接管理与发送/决策动作。
 */

import { useCallback, useEffect, useRef } from "react";

import { api } from "@/lib/api";
import { mapErrorText } from "@/lib/errors";
import { reduceEvent, useChatStore, type AnySSEEvent } from "@/stores/chatStore";
import type { SSEEventType } from "@/lib/types";

const READ_TIMEOUT_MS = 30_000;

export function useChatStream(sessionId: string | null) {
  const loadHistory = useChatStore((s) => s.loadHistory);
  const appendUser = useChatStore((s) => s.appendUser);
  const setStatus = useChatStore((s) => s.setStatus);
  const setLastError = useChatStore((s) => s.setLastError);
  const resetTurn = useChatStore((s) => s.resetTurn);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 历史：进页拉一次（事实源）
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    api
      .listMessages(sessionId)
      .then((data) => {
        if (!cancelled) loadHistory(data.messages);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [sessionId, loadHistory]);

  // SSE 订阅（EventSource 断线自动重连并带 Last-Event-ID）
  useEffect(() => {
    if (!sessionId) return;
    const es = new EventSource(api.eventsUrl(sessionId));
    let timeoutRef: ReturnType<typeof setTimeout> | null = null;

    const armTimeout = () => {
      if (timeoutRef) clearTimeout(timeoutRef);
      timeoutRef = setTimeout(() => {
        setStatus("等待响应超时，可点击 Stop 后重试");
      }, READ_TIMEOUT_MS);
    };

    const on = <T extends SSEEventType>(type: T) => {
      es.addEventListener(type, (e) => {
        if (type === "run_finished") {
          if (timeoutRef) clearTimeout(timeoutRef);  // 收敛后不再触发读超时
        } else {
          armTimeout();
        }
        const full = JSON.parse((e as MessageEvent).data) as AnySSEEvent;
        reduceEvent(full);
      });
    };
    (
      [
        "assistant_delta",
        "assistant_turn_complete",
        "tool_started",
        "tool_completed",
        "compact_progress",
        "approval_required",
        "status",
        "error",
        "run_finished",
      ] as SSEEventType[]
    ).forEach(on);

    es.onerror = () => {
      // EventSource 自动重连；仅在连接彻底关闭时提示
      if (es.readyState === EventSource.CLOSED) {
        setLastError({ code: "internal", message: "事件流已断开，请刷新页面恢复" });
      }
    };

    armTimeout();
    return () => {
      if (timeoutRef) clearTimeout(timeoutRef);
      es.close();
    };
  }, [sessionId, setStatus, setLastError]);

  const send = useCallback(
    async (text: string) => {
      if (!sessionId || !text.trim()) return;
      appendUser(text.trim());
      try {
        await api.sendMessage(sessionId, [{ type: "text", text: text.trim() }]);
      } catch (err) {
        resetTurn();
        setLastError({
          code: "internal",
          message: err instanceof Error ? err.message : mapErrorText("internal"),
        });
      }
    },
    [sessionId, appendUser, resetTurn, setLastError],
  );

  const decide = useCallback(
    async (
      ticketId: string,
      runId: string,
      choices: { call_id: string; approve: boolean; reason?: string }[],
    ) => {
      try {
        await api.decide(runId, ticketId, choices);
      } catch (err) {
        setLastError({
          code: "internal",
          message: err instanceof Error ? err.message : "决策提交失败",
        });
      }
    },
    [setLastError],
  );

  return { send, decide };
}
