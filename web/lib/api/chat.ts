// 对话 API 封装(005 §4)

import { apiGet, apiPost, streamSse, type SseEvent } from "./client";
import type { ChatMessage, SessionInfo } from "../types";

export async function listSessions(): Promise<SessionInfo[]> {
  return apiGet<SessionInfo[]>("/chat/sessions");
}

export async function createSession(
  pluginId: string | null = null,
): Promise<SessionInfo> {
  return apiPost<SessionInfo>("/chat/sessions", { plugin_id: pluginId });
}

export async function getHistory(sid: string): Promise<ChatMessage[]> {
  return apiGet<ChatMessage[]>(`/chat/sessions/${sid}/messages`);
}

// 发送消息,逐条返回 SSE 事件(delta / tool_call / done / error)
export function sendMessage(
  sid: string,
  content: string,
): AsyncGenerator<SseEvent> {
  return streamSse(`/chat/sessions/${sid}/messages`, { content });
}
