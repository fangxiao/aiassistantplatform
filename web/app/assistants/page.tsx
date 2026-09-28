"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Navbar } from "../../components/layout/Navbar";
import { apiFetch, apiGet, apiPost } from "../../lib/api/client";
import { isAuthed } from "../../lib/api/auth";
import type { AssistantInfo, SessionInfo } from "../../lib/types";

export default function AssistantsPage() {
  const router = useRouter();
  const [assistants, setAssistants] = useState<AssistantInfo[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // T18.20 助手独立运营:访问链接发布 + 使用统计
  const [opsTarget, setOpsTarget] = useState<{ assistant: AssistantInfo; url: string; stats?: Record<string, unknown> } | null>(null);
  const [opsBusy, setOpsBusy] = useState(false);

  const resubmit = async (assistant: AssistantInfo) => {
    try {
      setOpsBusy(true);
      await apiFetch(`/plugins/${assistant.id}/resubmit`, { method: "POST" });
      setAssistants((prev) =>
        prev.map((a) => (a.id === assistant.id ? { ...a, review_status: "pending_review", last_review_reason: null } : a)),
      );
    } catch (err) {
      alert(`重新提交失败: ${err instanceof Error ? err.message : err}`);
    } finally {
      setOpsBusy(false);
    }
  };

  const publishAccess = async (assistant: AssistantInfo) => {
    try {
      setOpsBusy(true);
      const r = await apiFetch<{ url: string }>(`/assistant-access/plugins/${assistant.id}/publish`, { method: "POST" });
      const stats = await apiFetch<Record<string, unknown>>(`/assistant-access/plugins/${assistant.id}/stats`).catch(() => undefined);
      setOpsTarget({ assistant, url: `${window.location.origin}${r.url}`, stats });
    } catch (err) {
      alert(`发布失败: ${err instanceof Error ? err.message : err}`);
    } finally {
      setOpsBusy(false);
    }
  };

  const refreshStats = async () => {
    if (!opsTarget) return;
    try {
      const stats = await apiFetch<Record<string, unknown>>(`/assistant-access/plugins/${opsTarget.assistant.id}/stats`);
      setOpsTarget({ ...opsTarget, stats });
    } catch { /* 保持旧值 */ }
  };

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
      (a.display_name && a.display_name.toLowerCase().includes(q)) ||
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
                        <h3 className="text-sm font-bold text-slate-900">
                          {item.display_name || item.name}
                        </h3>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <span className="font-mono text-[10px] text-slate-400">
                            {item.name}
                          </span>
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">
                            v{item.version}
                          </span>
                          {item.review_status === "pending_review" && (
                            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 border border-amber-200">
                              待审核
                            </span>
                          )}
                          {item.review_status === "rejected" && (
                            <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-medium text-rose-700 border border-rose-200">
                              已驳回
                            </span>
                          )}
                        </div>
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

                  {item.review_status === "rejected" && item.last_review_reason && (
                    <p className="mt-2 rounded-lg bg-rose-50 border border-rose-100 px-2.5 py-1.5 text-[10px] text-rose-700">
                      驳回原因:{item.last_review_reason}
                    </p>
                  )}

                  {item.review_status === "pending_review" && (
                    <p className="mt-2 rounded-lg bg-amber-50 border border-amber-100 px-2.5 py-1.5 text-[10px] text-amber-700">
                      审核通过前仅自己与管理员可见
                    </p>
                  )}

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
                  <div className="flex items-center gap-2">
                    {item.review_status === "rejected" && (
                      <button
                        type="button"
                        onClick={() => void resubmit(item)}
                        disabled={opsBusy}
                        title="按驳回原因修改后重新提交审核"
                        className="rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[11px] font-medium text-rose-600 hover:bg-rose-100 transition disabled:opacity-40"
                      >
                        ↻ 重新提交
                      </button>
                    )}
                    {item.review_status === "approved" && (
                      <button
                        type="button"
                        onClick={() => void publishAccess(item)}
                        disabled={opsBusy}
                        title="生成独立访问链接(给你的用户直接使用)"
                        className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-medium text-slate-600 hover:border-indigo-300 hover:text-indigo-600 transition disabled:opacity-40"
                      >
                        🔗 独立链接
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => handleStartChat(item)}
                      className="rounded-lg bg-slate-900 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-slate-800 transition"
                    >
                      开始对话 →
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      {opsTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setOpsTarget(null)}>
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-bold text-slate-800">🔗 {opsTarget.assistant.display_name || opsTarget.assistant.name} · 独立运营</h3>
            <div className="mt-3 rounded-xl bg-slate-50 p-3">
              <div className="text-[11px] text-slate-400">访问链接(发给你的用户,打开即是纯聊天页)</div>
              <div className="mt-1 flex items-center gap-2">
                <code className="flex-1 truncate rounded bg-white px-2 py-1.5 font-mono text-[11px] text-slate-700">{opsTarget.url}</code>
                <button
                  type="button"
                  onClick={() => { void navigator.clipboard.writeText(opsTarget.url); alert("已复制"); }}
                  className="rounded-lg bg-slate-900 px-2.5 py-1.5 text-[11px] font-medium text-white"
                >
                  复制
                </button>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-4 gap-2 text-center">
              {[
                ["用户", String(opsTarget.stats?.users ?? "–")], ["会话", String(opsTarget.stats?.sessions ?? "–")],
                ["消息", String(opsTarget.stats?.messages ?? "–")], ["Tokens", String(opsTarget.stats?.tokens ?? "–")],
              ].map(([label, v]) => (
                <div key={String(label)} className="rounded-xl border border-slate-100 py-2.5">
                  <div className="text-lg font-bold text-slate-800">{v ?? "–"}</div>
                  <div className="text-[10px] text-slate-400">{label}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex justify-between">
              <button type="button" onClick={() => void refreshStats()} className="text-[11px] text-slate-400 hover:text-slate-600">刷新统计</button>
              <button type="button" onClick={() => setOpsTarget(null)} className="rounded-lg bg-slate-900 px-4 py-1.5 text-xs font-medium text-white">完成</button>
            </div>
          </div>
        </div>
      )}
      </main>
    </div>
  );
}
