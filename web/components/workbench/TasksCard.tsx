"use client";

import React, { useCallback, useEffect, useState } from "react";
import { apiGet } from "../../lib/api/client";
import { Card } from "./WorkbenchView";

/** 任务中心(M25/需求 014):进行中 / 定时任务 / 交付物 三栏聚合。
 *  数据源 GET /workbench/tasks;60s 轮询与简报卡同节奏。
 *  交付物:点击打开(现签 URL)、跳会话续问、report 类可存知识库。 */

interface RunningItem {
  kind: "session" | "run";
  id: string;
  title: string;
  detail: string;
  session_id: string | null;
  started_at: string | null;
  updated_at: string | null;
}

interface ScheduledItem {
  id: string;
  name: string;
  kind: string;
  next_run_at: string | null;
  last_status: string;
}

interface ArtifactItem {
  id: string;
  kind: "html" | "image" | "report";
  title: string;
  created_at: string;
  session_id: string | null;
  signed_url: string | null;
  content: string | null;
}

interface TasksPanel {
  running: RunningItem[];
  scheduled: ScheduledItem[];
  artifacts: ArtifactItem[];
}

const KIND_ICON: Record<ArtifactItem["kind"], string> = {
  html: "📄",
  image: "🖼️",
  report: "📊",
};

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  success: { label: "成功", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  failed: { label: "失败", cls: "bg-rose-50 text-rose-700 border-rose-200" },
  running: { label: "运行中", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  never: { label: "未运行", cls: "bg-slate-50 text-slate-500 border-slate-200" },
};

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

export function TasksCard({
  onContinue,
  onSaveToKb,
}: {
  onContinue: (sessionId: string) => void;
  onSaveToKb: (content: string) => void;
}) {
  const [panel, setPanel] = useState<TasksPanel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setPanel(await apiGet<TasksPanel>("/workbench/tasks"));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 60_000);
    return () => clearInterval(timer);
  }, [refresh]);

  return (
    <Card title="📋 任务中心">
      {loading && <p className="py-2 text-center text-xs text-slate-400">加载中…</p>}
      {error && <p className="py-2 text-center text-xs text-rose-500">{error}</p>}
      {panel && (
        <div className="space-y-3">
          {/* 进行中 */}
          <section>
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-slate-400">进行中</p>
            {panel.running.length === 0 ? (
              <p className="text-xs text-slate-400">暂无进行中的任务</p>
            ) : (
              <ul className="space-y-1">
                {panel.running.map((r) => (
                  <li key={`${r.kind}-${r.id}`}>
                    <button
                      type="button"
                      onClick={() => r.session_id && onContinue(r.session_id)}
                      className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-slate-50"
                    >
                      <span className="shrink-0 text-xs">{r.kind === "run" ? "⏳" : "💬"}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs font-medium text-slate-800">{r.title}</span>
                        {r.detail && <span className="block truncate text-[10px] text-slate-400">{r.detail}</span>}
                      </span>
                      <span className="shrink-0 text-[10px] text-slate-400">
                        {fmtTime(r.updated_at ?? r.started_at)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* 定时任务 */}
          <section>
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-slate-400">定时任务</p>
            {panel.scheduled.length === 0 ? (
              <p className="text-xs text-slate-400">暂无定时任务</p>
            ) : (
              <ul className="space-y-1">
                {panel.scheduled.map((t) => {
                  const badge = STATUS_BADGE[t.last_status] ?? STATUS_BADGE.never;
                  return (
                    <li key={t.id} className="flex items-center gap-2 px-2 py-1">
                      <span className="min-w-0 flex-1 truncate text-xs text-slate-700">{t.name}</span>
                      <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] ${badge.cls}`}>{badge.label}</span>
                      <span className="shrink-0 text-[10px] text-slate-400">下次 {fmtTime(t.next_run_at)}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {/* 交付物 */}
          <section>
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-slate-400">交付物</p>
            {panel.artifacts.length === 0 ? (
              <p className="text-xs text-slate-400">暂无产出——让助手生成图片/报告后自动登记在这里</p>
            ) : (
              <ul className="space-y-1">
                {panel.artifacts.slice(0, 8).map((a) => (
                  <li key={a.id} className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-50">
                    <span className="shrink-0 text-xs">{KIND_ICON[a.kind] ?? "📦"}</span>
                    <button
                      type="button"
                      onClick={() => a.signed_url && window.open(a.signed_url, "_blank", "noopener")}
                      disabled={!a.signed_url}
                      className="min-w-0 flex-1 text-left disabled:cursor-default"
                      title={a.signed_url ? "点击打开" : "在会话中查看"}
                    >
                      <span className="block truncate text-xs font-medium text-slate-800">{a.title}</span>
                      <span className="block text-[10px] text-slate-400">{fmtTime(a.created_at)}</span>
                    </button>
                    {a.session_id && (
                      <button
                        type="button"
                        onClick={() => onContinue(a.session_id!)}
                        className="shrink-0 rounded border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-600 hover:bg-slate-100"
                      >
                        继续
                      </button>
                    )}
                    {a.kind === "report" && a.content && (
                      <button
                        type="button"
                        onClick={() => onSaveToKb(a.content!)}
                        className="shrink-0 rounded border border-indigo-200 bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-700 hover:bg-indigo-100"
                      >
                        存 KB
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </Card>
  );
}
