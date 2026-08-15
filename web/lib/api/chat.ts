// 对话 API 封装(005 §4 / 003 v2.0 §9)

import { apiDelete, apiGet, apiPatch, apiPost, streamSse, type SseEvent } from "./client";
import type { ChatMessage, ContentBlock, SessionInfo } from "../types";

export async function listSessions(): Promise<SessionInfo[]> {
  return apiGet<SessionInfo[]>("/chat/sessions");
}

export async function createSession(
  pluginId: string | null = null,
): Promise<SessionInfo> {
  return apiPost<SessionInfo>("/chat/sessions", { plugin_id: pluginId });
}

export async function deleteSession(sid: string): Promise<{ ok: boolean }> {
  return apiDelete<{ ok: boolean }>(`/chat/sessions/${sid}`);
}

export async function renameSession(
  sid: string,
  title: string,
): Promise<SessionInfo> {
  return apiPatch<SessionInfo>(`/chat/sessions/${sid}`, { title });
}

export async function getHistory(sid: string): Promise<ChatMessage[]> {
  return apiGet<ChatMessage[]>(`/chat/sessions/${sid}/messages`);
}

// 发送消息,逐条返回 SSE 事件(delta / block_meta / tool_call / done / error)
export function sendMessage(
  sid: string,
  content: string,
): AsyncGenerator<SseEvent> {
  return streamSse(`/chat/sessions/${sid}/messages`, { content });
}

// 交互回传
export async function interactBlock(
  sid: string,
  bid: string,
  action: string,
  value: any,
  args?: Record<string, any>,
): Promise<{ blocks: ContentBlock[] }> {
  return apiPost<{ blocks: ContentBlock[] }>(
    `/chat/sessions/${sid}/blocks/${bid}/interact`,
    { action, value, args },
  );
}

// 发送轻反馈事件
export async function sendFeedbackEvent(
  sid: string,
  kind: string,
  targetBlockId?: string,
  value?: any,
): Promise<{ ok: boolean }> {
  return apiPost<{ ok: boolean }>(`/chat/sessions/${sid}/events`, {
    kind,
    target_block_id: targetBlockId,
    value,
  });
}
