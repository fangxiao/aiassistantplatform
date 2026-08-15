// 前端共享类型(对齐 003 v2.0 消息信封 / 004 数据模型 / 005 API)

export interface ContentBlock {
  type: string;
  data: Record<string, any>;
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
  blocks?: ContentBlock[];
  toolCalls?: ToolCallInfo[];
  created_at?: string;
}

export interface SessionInfo {
  id: string;
  plugin_id: string | null;
  title: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface AssistantInfo {
  id: string;
  name: string;
  version: string;
  description: string | null;
  author: string | null;
  model: string | null;
  depends_on: string[];
  deployed_at: string;
  manifest: Record<string, any>;
}

export interface PluginInfo {
  id: string;
  name: string;
  version: string;
  status: "active" | "disabled";
  owner_id: string | null;
  deployed_at: string;
  manifest: Record<string, any>;
}

export interface LlmEndpointInfo {
  id: string;
  name: string;
  base_url: string;
  model: string;
  is_default: boolean;
}
