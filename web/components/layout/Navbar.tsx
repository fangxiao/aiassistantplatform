"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AuthUser, getUser, isAuthed, logout } from "../../lib/api/auth";

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUserState] = useState<AuthUser | null>(null);
  const [authed, setAuthed] = useState<boolean>(false);

  useEffect(() => {
    setUserState(getUser());
    setAuthed(isAuthed());
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
    { href: "/developer", label: "🛠️ 开发者中心" },
  ];

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
        </div>

        <div className="flex items-center gap-3">
          {authed && user ? (
            <div className="flex items-center gap-3">
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
                退出登录
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
    </header>
  );
}
