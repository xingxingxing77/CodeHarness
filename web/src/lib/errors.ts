/** 错误码 → 中文文案（契约⑥ error.code；接口文档错误码表） */

const MAP: Record<string, string> = {
  upstream: "模型服务暂不可用，请稍后重试",
  rate_limit: "请求过于频繁，请稍后再试",
  auth: "登录已过期，请重新登录",
  max_turns_exceeded: "已达本轮对话的轮次上限",
  context_overflow: "对话过长，已自动压缩仍超出上下文",
  empty_response: "模型返回了空内容，本轮已终止",
  empty_stream: "模型流式响应异常中断",
  session_busy: "会话正在运行中，请等待完成后再发送",
  quota_exceeded: "租户配额已用尽",
  run_not_resumable: "该运行不处于可恢复状态",
  ticket_expired: "审批已超时，按拒绝处理",
  not_found: "资源不存在",
  forbidden: "没有访问权限",
  internal: "服务开小差了，请稍后重试",
};

export function mapErrorText(code: string | null | undefined): string {
  if (!code) return "服务开小差了，请稍后重试";
  return MAP[code] ?? `出错了（${code}）`;
}
