"use client";

import { useState } from "react";
import { apiPatch } from "../../lib/api/client";
import { getUser, setUser } from "../../lib/api/auth";

/** 角色画像选择(M37):登录后首次弹出,控制工作台卡片;可多选。 */

const OPTIONS = [
  { id: "student", icon: "🎓", label: "学生", desc: "学习进度、错题复习、每日打卡" },
  { id: "parent", icon: "👨‍👩‍👧", label: "家长", desc: "学习日报、任务管理、全局视图" },
  { id: "developer", icon: "🧑‍💻", label: "开发者", desc: "完整工作台、插件开发、知识库管理" },
];

export function PersonaSelect({ onDone }: { onDone: () => void }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const save = async () => {
    if (selected.size === 0) return; // 不选 = general(通用)
    setBusy(true);
    try {
      await apiPatch("/auth/me/personas", { personas: Array.from(selected) });
      const u = getUser();
      if (u) {
        const updated = { ...u, personas: Array.from(selected) };
        setUser(updated);
      }
    } catch {
      // 保存失败不阻断,下次可再改
    } finally {
      setBusy(false);
      onDone();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <h2 className="text-center text-base font-bold text-slate-900">选择你的角色</h2>
        <p className="mt-1 text-center text-xs text-slate-500">
          我们会根据角色定制你的工作台(可多选,之后随时改)
        </p>
        <div className="mt-4 space-y-2">
          {OPTIONS.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => toggle(o.id)}
              className={`flex w-full items-center gap-3 rounded-xl border-2 px-4 py-3 text-left transition ${
                selected.has(o.id)
                  ? "border-indigo-500 bg-indigo-50"
                  : "border-slate-200 bg-white hover:border-slate-300"
              }`}
            >
              <span className="text-2xl">{o.icon}</span>
              <span className="flex-1">
                <span className="block text-sm font-semibold text-slate-800">{o.label}</span>
                <span className="block text-[11px] text-slate-500">{o.desc}</span>
              </span>
              {selected.has(o.id) && <span className="text-indigo-600">✓</span>}
            </button>
          ))}
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void save()}
          className="mt-4 w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {busy ? "保存中…" : selected.size > 0 ? `进入我的工作台(${selected.size} 个角色)` : "使用通用工作台"}
        </button>
      </div>
    </div>
  );
}
