"use client";

import React, { useEffect, useState } from "react";
import { listKbs } from "../../lib/api/kb";
import type { KbInfo } from "../../lib/types";

interface KbMountModalProps {
  sessionId: string;
  currentKbIds: string[];
  onClose: () => void;
  onSave: (kbIds: string[]) => Promise<void>;
}

/** 会话挂载知识库选择器 (M12, T12.13):勾选当前用户可见的库,PATCH 会话 mounted_kb_ids。 */
export function KbMountModal({ sessionId, currentKbIds, onClose, onSave }: KbMountModalProps) {
  const [kbs, setKbs] = useState<KbInfo[]>([]);
  const [checked, setChecked] = useState<Set<string>>(new Set(currentKbIds));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const list = await listKbs();
        setKbs(list);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionId]);

  const toggle = (id: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // 仅保留仍然可见的库,避免挂载已不可读的库
      const visibleIds = new Set(kbs.map((k) => k.id));
      const nextIds = Array.from(checked).filter((id) => visibleIds.has(id));
      await onSave(nextIds);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <span className="text-xl">📚</span>
            <div>
              <h3 className="font-bold text-sm text-slate-900">挂载知识库</h3>
              <p className="text-[11px] text-slate-400">挂载后智能体可在对话中检索库内资料</p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600 text-sm">
            ✕
          </button>
        </div>

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-2.5 text-[11px] text-red-700">⚠️ {error}</div>
        )}

        <div className="max-h-72 overflow-y-auto space-y-1.5">
          {loading ? (
            <div className="py-8 text-center text-xs text-slate-400">加载知识库列表...</div>
          ) : kbs.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-400">
              暂无可用知识库，请先前往「知识库」页面创建
            </div>
          ) : (
            kbs.map((kb) => {
              const isChecked = checked.has(kb.id);
              const isReady = kb.chunk_count > 0;
              return (
                <label
                  key={kb.id}
                  className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition ${
                    isChecked ? "border-indigo-300 bg-indigo-50/70" : "border-slate-200 bg-white hover:bg-slate-50"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => toggle(kb.id)}
                    className="h-4 w-4 shrink-0 accent-indigo-600"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm shrink-0">{kb.visibility === "public" ? "🌐" : kb.visibility === "shared" ? "👥" : "🔒"}</span>
                      <span className="truncate text-xs font-bold text-slate-900">{kb.name}</span>
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[9px] text-slate-500">
                        v{kb.version}
                      </span>
                    </div>
                    <div className="mt-0.5 text-[10px] text-slate-400">
                      🧩 {kb.chunk_count} 片段
                      {!isReady && <span className="ml-1 text-amber-600">· 尚无可用片段，检索将无结果</span>}
                    </div>
                  </div>
                </label>
              );
            })
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-200"
          >
            取消
          </button>
          <button
            type="button"
            disabled={saving || loading}
            onClick={() => void handleSave()}
            className="rounded-md bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {saving ? "保存中..." : "保存挂载"}
          </button>
        </div>
      </div>
    </div>
  );
}
