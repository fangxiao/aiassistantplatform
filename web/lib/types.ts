// 前端共享类型(对齐 003 v2.0 消息信封 / 004 数据模型 / 005 API)

export interface ContentBlock {
  type: string;
  data: Record<string, any>;
  meta?: { id?: string; group?: string };
}

export interface ToolCallInfo {
  id?: string;
  kind?: string;
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
  reasoning?: string;   // 模型深度思考内容（流式，展示为思考进度指示器）
  created_at?: string;
}

export interface SessionInfo {
  id: string;
  plugin_id: string | null;
  title: string | null;
  mounted_kb_ids?: string[]; // 会话挂载知识库 (M12)
  created_at?: string;
  updated_at?: string;
}

export interface AssistantInfo {
  id: string;
  name: string;
  display_name?: string | null;
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
  display_name?: string | null;
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
  endpoint_type?: "chat" | "embedding"; // M12: kb 向量化端点
}

export interface BuiltinResourceInfo {
  id: string;
  name: string;
  version: string;
  description: string;
  schema: Record<string, any>;
  dependency_example: string;
}

export interface ContentBlockDef {
  type: string;
  category: "display" | "interactive" | "action";
  category_name: string;
  name: string;
  description: string;
  sample_data: Record<string, any>;
  python_snippet: string;
}

export interface CapabilitiesInfo {
  platform: string;
  version: string;
  summary: {
    builtin_skills_count: number;
    builtin_tools_count: number;
    content_blocks_count: number;
  };
  builtin_skills: BuiltinResourceInfo[];
  builtin_tools: BuiltinResourceInfo[];
  content_blocks: ContentBlockDef[];
}

// ===== 知识库 (M12) =====

export interface KbInfo {
  id: string;
  name: string;
  slug: string;
  visibility: "private" | "shared" | "public";
  version: string;
  description: string | null;
  status: string;
  doc_count: number;
  chunk_count: number;
  size_bytes: number;
  can_write: boolean; // 服务端计算:private=owner / shared=owner+成员 / public=developer(设计 008 §11.2/§12.2)
}

export interface KbMemberInfo {
  user_id: string;
  email: string | null;
  role: string;
  created_at: string | null;
}

export type KbDocStatus = "pending" | "parsing" | "embedding" | "ready" | "failed" | "deleted";

export interface KbDocumentInfo {
  id: string;
  kb_id: string;
  filename: string;
  mime: string;
  size_bytes: number;
  status: KbDocStatus;
  error: string | null;
  origin?: "upload" | "session";
  source_app?: string | null;
  source_session_id?: string | null;
  source_message_id?: string | null;
}

export interface KbSearchHit {
  kb_id: string;
  kb_name: string;
  document_id: string;
  document_name: string;
  chunk_index: number;
  score: number;
  text: string;
  source_span: { start: number; end: number };
}

export interface KbSearchResponse {
  results: KbSearchHit[];
  hint?: string | null;
}

