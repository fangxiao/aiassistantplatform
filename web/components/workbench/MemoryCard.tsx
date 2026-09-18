"use client";

import React, { useCallback, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost } from "../../lib/api/client";
import { Card, Placeholder } from "./WorkbenchView";

/** 🧠 记忆管理卡(打磨①):助手记住的用户偏好/事实——可见、可删、可清空。
 *  透明度是记忆系统的必备件:AI 记错了要能纠正,不想记的要能删。 */

interface MemoryItem {
  id: string;
  content: string;
  created_at: string | null;
}

export function MemoryCard() {
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const refresh = useCallback(async () => {
    try {
      setItems(await apiGet<MemoryItem[]>("/memory/memories"));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const add = async () => {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    try {
      await apiPost("/memory/memories", { content: text });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const remove = async (id: string) => {
    try {
      await apiDelete(`/memory/memories/${id}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const clearAll = async () => {
    if (!confirm("清空全部记忆?助手将不再记得这些内容。")) return;
    try {
      await apiDelete("/memory/memories");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-xs">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <span className="text-xs font-bold text-slate-900">
          🧠 助手的记忆
          <span className="ml-2 text-[10px] font-normal text-slate-400">
            {items.length > 0 ? `${items.length} 条` : "暂无"}·对话中说"记住…"也会存到这里
          </span>
        </span>
        {items.length > 0 && (
          <button
            type="button"
            onClick={() => void clearAll()}
            className="text-[11px] font-medium text-rose-500 hover:text-rose-600"
          >
            清空
          </button>
        )}
      </div>

      <div className="p-3">
        {error && (
          <div className="mb-2 rounded-lg bg-red-50 border border-red-200 p-2 text-[10px] text-red-700">⚠️ {error}</div>
        )}

        <div className="mb-2 flex gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void add()}
            placeholder="手动添加一条记忆,如:回答用中文"
            className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs outline-none focus:border-indigo-400"
          />
          <button
            type="button"
            onClick={() => void add()}
            disabled={!draft.trim()}
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-40"
          >
            添加
          </button>
        </div>

        {loading && items.length === 0 ? (
          <Placeholder text="加载记忆..." />
        ) : items.length === 0 ? (
          <Placeholder text="助手还没有记住任何内容" />
        ) : (
          <div className="max-h-52 space-y-1 overflow-y-auto">
            {items.map((m) => (
              <div key={m.id} className="group flex items-center gap-2 rounded-lg px-2 py-1.5 transition hover:bg-slate-50">
                <span className="flex-1 truncate text-xs text-slate-700">{m.content}</span>
                <button
                  type="button"
                  onClick={() => void remove(m.id)}
                  className="shrink-0 text-[10px] text-slate-300 opacity-0 transition group-hover:opacity-100 hover:text-rose-500"
                  title="遗忘"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
