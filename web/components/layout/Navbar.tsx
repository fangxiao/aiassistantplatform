"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AuthUser, broadcastAuthSync, getUser, isAuthed, logout } from "../../lib/api/auth";
import { NotificationBell } from "../workbench/NotificationBell";

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUserState] = useState<AuthUser | null>(null);
  const [authed, setAuthed] = useState<boolean>(false);

  useEffect(() => {
    setUserState(getUser());
    setAuthed(isAuthed());
    broadcastAuthSync();

    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === "AGENTPLATFORM_AUTH_QUERY") {
        broadcastAuthSync();
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [pathname]);

  const handleLogout = () => {
    logout();
    setAuthed(false);
    setUserState(null);
    router.push("/auth");
  };

  const navLinks = [
    { href: "/", label: "💬 对话工作台" },
    { href: "/assistants", label: "🧩 助手广场" },
    { href: "/kb", label: "📚 知识库" },
    { href: "/developer", label: "🛠️ 开发者中心" },
    { href: "/status", label: "🩺 系统诊断" },
  ];

  const [showTokenModal, setShowTokenModal] = useState(false);
  const [copied, setCopied] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const handleCopyToken = () => {
    const token = typeof window !== "undefined" ? localStorage.getItem("agentplatform_token") : "";
    if (token) {
      navigator.clipboard.writeText(token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-sm font-bold text-white shadow-xs">
              🤖
            </span>
            <span className="font-bold tracking-tight text-slate-900 text-base">
              AgentPlatform
            </span>
          </Link>

          <nav className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => {
              const active = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                    active
                      ? "bg-slate-100 text-slate-900 font-semibold"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
          {/* 移动端汉堡菜单 */}
          <button
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            className="md:hidden rounded-md p-2 text-slate-600 hover:bg-slate-100"
            aria-label="菜单"
          >
            {menuOpen ? "✕" : "☰"}
          </button>
        </div>

        <div className="flex items-center gap-3">
          {authed && user ? (
            <div className="flex items-center gap-2">
              <NotificationBell />
              <button
                type="button"
                onClick={() => setShowTokenModal(true)}
                className="flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100 transition shadow-2xs"
                title="查看与复制 BrowserAgent 插件连接 Token"
              >
                <span>🔌</span>
                <span>插件连接</span>
              </button>

              <div className="hidden sm:flex flex-col text-right text-xs">
                <span className="font-medium text-slate-800">{user.email}</span>
                <span className="text-[10px] text-slate-400 capitalize">
                  {user.role === "developer" ? "开发者" : "普通用户"}
                </span>
              </div>
              <button
                type="button"
                onClick={handleLogout}
                className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 transition"
              >
                退出
              </button>
            </div>
          ) : (
            <Link
              href="/auth"
              className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800 transition"
            >
              登录 / 注册
            </Link>
          )}
        </div>
      </div>

      {/* BrowserAgent 连接 Token 弹窗 */}
      {showTokenModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-xl">🔌</span>
                <h3 className="font-bold text-sm text-slate-900">BrowserAgent 扩展直连配置</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowTokenModal(false)}
                className="text-slate-400 hover:text-slate-600 text-sm"
              >
                ✕
              </button>
            </div>

            <div className="text-xs text-slate-600 space-y-3">
              <p>
                如果 Chrome 扩展端侧直连显示 <strong className="text-rose-600">红色（未连接）</strong>，是因为 Token 已过期或未配置。
              </p>

              <div>
                <label className="block font-semibold text-slate-800 mb-1">你的当前认证 Token：</label>
                <div className="relative">
                  <input
                    type="text"
                    readOnly
                    value={typeof window !== "undefined" ? (localStorage.getItem("agentplatform_token") || "未登录") : ""}
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 p-2.5 font-mono text-[11px] text-slate-700 pr-20"
                  />
                  <button
                    type="button"
                    onClick={handleCopyToken}
                    className="absolute right-1.5 top-1.5 rounded-md bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700 transition"
                  >
                    {copied ? "已复制 ✓" : "复制"}
                  </button>
                </div>
              </div>

              <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-[11px] text-amber-900 space-y-1">
                <div className="font-bold">📋 配置步骤：</div>
                <ol className="list-decimal list-inside space-y-0.5 text-amber-800">
                  <li>打开 Chrome 浏览器中的 <strong>BrowserAgent 扩展</strong> 图标或设置页；</li>
                  <li>将平台地址设为 <code>ws://localhost:8000/api/browser/tunnel</code>；</li>
                  <li>将上方复制的 <strong>Token</strong> 粘贴并保存；</li>
                  <li>状态即刻变为 🟢 <strong>已连接（绿色）</strong>。</li>
                </ol>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setShowTokenModal(false)}
                className="rounded-lg bg-slate-900 px-4 py-2 text-xs font-medium text-white hover:bg-slate-800 transition"
              >
                我知道了
              </button>
            </div>
          </div>
        </div>
      )}
    
      {/* 移动端导航下拉 */}
      {menuOpen && (
        <nav className="md:hidden border-t border-slate-100 bg-white px-4 py-2">
          {navLinks.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className={`block rounded-md px-3 py-2.5 text-sm font-medium transition ${
                  active ? "bg-slate-100 text-slate-900 font-semibold" : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      )}</header>
  );
}
