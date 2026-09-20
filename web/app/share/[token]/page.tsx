"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "../../../components/layout/Navbar";

interface SharedMsg {
  role: string;
  text: string;
  blocks: any[];
}

export default function SharedConversation() {
  const [data, setData] = useState<{ title: string; created_at: string; messages: SharedMsg[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = window.location.pathname.split("/").pop();
    (async () => {
      try {
        const resp = await fetch(`${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api"}/chat/shared/${token}`);
        if (!resp.ok) throw new Error((await resp.json())?.error?.message || "分享不存在或已过期");
        setData(await resp.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    })();
  }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <div className="mx-auto max-w-3xl px-4 py-8">
        {error && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-8 text-center text-sm text-rose-700">
            🔗 {error}
          </div>
        )}
        {data && (
          <>
            <div className="mb-6">
              <h1 className="text-lg font-bold text-slate-900">{data.title}</h1>
              <p className="mt-1 text-xs text-slate-400">
                只读分享 · 创建于 {new Date(data.created_at).toLocaleString("zh-CN")}
              </p>
            </div>
            <div className="space-y-3">
              {data.messages.map((m, i) => (
                <div
                  key={i}
                  className={`rounded-2xl p-4 ${
                    m.role === "user"
                      ? "bg-indigo-50 border border-indigo-100"
                      : "bg-white border border-slate-200"
                  }`}
                >
                  <div className="mb-1 text-[10px] font-medium text-slate-400">
                    {m.role === "user" ? "👤 用户" : "🤖 助手"}
                  </div>
                  <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{m.text}</div>
                </div>
              ))}
            </div>
          </>
        )}
        {!data && !error && <div className="py-16 text-center text-sm text-slate-400">加载分享内容...</div>}
      </div>
    </div>
  );
}
