// 登录 / 注册页(M1):登录成功后写 localStorage,跳转聊天页
// M24 P2:飞书扫码登录入口 + 邮箱验证链接落地(verify_token)

"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { setToken, login, me, register, verifyEmail } from "../../lib/api/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"user" | "developer">("user");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // 第三方登录可用性探测(未配置不再裸露 503 JSON,渲染禁用态)
  const [providers, setProviders] = useState<{ github: boolean; feishu: boolean } | null>(null);
  useEffect(() => {
    fetch(`${API_BASE}/auth/providers`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setProviders(d))
      .catch(() => setProviders(null));
  }, []);

  // GitHub/飞书 OAuth 回调:/auth?token=...(M24)——落地登录态后跳首页;
  // 邮箱验证链接:/auth?verify_token=...(M24 P2)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const verifyToken = params.get("verify_token");
    const err = params.get("error");
    if (err) {
      const msg: Record<string, string> = {
        github_denied: "GitHub 授权被拒绝",
        github_no_email: "GitHub 账号未公开邮箱,无法自动建号",
        feishu_denied: "飞书授权被拒绝或已失效",
        feishu_profile: "无法获取飞书用户信息,请重试或联系管理员",
        oauth_state: "登录会话校验失败,请重新发起登录",
        disabled: "账号已被禁用",
      };
      setError(msg[err] ?? "第三方登录失败");
      window.history.replaceState({}, "", "/auth");
    } else if (verifyToken) {
      verifyEmail(verifyToken)
        .then((r) => setNotice(`邮箱 ${r.email ?? ""} 验证成功 ✓`))
        .catch(() => setError("验证链接无效或已过期(24 小时有效),可登录后重发"))
        .finally(() => window.history.replaceState({}, "", "/auth"));
    } else if (token) {
      setToken(token);
      me()
        .then(() => router.push("/"))
        .catch(() => setError("登录态获取失败,请重试"));
    }
  }, [router]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, role, inviteCode);
        await login(email, password);
      }
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h1 className="mb-4 text-center text-lg font-bold">agentplatform</h1>

        <div className="mb-4 flex rounded border border-slate-300 text-sm">
          {(["login", "register"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => {
                setMode(m);
                setError(null);
              }}
              className={`flex-1 py-1.5 ${
                mode === m ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {m === "login" ? "登录" : "注册"}
            </button>
          ))}
        </div>

        <label className="mb-1 block text-sm text-slate-600">邮箱</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mb-3 w-full rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
          placeholder="you@example.com"
        />

        <label className="mb-1 block text-sm text-slate-600">密码</label>
        <input
          type="password"
          required
          minLength={mode === "register" ? 6 : undefined}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mb-3 w-full rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
          placeholder="••••••••"
        />

        {mode === "register" && (
          <>
            <label className="mb-1 block text-sm text-slate-600">邀请码</label>
            <input
              required
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              className="mb-3 w-full rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
              placeholder="向管理员索取(inv-xxxxxxxxxx)"
            />
            <label className="mb-1 block text-sm text-slate-600">角色</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as "user" | "developer")}
              className="mb-3 w-full rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
            >
              <option value="user">用户</option>
              <option value="developer">开发者</option>
            </select>
          </>
        )}

        {error && (
          <p className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-600">
            {error}
          </p>
        )}
        {notice && (
          <p className="mb-3 rounded bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {notice}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded bg-slate-800 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {busy ? "处理中…" : mode === "login" ? "登录" : "注册并登录"}
        </button>

        <div className="my-3 flex items-center gap-2 text-[11px] text-slate-400">
          <span className="h-px flex-1 bg-slate-200" />或<span className="h-px flex-1 bg-slate-200" />
        </div>
        <a
          href={providers?.github ? `${API_BASE}/auth/github` : undefined}
          aria-disabled={!providers?.github}
          className={`flex w-full items-center justify-center gap-2 rounded border border-slate-300 bg-white py-2 text-sm font-medium ${
            providers?.github === false
              ? "cursor-not-allowed opacity-40"
              : "text-slate-700 hover:bg-slate-50"
          }`}
          title={providers?.github === false ? "管理员未配置 GitHub 登录(GITHUB_CLIENT_ID/SECRET)" : undefined}
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden>
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
          </svg>
          使用 GitHub 登录
        </a>
        <a
          href={providers?.feishu ? `${API_BASE}/auth/feishu` : undefined}
          aria-disabled={!providers?.feishu}
          className={`mt-2 flex w-full items-center justify-center gap-2 rounded border border-slate-300 bg-white py-2 text-sm font-medium ${
            providers?.feishu === false
              ? "cursor-not-allowed opacity-40"
              : "text-slate-700 hover:bg-slate-50"
          }`}
          title={providers?.feishu === false ? "管理员未配置飞书机器人(FEISHU_APP_ID/SECRET)" : undefined}
        >
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden>
            <path d="M3.8 5.1 12 0l8.2 5.1-2 3.2L12 4.3l-6.2 4 4.6 2.9-1.9 3.1-6.6-4.2a1.3 1.3 0 0 1 0-2.2l1.9-1.2-1.9-1.6Zm1 8.4 5 3.2v3.1c0 .9 1 1.4 1.7.9L12 20l.5.7c.7.5 1.7 0 1.7-.9v-3.1l5-3.2 1.6 2.5L12 24l-8.8-8 1.6-2.5Zm10.3-6.6-2 3.2 6.2 4-2 3.2L20.2 5.1 15.1 0l-2 3.2 2 3.7Z" />
          </svg>
          飞书扫码登录
        </a>
        <p className="mt-2 text-center text-[11px] text-slate-400">
          {providers && !providers.github && !providers.feishu
            ? "第三方登录均未配置——使用邮箱邀请码注册"
            : "GitHub / 飞书登录免邀请码;同邮箱账号自动绑定"}
        </p>
      </form>
    </main>
  );
}
