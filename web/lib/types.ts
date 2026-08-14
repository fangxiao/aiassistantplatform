// 前端共享类型(对齐 003 v2.0 消息信封 / 005 §4 SSE)

export interface ContentBlock {
  type: string;
  data: Record<string, unknown>;
  meta?: { id?: string; group?: string };
}

export interface ToolCallInfo {
  kind: string;
  name: string;
  args: unknown;
  result: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "tool" | "system";
  text: string;
  toolCalls?: ToolCallInfo[];
}

export interface SessionInfo {
  id: string;
  plugin_id: string | null;
  title: string | null;
}
