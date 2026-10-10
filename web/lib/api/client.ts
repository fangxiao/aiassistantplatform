// API 客户端:基础封装 + SSE 流式解析
//
// 已登录时统一注入 Authorization: Bearer <token>(M1);未登录请求不带该头。
// M24 P2:401 时先用 httpOnly cookie 静默 refresh 一次并重放(单飞,防并发
// 重放触发全族吊销);refresh 失败才清理登录态跳登录页。

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";

/** 结构化 API 错误:携带 status/code,供 UI 按 code 分流(如 email_unverified) */
export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(status: number, code: string | undefined, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function toApiError(status: number, text: string): ApiError {
  try {
    const body = JSON.parse(text) as { error?: { code?: string; message?: string }; detail?: { code?: string; message?: string } };
    const err = body.error ?? body.detail;
    if (err?.message) return new ApiError(status, err.code, err.message);
  } catch {
    /* 非 JSON 原文兜底 */
  }
  return new ApiError(status, undefined, `HTTP ${status}: ${text.slice(0, 180)}`);
}

export interface SseEvent {
  event: string;
  data: unknown;
}

// 读取登录 token(localStorage);服务端渲染时无 window 返回 null
export function getAuthHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("agentplatform_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function handleUnauthorized(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("agentplatform_token");
  localStorage.removeItem("agentplatform_user");
  if (!window.location.pathname.startsWith("/auth")) {
    window.location.href = "/auth";
  }
}

// ── 静默续期(M24 P2)────────────────────────────────────────
// cookie 内 refresh 令牌 → POST /auth/refresh → 新 access 落 localStorage。
// 单飞:并发 401 共享同一次 refresh(重复用已轮换 cookie 会触发全族吊销)。

let refreshInFlight: Promise<boolean> | null = null;

export async function refreshSession(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const resp = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          credentials: "include",
        });
        if (!resp.ok) return false;
        const data = (await resp.json()) as { token: string; user?: unknown };
        localStorage.setItem("agentplatform_token", data.token);
        if (data.user) {
          localStorage.setItem("agentplatform_user", JSON.stringify(data.user));
        }
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

function authedInit(init: RequestInit): RequestInit {
  const base = init.headers instanceof Headers ? Object.fromEntries(init.headers) : (init.headers ?? {});
  return { ...init, headers: { ...getAuthHeader(), ...base } };
}

// 统一请求核心:401 → 静默 refresh 一次 → 重放一次;再失败走清理跳转
async function requestOnce(path: string, init: RequestInit): Promise<Response> {
  return fetch(`${API_BASE}${path}`, authedInit(init));
}

async function requestWithRefresh(path: string, init: RequestInit): Promise<Response> {
  const first = await requestOnce(path, init);
  if (first.status !== 401) return first;
  if (await refreshSession()) {
    const second = await requestOnce(path, init);
    if (second.status !== 401) return second;
  }
  handleUnauthorized();
  return first;
}

function jsonHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

async function errText(status: number, resp: Response): Promise<ApiError> {
  return toApiError(status, await resp.text());
}

export async function apiFetch<T>(
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  const resp = await requestWithRefresh(path, {
    method: init.method ?? "GET",
    headers: jsonHeaders(),
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (resp.status === 401) throw new Error(`HTTP 401: 登录已过期，请重新登录`);
  if (!resp.ok) throw await errText(resp.status, resp);
  return (await resp.json().catch(() => undefined)) as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  const resp = await requestWithRefresh(path, { method: "GET" });
  if (resp.status === 401) throw new Error(`HTTP 401: 登录已过期，请重新登录`);
  if (!resp.ok) throw await errText(resp.status, resp);
  return (await resp.json()) as T;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const resp = await requestWithRefresh(path, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (resp.status === 401) throw new Error(`HTTP 401: 登录已过期，请重新登录`);
  if (!resp.ok) throw await errText(resp.status, resp);
  return (await resp.json()) as T;
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const resp = await requestWithRefresh(path, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (resp.status === 401) throw new Error(`HTTP 401: 登录已过期，请重新登录`);
  if (!resp.ok) throw await errText(resp.status, resp);
  return (await resp.json()) as T;
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const resp = await requestWithRefresh(path, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (resp.status === 401) throw new Error(`HTTP 401: 登录已过期，请重新登录`);
  if (!resp.ok) throw await errText(resp.status, resp);
  return (await resp.json()) as T;
}

export async function apiDelete<T>(path: string): Promise<T> {
  const resp = await requestWithRefresh(path, { method: "DELETE" });
  if (resp.status === 401) throw new Error(`HTTP 401: 登录已过期，请重新登录`);
  if (!resp.ok) throw await errText(resp.status, resp);
  if (resp.status === 204) return {} as T;
  return (await resp.json()) as T;
}

// multipart 文件上传(kb 文档上传等);不设置 Content-Type,由浏览器补 boundary
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const resp = await requestWithRefresh(path, { method: "POST", body: form });
  if (resp.status === 401) throw new Error(`HTTP 401: 登录已过期，请重新登录`);
  if (!resp.ok) throw await errText(resp.status, resp);
  return (await resp.json()) as T;
}


// 流式 POST,逐条产出 SSE 事件(对应后端 event: X\ndata: {...}\n\n 帧)
export async function* streamSse(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeader() },
    body: JSON.stringify(body),
    signal,
  });
  if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx = buffer.indexOf("\n\n");
    while (idx >= 0) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const parsed = parseFrame(frame);
      if (parsed) yield parsed;
      idx = buffer.indexOf("\n\n");
    }
  }
}

function parseFrame(frame: string): SseEvent | null {
  let event = "message";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7);
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return { event, data };
  }
}
