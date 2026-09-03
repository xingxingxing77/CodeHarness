"use client";

/**
 * useChatStream：SSE 订阅（EventSource + Last-Event-ID 续传）→ chatStore 归约。
 * 状态本体在 zustand store；本 hook 只做连接管理与发送/决策动作。
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { mapErrorText } from "@/lib/errors";
import { reduceEvent, useChatStore, type AnySSEEvent } from "@/stores/chatStore";
import type { ContentBlock, SSEEventType } from "@/lib/types";

const READ_TIMEOUT_MS = 30_000;

export function useChatStream(
  sessionId: string | null,
  onSessionCreated?: (id: string) => void,
) {
  const [activeId, setActiveId] = useState(sessionId);

  useEffect(() => {
    setActiveId(sessionId);
  }, [sessionId]);
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
    if (!activeId) return;
    // 草稿创建的会话：从缓冲头重放（POST 可能先于订阅到达）
    const after = createdHereRef.current ? "0" : undefined;
    createdHereRef.current = false;
    const es = new EventSource(api.eventsUrl(activeId, after));
    let timeoutRef: ReturnType<typeof setTimeout> | null = null;

    // 读超时 = “无状态变更间隔”30s：任何 store 变更都会重置；空闲（finished）不计时
    const unsubStore = useChatStore.subscribe((s) => {
      if (timeoutRef) clearTimeout(timeoutRef);
      if (!s.finished) {
        timeoutRef = setTimeout(() => {
          setStatus("等待响应超时，可点击 Stop 后重试");
        }, READ_TIMEOUT_MS);
      }
    });

    const on = <T extends SSEEventType>(type: T) => {
      es.addEventListener(type, (e) => {
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

    return () => {
      unsubStore();
      if (timeoutRef) clearTimeout(timeoutRef);
      es.close();
    };
  }, [activeId, setStatus, setLastError]);

  const send = useCallback(
    async (blocks: ContentBlock[], toolId: string | null = null) => {
      if (!blocks.length) return;
      let id = activeId;
      if (!id) {
        // 草稿模式：首条消息时惰性创建会话
        const created = await api.createSession("claude-sonnet-4-6", "New session");
        id = created.id;
        createdHereRef.current = true;
        setActiveId(id);
        onSessionCreated?.(id);
      }
      appendUser(blocks);
      try {
        await api.sendMessage(id, blocks);
      } catch (err) {
        resetTurn();
        setLastError({
          code: "internal",
          message: err instanceof Error ? err.message : mapErrorText("internal"),
        });
      }
    },
    [activeId, appendUser, resetTurn, setLastError, onSessionCreated],
  );
  const createdHereRef = { current: false };

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

  return { send, decide, activeId };
}
