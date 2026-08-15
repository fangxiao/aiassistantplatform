"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Navbar } from "../../components/layout/Navbar";
import { apiGet, apiPost } from "../../lib/api/client";
import { isAuthed } from "../../lib/api/auth";
import type { AssistantInfo, SessionInfo } from "../../lib/types";

export default function AssistantsPage() {
  const router = useRouter();
  const [assistants, setAssistants] = useState<AssistantInfo[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthed()) {
      router.push("/auth");
      return;
    }

    const loadAssistants = async () => {
      try {
        setLoading(true);
        const list = await apiGet<AssistantInfo[]>("/assistants");
        setAssistants(list);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    };
    loadAssistants();
  }, [router]);

  const handleStartChat = async (assistant: AssistantInfo) => {
    try {
      const session = await apiPost<SessionInfo>("/chat/sessions", {
        plugin_id: assistant.id,
      });
      router.push(`/?sessionId=${session.id}`);
    } catch (err) {
      alert(`创建会话失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const filtered = assistants.filter((a) => {
    const q = search.toLowerCase();
    return (
      a.name.toLowerCase().includes(q) ||
      (a.description && a.description.toLowerCase().includes(q))
    );
  });

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Navbar />

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
            🧩 助手广场 (Assistant Marketplace)
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            浏览与选用由平台开发者部署的专属领域智能体，即开即用。
          </p>

          <div className="mt-5 max-w-md">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索智能体名称或功能描述..."
              className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs text-slate-800 shadow-xs focus:border-slate-500 focus:outline-none"
            />
          </div>
        </div>

        {error && (
          <div className="mb-6 rounded-lg bg-red-50 p-4 text-xs text-red-600 border border-red-200">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex h-48 items-center justify-center text-xs text-slate-400">
            加载智能体市场中...
          </div>
        ) : filtered.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 bg-white p-12 text-center text-xs text-slate-400">
            <p className="text-3xl mb-2">🔍</p>
            <p className="font-medium text-slate-600">未找到匹配的智能体</p>
            <p className="mt-1">您可以前往「开发者中心」或使用 CLI 部署新插件助手。</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((item) => (
              <div
                key={item.id}
                className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-xs transition hover:shadow-md hover:border-slate-300"
              >
                <div>
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 text-lg font-bold">
                        🤖
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-slate-900">{item.name}</h3>
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">
                          v{item.version}
                        </span>
                      </div>
                    </div>
                    {item.model && (
                      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700 border border-emerald-100">
                        {item.model}
                      </span>
                    )}
                  </div>

                  <p className="mt-3 text-xs leading-relaxed text-slate-600 line-clamp-3">
                    {item.description || "暂无描述"}
                  </p>

                  {item.depends_on && item.depends_on.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1">
                      {item.depends_on.map((dep, idx) => (
                        <span
                          key={idx}
                          className="rounded bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-500 border border-slate-100 font-mono"
                        >
                          {dep}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-3 text-xs text-slate-400">
                  <span>作者: {item.author || "官方平台"}</span>
                  <button
                    type="button"
                    onClick={() => handleStartChat(item)}
                    className="rounded-lg bg-slate-900 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-slate-800 transition"
                  >
                    开始对话 →
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
