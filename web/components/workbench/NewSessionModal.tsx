"use client";

import React, { useMemo, useState } from "react";
import type { AssistantInfo } from "../../lib/types";

/** 新会话助手选择器(M14,设计 010 交互修订):
 *  "新会话"是选择意图而非制造记录——取消不创建任何会话。 */

interface Props {
  assistants: AssistantInfo[];
  onPick: (assistantId: string | null) => void;
  onClose: () => void;
}

export function NewSessionModal({ assistants, onPick, onClose }: Props) {
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    if (!q.trim()) return assistants;
    const kw = q.trim().toLowerCase();
    return assistants.filter(
      (a) =>
        (a.display_name || a.name).toLowerCase().includes(kw) ||
        a.name.toLowerCase().includes(kw) ||
        (a.description || "").toLowerCase().includes(kw)
    );
  }, [assistants, q]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
      <div className="w-full max-w-lg space-y-4 rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div>
            <h3 className="text-sm font-bold text-slate-900">💬 开始新对话</h3>
            <p className="text-[11px] text-slate-400">选择一个助手;通用助手适合问知识库与日常问答</p>
          </div>
          <button type="button" onClick={onClose} className="text-sm text-slate-400 hover:text-slate-600">
            ✕
          </button>
        </div>

        {/* 平台通用助手(固定首项) */}
        <button
          type="button"
          onClick={() => onPick(null)}
          className="flex w-full items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 text-left transition hover:border-indigo-300 hover:bg-indigo-50/60"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-base">✨</span>
          <span className="min-w-0 flex-1">
            <span className="block text-xs font-bold text-slate-900">平台通用助手</span>
            <span className="block truncate text-[10px] text-slate-400">
              无插件;可检索你挂载的知识库、记录待办
            </span>
          </span>
          <span className="shrink-0 text-[10px] text-slate-300">→</span>
        </button>

        {assistants.length > 3 && (
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜索助手..."
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
          />
        )}

        {assistants.length === 0 ? (
          <div className="py-4 text-center text-[11px] text-slate-400">
            暂无已部署助手;开发者可在工作台部署插件
          </div>
        ) : (
          <div className="max-h-64 space-y-2 overflow-y-auto">
            {filtered.map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => onPick(a.id)}
                className="flex w-full items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 text-left transition hover:border-indigo-300 hover:bg-indigo-50/60"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-base">🤖</span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    <span className="truncate text-xs font-bold text-slate-900">
                      {a.display_name || a.name}
                    </span>
                    {(a.mounted_kb_ids?.length ?? 0) > 0 && (
                      <span className="shrink-0 rounded bg-emerald-50 border border-emerald-200 px-1 py-0.5 text-[9px] font-medium text-emerald-700">
                        📚{a.mounted_kb_ids!.length}
                      </span>
                    )}
                  </span>
                  <span className="block truncate text-[10px] text-slate-400">
                    {a.description || a.name}
                  </span>
                </span>
                <span className="shrink-0 text-[10px] text-slate-300">→</span>
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="py-4 text-center text-[11px] text-slate-400">没有匹配的助手</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
