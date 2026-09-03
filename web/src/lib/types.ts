/**
 * 平台契约镜像（接口契约.md ④⑥）—— 手写类型，唯一允许与后端对齐的地方。
 * 接口变更以 docs/接口文档/接口契约.md 为准同步本文件。
 */

// ---- ContentBlock（契约⑥ Message） -------------------------------------

export type TextBlock = { type: "text"; text: string };
export type ImageBlock = { type: "image"; media_type: string; data: string };
export type ToolCallBlock = { type: "tool_call"; id: string; name: string; input: Record<string, unknown> };
export type ToolResultBlock = { type: "tool_result"; tool_use_id: string; content: string; is_error: boolean };

export type ContentBlock = TextBlock | ImageBlock | ToolCallBlock | ToolResultBlock;

export type PlatformMessage = {
  role: "user" | "assistant";
  content: ContentBlock[];
  metadata?: Record<string, unknown>;
};

// ---- REST（契约⑥） -------------------------------------------------------

export type Session = { id: string; title: string; model: string; archived?: boolean };

export type Run = {
  id: string;
  session_id: string;
  kind: "new" | "resume";
  status: "queued" | "running" | "interrupted" | "succeeded" | "failed" | "cancelled";
  usage_input: number;
  usage_output: number;
  error: { code: string; message: string } | null;
};

export type ApprovalItem = {
  call_id: string;
  tool_name: string;
  reason: string;
  risk_level: string;
  input_preview: string;
};

export type ApprovalTicket = {
  ticket_id: string;
  run_id: string;
  items: ApprovalItem[];
  status: "pending" | "decided" | "expired";
  expires_at: number;
};

// ---- SSE（契约④） ---------------------------------------------------------

export type UiPayload = { kind: string; data: Record<string, unknown> } | null;

export type SSEEventType =
  | "assistant_delta"
  | "assistant_turn_complete"
  | "tool_started"
  | "tool_completed"
  | "compact_progress"
  | "approval_required"
  | "status"
  | "error"
  | "run_finished";

export type SSEEventMap = {
  assistant_delta: { text: string };
  assistant_turn_complete: { message: PlatformMessage };
  tool_started: { tool_name: string; tool_input: Record<string, unknown> };
  tool_completed: { tool_name: string; output: string; is_error: boolean; ui: UiPayload };
  compact_progress: { stage: string; detail: string };
  approval_required: { ticket_id: string; run_id: string; items: ApprovalItem[] };
  status: { message: string };
  error: { code: string; message: string };
  run_finished: {
    usage: { input_tokens: number; output_tokens: number; total_tokens: number };
    stop_reason_hint: string | null;
    error: { code: string; message: string } | null;
  };
};

export type SSEEventOf<T extends SSEEventType> = { type: T; payload: SSEEventMap[T] };
