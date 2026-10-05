// 认证 API 封装(M1):注册/登录/当前用户 + token 存取
//
// token 存 localStorage;client.ts 的 apiGet/apiPost/streamSse 统一读取注入
// Authorization: Bearer 头(见 lib/api/client.ts)。

import { apiGet, apiPost } from "./client";

export interface AuthUser {
  id: string;
  email: string;
  role: "user" | "developer" | "admin";
  created_at: string;
  email_verified?: boolean; // M24 P2:未验证账号顶栏横幅提醒
}

export interface LoginResult {
  token: string;
  user: AuthUser;
}

const TOKEN_KEY = "agentplatform_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function broadcastAuthSync(token?: string | null, user?: AuthUser | null): void {
  if (typeof window === "undefined") return;
  const currentToken = token !== undefined ? token : getToken();
  const currentUser = user !== undefined ? user : getUser();
  window.postMessage(
    {
      type: "AGENTPLATFORM_AUTH_SYNC",
      source: "agentplatform-web",
      token: currentToken,
      apiUrl: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api",
      tunnelUrl: "ws://localhost:8000/api/browser/tunnel",
      user: currentUser,
    },
    "*"
  );
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
  broadcastAuthSync(token);
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("agentplatform_user");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function setUser(user: AuthUser | null): void {
  if (typeof window === "undefined") return;
  if (user) localStorage.setItem("agentplatform_user", JSON.stringify(user));
  else localStorage.removeItem("agentplatform_user");
  broadcastAuthSync(undefined, user);
}

export function isAuthed(): boolean {
  return getToken() !== null;
}

export async function register(
  email: string,
  password: string,
  role: "user" | "developer" = "user",
  inviteCode = "",
): Promise<AuthUser> {
  return apiPost<AuthUser>("/auth/register", {
    email,
    password,
    role,
    ...(inviteCode ? { invite_code: inviteCode } : {}),
  });
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const result = await apiPost<LoginResult>("/auth/login", { email, password });
  setToken(result.token);
  setUser(result.user);
  broadcastAuthSync(result.token, result.user);
  return result;
}

export async function me(): Promise<AuthUser> {
  return apiGet<AuthUser>("/auth/me");
}

// M24 P2:邮箱验证(邮件链接中转落地 + 登录态重发)
export async function verifyEmail(token: string): Promise<{ ok: boolean; email?: string }> {
  return apiPost<{ ok: boolean; email?: string }>("/auth/verify-email", { token });
}

export async function resendVerification(): Promise<{ ok: boolean; message?: string }> {
  return apiPost<{ ok: boolean; message?: string }>("/auth/resend-verification", {});
}

export async function logout(): Promise<void> {
  // M24 P2:吊销服务端 refresh 令牌族 + 清 cookie(尽力而为,本地态必清)
  try {
    await fetch(`${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api"}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  } catch {
    // 网络异常时继续清理本地登录态
  }
  setToken(null);
  setUser(null);
  broadcastAuthSync(null, null);
}
