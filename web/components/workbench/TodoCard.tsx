"use client";

import React, { useCallback, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost } from "../../lib/api/client";

/** 我的待办(M14 P1.5 云端化,需求 007 U8 v0.2):
 *  权威存储为平台 workbench_todos 表——AI 经 tool:workbench_todo 与本卡共写同一份数据,
 *  跨设备同步。旧 localStorage 数据在首次加载时一次性迁移到云端。 */

const LEGACY_KEY = "workbench_todos";
const MIGRATED_KEY = "workbench_todos_migrated";

interface Todo {
  id: string;
  text: string;
  done: boolean;
  origin: string;
  created_at: string | null;
  done_at: string | null;
}

export function TodoCard() {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [draft, setDraft] = useState("");
  const [showDone, setShowDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setTodos(await apiGet<Todo[]>("/workbench/todos"));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      await refresh();
      // 一次性迁移:本地旧数据存在且未迁移过 → 导入云端后清掉本地
      try {
        const legacy = localStorage.getItem(LEGACY_KEY);
        if (legacy && !localStorage.getItem(MIGRATED_KEY)) {
          const items = JSON.parse(legacy) as { text: string; done: boolean }[];
          const texts = (Array.isArray(items) ? items : [])
            .filter((t) => t?.text?.trim())
            .map((t) => t.text);
          if (texts.length > 0) {
            await apiPost("/workbench/todos/import", texts);
          }
          localStorage.setItem(MIGRATED_KEY, "1");
          localStorage.removeItem(LEGACY_KEY);
          await refresh();
        }
      } catch {
        /* 迁移失败不影响主流程,下次再试 */
      }
    })();
  }, [refresh]);

  const add = async () => {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    try {
      await apiPost("/workbench/todos", { text });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const toggle = async (t: Todo) => {
    // 乐观更新,失败回滚由 refresh 兜底
    setTodos((prev) => prev.map((x) => (x.id === t.id ? { ...x, done: !x.done } : x)));
    try {
      await apiPatch(`/workbench/todos/${t.id}`, { done: !t.done });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      await refresh();
    }
  };

  const remove = async (id: string) => {
    try {
      await apiDelete(`/workbench/todos/${id}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const clearDone = async () => {
    try {
      await apiDelete("/workbench/todos/completed");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const open = todos.filter((t) => !t.done);
  const done = todos.filter((t) => t.done);
  const visible = showDone ? done.slice(0, 10) : open.slice(0, 8);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-xs">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <span className="text-xs font-bold text-slate-900">
          ✅ 我的待办
          <span className="ml-2 text-[10px] font-normal text-slate-400">
            {open.length > 0 ? `${open.length} 项未完成` : "全部完成"}·云端同步,助手也可帮你记
          </span>
        </span>
        {done.length > 0 && (
          <button
            type="button"
            onClick={() => setShowDone((v) => !v)}
            className="text-[11px] font-medium text-indigo-600 hover:text-indigo-700"
          >
            {showDone ? "看未完成" : `看已完成(${done.length})`}
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
            placeholder="添加待办,回车确认"
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

        {loading && todos.length === 0 ? (
          <div className="py-4 text-center text-[11px] text-slate-400">加载待办...</div>
        ) : visible.length === 0 ? (
          <div className="py-4 text-center text-[11px] text-slate-400">
            {showDone ? "暂无已完成" : "没有待办;也可以在对话里让助手帮你记"}
          </div>
        ) : (
          <div className="space-y-1">
            {visible.map((t) => (
              <div
                key={t.id}
                className="group flex items-center gap-2 rounded-lg px-2 py-1.5 transition hover:bg-slate-50"
              >
                <input
                  type="checkbox"
                  checked={t.done}
                  onChange={() => void toggle(t)}
                  className="h-3.5 w-3.5 accent-indigo-600"
                />
                <span className={`flex-1 truncate text-xs ${t.done ? "text-slate-400 line-through" : "text-slate-700"}`}>
                  {t.text}
                  {t.origin === "ai" && (
                    <span className="ml-1.5 rounded bg-violet-50 border border-violet-200 px-1 py-0.5 text-[9px] font-medium text-violet-700" title="由助手在对话中记录">
                      AI
                    </span>
                  )}
                </span>
                <button
                  type="button"
                  onClick={() => void remove(t.id)}
                  className="shrink-0 text-[10px] text-slate-300 opacity-0 transition group-hover:opacity-100 hover:text-rose-500"
                  title="删除"
                >
                  ✕
                </button>
              </div>
            ))}
            {showDone && done.length > 0 && (
              <button
                type="button"
                onClick={() => void clearDone()}
                className="mt-1 text-[10px] text-slate-400 hover:text-rose-500"
              >
                清空已完成
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
