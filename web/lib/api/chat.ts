// 对话 API 封装(005 §4 / 003 v2.0 §9)

import { apiDelete, apiGet, apiPatch, apiPost, apiUpload, streamSse, type SseEvent } from "./client";
import type { ChatMessage, ContentBlock, SessionInfo } from "../types";

export async function listSessions(): Promise<SessionInfo[]> {
  return apiGet<SessionInfo[]>("/chat/sessions");
}

export async function createSession(
  pluginId: string | null = null,
  mountedKbIds: string[] = [],
): Promise<SessionInfo> {
  return apiPost<SessionInfo>("/chat/sessions", {
    plugin_id: pluginId,
    mounted_kb_ids: mountedKbIds,
  });
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

// 更新会话挂载知识库 (M12);kbIds 传 [] 表示清空挂载
export async function updateSessionKbs(
  sid: string,
  kbIds: string[],
): Promise<SessionInfo> {
  return apiPatch<SessionInfo>(`/chat/sessions/${sid}`, { mounted_kb_ids: kbIds });
}

export async function getHistory(sid: string): Promise<ChatMessage[]> {
  return apiGet<ChatMessage[]>(`/chat/sessions/${sid}/messages`);
}

// 发送消息,逐条返回 SSE 事件(delta / block_meta / tool_call / done / error)
// images(设计 012):data:image/* dataURL 多模态输入
export function sendMessage(
  sid: string,
  content: string,
  images: string[] = [],
  signal?: AbortSignal,
  docs: string[] = [],
): AsyncGenerator<SseEvent> {
  return streamSse(`/chat/sessions/${sid}/messages`, { content, images, docs }, signal);
}

// 打磨②:重新生成最后一条助手回复(撤回 + 重跑)
export function regenerateLast(
  sid: string,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  return streamSse(`/chat/sessions/${sid}/regenerate`, {}, signal);
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

// 打磨④:对话图片上传(对象存储化)——返回服务端 URL,消息块不再存 dataURL
export async function uploadImage(file: File): Promise<{ url: string; size: number }> {
  return apiUpload<{ url: string; size: number }>("/files/upload", file);
}

// 打磨⑥:单文档即问上传(pdf/md/txt,临时解析不入库)
export async function uploadDoc(file: File): Promise<{ url: string; size: number }> {
  return apiUpload<{ url: string; size: number }>("/files/upload", file);
}

// 会话分享(产品成熟度③):创建/撤销只读链接
export async function createShare(sid: string, days = 7): Promise<{ share_token: string; share_url: string; expires_at: string }> {
  return apiPost(`/chat/sessions/${sid}/share`, { days });
}

export async function revokeShare(sid: string): Promise<void> {
  await apiDelete(`/chat/sessions/${sid}/share`);
}
