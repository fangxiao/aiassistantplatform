"use client";

import React, { useCallback, useEffect, useState } from "react";
import { apiGet } from "../../lib/api/client";
import { Card } from "./WorkbenchView";

/** 会话中心(20261010 v4):所有会话统一列表(定时+手动),点击进会话。
 *  来源列区分手动/定时;运行中的定时会话带 spinner。 */

interface SessionRow {
  session_id: string;
  title: string;
  source: "manual" | "scheduled";
  last_active: string;
  artifact_count: number;
  running: boolean;
  next_run_at: string | null;
}

interface Panel {
  sessions: SessionRow[];
}

const SPIN = (
  <svg className="h-3 w-3 animate-spin text-indigo-500" viewBox="0 0 24 24" fill="none" aria-hidden>
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
  </svg>
);

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${mm}/${dd} ${hh}:${mi}`;
}

export function TasksCard({
  onContinue,
}: {
  onContinue: (sessionId: string) => void;
  onSaveToKb: (c: string) => void;
}) {
  const [panel, setPanel] = useState<Panel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setPanel(await apiGet<Panel>("/workbench/tasks"));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 30_000);
    const onChanged = () => void refresh();
    window.addEventListener("ap:tasks-changed", onChanged);
    return () => {
      clearInterval(timer);
      window.removeEventListener("ap:tasks-changed", onChanged);
    };
  }, [refresh]);

  return (
    <Card title="💬 会话中心">
      {loading && <p className="py-2 text-center text-xs text-slate-400">加载中…</p>}
      {error && <p className="py-2 text-center text-xs text-rose-500">{error}</p>}
      {panel && (
        <div>
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                <th className="px-2 py-1.5 font-semibold">会话</th>
                <th className="w-12 px-1 py-1.5 font-semibold">来源</th>
                <th className="w-28 px-1 py-1.5 font-semibold">最后活跃</th>
                <th className="w-12 px-1 py-1.5 text-right font-semibold">交付物</th>
              </tr>
            </thead>
            <tbody>
              {panel.sessions.map((s) => (
                <tr key={s.session_id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50">
                  <td className="px-2 py-1.5">
                    <button
                      type="button"
                      onClick={() => onContinue(s.session_id)}
                      className="flex max-w-[240px] items-center gap-1.5 truncate text-left text-xs font-medium text-slate-800"
                    >
                      {s.running && SPIN}
                      <span className="truncate">{s.title}</span>
                    </button>
                  </td>
                  <td className="px-1 py-1.5">
                    <span className={`rounded px-1.5 py-0.5 text-[9px] font-medium ${
                      s.source === "scheduled"
                        ? "border border-indigo-200 bg-indigo-50 text-indigo-600"
                        : "border border-slate-200 bg-slate-50 text-slate-500"
                    }`}>
                      {s.source === "scheduled" ? "⏰ 定时" : "💬 手动"}
                    </span>
                  </td>
                  <td className="px-1 py-1.5 text-[10px] text-slate-400">{fmtTime(s.last_active)}</td>
                  <td className="px-1 py-1.5 text-right">
                    {s.artifact_count > 0 ? (
                      <span className="text-[10px] text-slate-500" title="该会话产出的交付物数">
                        📦 {s.artifact_count}
                      </span>
                    ) : (
                      <span className="text-[10px] text-slate-300">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {panel.sessions.length === 0 && (
            <p className="py-3 text-center text-xs text-slate-400">
              暂无会话——去对话页发起一次对话,或创建定时任务
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
