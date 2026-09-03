"use client";

/** 聊天状态归约（zustand）：SSE 事件 → store → 组件（前端设计 §4 数据流）。 */

import { create } from "zustand";

import type { ApprovalItem, ContentBlock, PlatformMessage, SSEEventMap } from "@/lib/types";

export type ToolRun = {
  key: string;
  tool_name: string;
  status: "running" | "done" | "error";
  output?: string;
  ui?: { kind: string; data: Record<string, unknown> } | null;
};

export type ThoughtStep = { label: string; state: "running" | "done" };

export type Usage = { input_tokens: number; output_tokens: number; total_tokens: number };

export type ApprovalState = {
  ticket_id: string;
  run_id: string;
  items: ApprovalItem[];
};

type ChatState = {
  messages: PlatformMessage[];
  live: PlatformMessage | null;          // 活跃流式 assistant 消息
  thoughtSteps: ThoughtStep[];
  tools: ToolRun[];
  typewriterTarget: string | null;       // 终态打字机回放
  status: string | null;
  usage: Usage | null;
  approval: ApprovalState | null;
  finished: boolean;
  lastError: { code: string; message: string } | null;

  loadHistory: (messages: PlatformMessage[]) => void;
  appendUser: (content: ContentBlock[]) => void;
  appendStreamChunk: (text: string) => void;
  setFinalAnswer: (message: PlatformMessage) => void;
  addThought: (label: string) => void;
  resolveThought: (label: string) => void;
  addTool: (tool_name: string) => void;
  updateTool: (tool_name: string, output: string, is_error: boolean, ui: ToolRun["ui"]) => void;
  setStatus: (message: string | null) => void;
  setApproval: (a: ApprovalState | null) => void;
  setUsage: (u: Usage) => void;
  setTypewriterTarget: (text: string | null) => void;
  setLastError: (e: { code: string; message: string } | null) => void;
  resetTurn: () => void;
};

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  live: null,
  thoughtSteps: [],
  tools: [],
  typewriterTarget: null,
  status: null,
  usage: null,
  approval: null,
  finished: true,
  lastError: null,

  loadHistory: (messages) => set({ messages, finished: true }),

  appendUser: (content) =>
    set((s) => ({
      messages: [...s.messages, { role: "user", content }],
      finished: false,
      status: null,
      usage: null,
      typewriterTarget: null,
      approval: null,
      thoughtSteps: [],
      tools: [],
      lastError: null,
    })),

  appendStreamChunk: (text) =>
    set((s) => {
      const live = s.live ?? { role: "assistant" as const, content: [{ type: "text" as const, text: "" }] };
      const block = live.content[0];
      if (block.type !== "text") return s;
      const content = [{ ...block, text: block.text + text }];
      return { live: { ...live, content }, finished: false };
    }),

  setFinalAnswer: (message) =>
    set((s) => {
      const messages = [...s.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") messages[messages.length - 1] = message;
      else messages.push(message);
      return { messages, live: null };
    }),

  addThought: (label) =>
    set((s) => {
      const steps = s.thoughtSteps.map((t) => (t.state === "running" ? { ...t, state: "done" as const } : t));
      steps.push({ label, state: "running" });
      return { thoughtSteps: steps.slice(-12) };
    }),

  resolveThought: (label) =>
    set((s) => {
      const steps = [...s.thoughtSteps];
      for (let i = steps.length - 1; i >= 0; i--) {
        if (steps[i].state === "running") {
          steps[i] = { ...steps[i], label, state: "done" };
          break;
        }
      }
      return { thoughtSteps: steps };
    }),

  addTool: (tool_name) =>
    set((s) => {
      const steps = s.thoughtSteps.map((t) => (t.state === "running" ? { ...t, state: "done" as const } : t));
      steps.push({ label: `调用 ${tool_name}`, state: "running" });
      return {
        thoughtSteps: steps.slice(-12),
        tools: [...s.tools, { key: `${tool_name}:${s.tools.length}`, tool_name, status: "running" as const }],
      };
    }),

  updateTool: (tool_name, output, is_error, ui) =>
    set((s) => {
      const tools = [...s.tools];
      const idx = tools.findIndex((t) => t.status === "running" && t.tool_name === tool_name);
      if (idx >= 0) tools[idx] = { ...tools[idx], status: is_error ? "error" : "done", output, ui };
      else tools.push({ key: `${tool_name}:done:${tools.length}`, tool_name, status: is_error ? "error" : "done", output, ui });
      const steps = s.thoughtSteps.map((t) =>
        t.state === "running" && t.label.startsWith(`调用 ${tool_name}`) ? { ...t, state: "done" as const } : t,
      );
      return { tools, thoughtSteps: steps };
    }),

  setStatus: (message) => set({ status: message }),

  setApproval: (approval) => set({ approval, finished: false }),

  setUsage: (usage) => set({ usage }),

  setTypewriterTarget: (text) => set({ typewriterTarget: text }),

  setLastError: (e) => set({ lastError: e }),

  resetTurn: () =>
    set({
      status: null,
      approval: null,
      lastError: null,
      finished: true,
    }),
}));

// ---------------------------------------------------------------------------
// SSE 事件 → store 归约（useChatStream 消费）
// ---------------------------------------------------------------------------

export type AnySSEEvent = { [K in keyof SSEEventMap]: { type: K; payload: SSEEventMap[K] } }[keyof SSEEventMap];

export function reduceEvent(event: AnySSEEvent): void {
  const s = useChatStore.getState();
  switch (event.type) {
    case "assistant_delta":
      s.appendStreamChunk(event.payload.text);
      break;
    case "assistant_turn_complete":
      s.setFinalAnswer(event.payload.message);
      break;
    case "tool_started":
      s.addTool(event.payload.tool_name);
      break;
    case "tool_completed":
      s.updateTool(event.payload.tool_name, event.payload.output, event.payload.is_error, event.payload.ui);
      break;
    case "status":
      s.setStatus(event.payload.message);
      s.addThought(event.payload.message);
      break;
    case "compact_progress":
      s.setStatus(`压缩对话记忆（${event.payload.stage}）`);
      break;
    case "approval_required":
      s.setApproval(event.payload);
      break;
    case "error":
      s.setLastError(event.payload);
      break;
    case "run_finished": {
      s.setUsage(event.payload.usage);
      const messages = useChatStore.getState().messages;
      const last = messages[messages.length - 1];
      const text = last && last.role === "assistant" ? last.content.find((b) => b.type === "text") : undefined;
      s.setTypewriterTarget(text && text.type === "text" ? text.text : null);
      s.resetTurn();
      break;
    }
    default:
      break;
  }
}
