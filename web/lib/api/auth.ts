// 认证 API 封装(M1):注册/登录/当前用户 + token 存取
//
// token 存 localStorage;client.ts 的 apiGet/apiPost/streamSse 统一读取注入
// Authorization: Bearer 头(见 lib/api/client.ts)。

import { apiGet, apiPost } from "./client";

export interface AuthUser {
  id: string;
  email: string;
  role: "user" | "developer";
  created_at: string;
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

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
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
}

export function isAuthed(): boolean {
  return getToken() !== null;
}

export async function register(
  email: string,
  password: string,
  role: "user" | "developer" = "user",
): Promise<AuthUser> {
  return apiPost<AuthUser>("/auth/register", { email, password, role });
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const result = await apiPost<LoginResult>("/auth/login", { email, password });
  setToken(result.token);
  setUser(result.user);
  return result;
}

export async function me(): Promise<AuthUser> {
  return apiGet<AuthUser>("/auth/me");
}

export function logout(): void {
  setToken(null);
  setUser(null);
}
