"use client";

import React, { useEffect, useState } from "react";

/** 我的待办(M14 P1,需求 007 U8):纯本地 localStorage,不产生后端写请求。
 *  数据不作为业务权威——将来跨设备需求出现时迁云端表,迁移无历史包袱。 */

const STORAGE_KEY = "workbench_todos";

interface Todo {
  id: string;
  text: string;
  done: boolean;
  created_at: string;
}

function load(): Todo[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const list = raw ? (JSON.parse(raw) as Todo[]) : [];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function save(list: Todo[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
}

export function TodoCard() {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [draft, setDraft] = useState("");
  const [showDone, setShowDone] = useState(false);

  useEffect(() => setTodos(load()), []);

  const update = (next: Todo[]) => {
    setTodos(next);
    save(next);
  };

  const add = () => {
    const text = draft.trim();
    if (!text) return;
    update([
      { id: `t-${Date.now()}`, text, done: false, created_at: new Date().toISOString() },
      ...todos,
    ]);
    setDraft("");
  };

  const toggle = (id: string) =>
    update(todos.map((t) => (t.id === id ? { ...t, done: !t.done } : t)));

  const remove = (id: string) => update(todos.filter((t) => t.id !== id));

  const clearDone = () => update(todos.filter((t) => !t.done));

  const open = todos.filter((t) => !t.done);
  const done = todos.filter((t) => t.done);
  const visible = showDone ? done.slice(0, 10) : open.slice(0, 8);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-xs">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <span className="text-xs font-bold text-slate-900">
          ✅ 我的待办
          <span className="ml-2 text-[10px] font-normal text-slate-400">
            {open.length > 0 ? `${open.length} 项未完成` : "全部完成"}·仅存本机
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
        <div className="mb-2 flex gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="添加待办,回车确认"
            className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs outline-none focus:border-indigo-400"
          />
          <button
            type="button"
            onClick={add}
            disabled={!draft.trim()}
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-40"
          >
            添加
          </button>
        </div>

        {visible.length === 0 ? (
          <div className="py-4 text-center text-[11px] text-slate-400">
            {showDone ? "暂无已完成" : "没有待办,添加一条开始今天"}
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
                  onChange={() => toggle(t.id)}
                  className="h-3.5 w-3.5 accent-indigo-600"
                />
                <span className={`flex-1 truncate text-xs ${t.done ? "text-slate-400 line-through" : "text-slate-700"}`}>
                  {t.text}
                </span>
                <button
                  type="button"
                  onClick={() => remove(t.id)}
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
                onClick={clearDone}
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
