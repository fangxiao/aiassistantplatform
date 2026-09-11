// 知识库 API 封装 (M12, 设计 008 §7)

import { apiDelete, apiGet, apiPatch, apiPost, apiUpload } from "./client";
import type { KbDocumentInfo, KbInfo, KbMemberInfo, KbSearchResponse } from "../types";

export async function listKbs(): Promise<KbInfo[]> {
  return apiGet<KbInfo[]>("/kb/kbs");
}

export interface KbCreatePayload {
  name: string;
  slug: string;
  visibility: "private" | "shared" | "public";
  description?: string;
}

export async function createKb(payload: KbCreatePayload): Promise<KbInfo> {
  return apiPost<KbInfo>("/kb/kbs", payload);
}

export async function updateKb(
  kbId: string,
  payload: { name?: string; description?: string },
): Promise<KbInfo> {
  return apiPatch<KbInfo>(`/kb/kbs/${kbId}`, payload);
}

export async function deleteKb(kbId: string): Promise<{ ok: boolean }> {
  return apiDelete<{ ok: boolean }>(`/kb/kbs/${kbId}`);
}

export async function uploadDocument(kbId: string, file: File): Promise<KbDocumentInfo> {
  return apiUpload<KbDocumentInfo>(`/kb/kbs/${kbId}/documents`, file);
}

export interface KbSaveSource {
  app: string; // 消费方标识(platform / swiftship / ...),消费无关溯源
  session_id?: string;
  message_id?: string; // 同库幂等键
}

export interface KbSaveTextPayload {
  title: string;
  content: string;
  mime?: "text/markdown" | "text/plain" | "text/html";
  source?: KbSaveSource;
}

/** 文本直存(设计 008 §11):会话产出物收藏,复用 pipeline。 */
export async function saveTextDocument(kbId: string, payload: KbSaveTextPayload): Promise<KbDocumentInfo> {
  return apiPost<KbDocumentInfo>(`/kb/kbs/${kbId}/documents/from-text`, payload);
}

export async function listDocuments(kbId: string): Promise<KbDocumentInfo[]> {
  return apiGet<KbDocumentInfo[]>(`/kb/kbs/${kbId}/documents`);
}

export async function deleteDocument(kbId: string, docId: string): Promise<{ ok: boolean }> {
  return apiDelete<{ ok: boolean }>(`/kb/kbs/${kbId}/documents/${docId}`);
}

export async function retryDocument(kbId: string, docId: string): Promise<KbDocumentInfo> {
  return apiPost<KbDocumentInfo>(`/kb/kbs/${kbId}/documents/${docId}/retry`, {});
}

export async function searchKb(
  kbId: string,
  query: string,
  topK = 5,
): Promise<KbSearchResponse> {
  return apiPost<KbSearchResponse>(`/kb/kbs/${kbId}/search`, { query, top_k: topK });
}

export async function publishKb(kbId: string, version?: string): Promise<KbInfo> {
  return apiPost<KbInfo>(`/kb/kbs/${kbId}/publish`, version ? { version } : {});
}

// ---------------------------------------------------------------- 成员管理(设计 008 §12.3)

export async function listKbMembers(kbId: string): Promise<KbMemberInfo[]> {
  return apiGet<KbMemberInfo[]>(`/kb/kbs/${kbId}/members`);
}

export async function addKbMemberByEmail(kbId: string, email: string): Promise<KbMemberInfo> {
  return apiPost<KbMemberInfo>(`/kb/kbs/${kbId}/members`, { email });
}

export async function removeKbMember(kbId: string, userId: string): Promise<{ ok: boolean }> {
  return apiDelete<{ ok: boolean }>(`/kb/kbs/${kbId}/members/${userId}`);
}
