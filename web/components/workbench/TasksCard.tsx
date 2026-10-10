"use client";

import React, { useCallback, useEffect, useState } from "react";
import { apiGet, apiPatch } from "../../lib/api/client";
import { Card } from "./WorkbenchView";
import MarkdownRenderer from "../renderers/MarkdownRenderer";

/** 任务中心(M25/028 + 20261010 重构):单表格四列——任务名称/类型/状态/交付物。
 *  交付物点击可查看(md 预览或打开文件);定时任务的完整管理在「⏰ 定时任务」卡。 */

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

interface TaskEntityItem {
  id: string;
  title: string;
  status: "active" | "done" | "archived";
  kind: "manual" | "scheduled";
  session_id: string | null;
  scheduled_task_id?: string | null;
  latest_session_id?: string | null;
  artifact_count: number;
  created_at: string;
  completed_at: string | null;
}

interface TasksPanel {
  tasks: TaskEntityItem[];
  done_tasks?: TaskEntityItem[];
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

const SPIN = (
  <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
  </svg>
);

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
  const [showDone, setShowDone] = useState(false);
  // 交付物 markdown 预览(20261010:任务表第四列点击直达)
  const [preview, setPreview] = useState<{ title: string; content: string } | null>(null);
  // 某任务的交付物列表弹层(多交付物时)
  const [listFor, setListFor] = useState<{ task: TaskEntityItem; items: ArtifactItem[] } | null>(null);

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
    // M30:定时任务增删改/会话提升后即时刷新(60s 轮询兜底)
    const onChanged = () => void refresh();
    window.addEventListener("ap:tasks-changed", onChanged);
    return () => {
      clearInterval(timer);
      window.removeEventListener("ap:tasks-changed", onChanged);
    };
  }, [refresh]);

  const patchTask = useCallback(
    async (id: string, body: { status?: string; title?: string }) => {
      try {
        await apiPatch(`/tasks/${id}`, body);
        await refresh();
      } catch {
        // 静默:下轮轮询自愈
      }
    },
    [refresh],
  );

  const artifactsOf = (t: TaskEntityItem): ArtifactItem[] => {
    const sid = t.kind === "scheduled" ? (t.latest_session_id ?? t.session_id) : t.session_id;
    if (!sid) return [];
    return panel?.artifacts.filter((a) => a.session_id === sid) ?? [];
  };

  const openArtifacts = (t: TaskEntityItem) => {
    const items = artifactsOf(t);
    if (items.length === 0) return;
    if (items.length === 1) {
      const a = items[0];
      if (a.kind === "report" && a.content) setPreview({ title: a.title, content: a.content });
      else if (a.signed_url) window.open(a.signed_url, "_blank", "noopener");
      return;
    }
    setListFor({ task: t, items });
  };

  const doneTasks = panel?.done_tasks ?? [];
  const rows = panel ? [...panel.tasks, ...(showDone ? doneTasks : [])] : [];

  return (
    <div className="space-y-0">
      <Card title="📋 任务中心">
        {loading && <p className="py-2 text-center text-xs text-slate-400">加载中…</p>}
        {error && <p className="py-2 text-center text-xs text-rose-500">{error}</p>}
        {panel && (
          <div>
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                  <th className="px-2 py-1.5 font-semibold">任务名称</th>
                  <th className="w-16 px-1 py-1.5 font-semibold">类型</th>
                  <th className="w-20 px-1 py-1.5 font-semibold">状态</th>
                  <th className="w-16 px-1 py-1.5 text-right font-semibold">交付物</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((t) => {
                  const sched = t.scheduled_task_id
                    ? panel.scheduled.find((s) => s.id === t.scheduled_task_id)
                    : undefined;
                  const isDone = t.status !== "active";
                  const target = t.kind === "scheduled" ? (t.latest_session_id ?? t.session_id) : t.session_id;
                  return (
                    <tr key={t.id} className={`group border-b border-slate-50 last:border-0 hover:bg-slate-50 ${isDone ? "opacity-60" : ""}`}>
                      <td className="px-2 py-1.5">
                        <button
                          type="button"
                          onClick={() => target && onContinue(target)}
                          disabled={!target}
                          className="max-w-[220px] truncate text-left text-xs font-medium text-slate-800 disabled:cursor-default"
                          title={t.kind === "scheduled" ? "打开最近一次执行的会话" : "打开任务会话"}
                        >
                          {t.title}
                        </button>
                        {t.kind === "manual" && t.status === "active" && (
                          <span className="ml-1.5 inline-flex gap-1 opacity-0 transition group-hover:opacity-100">
                            <button
                              type="button"
                              onClick={() => void patchTask(t.id, { status: "done" })}
                              className="rounded border border-emerald-200 px-1 py-0.5 text-[9px] text-emerald-700 hover:bg-emerald-50"
                              title="标记完成"
                            >
                              ✓
                            </button>
                            <button
                              type="button"
                              onClick={() => void patchTask(t.id, { status: "archived" })}
                              className="rounded border border-slate-200 px-1 py-0.5 text-[9px] text-slate-500 hover:bg-slate-100"
                              title="归档"
                            >
                              归档
                            </button>
                          </span>
                        )}
                      </td>
                      <td className="px-1 py-1.5 text-[10px] text-slate-500">
                        {t.kind === "scheduled" ? "定时" : "常规"}
                      </td>
                      <td className="px-1 py-1.5 text-[10px]">
                        {isDone ? (
                          <span className="text-slate-400">已完成</span>
                        ) : t.kind === "scheduled" && sched?.last_status === "running" ? (
                          <span className="inline-flex items-center gap-1 font-medium text-indigo-600">
                            {SPIN}运行中
                          </span>
                        ) : t.kind === "scheduled" && sched?.last_status === "failed" ? (
                          <span className="font-medium text-rose-600" title={sched ? `下次 ${fmtTime(sched.next_run_at)}` : undefined}>失败</span>
                        ) : (
                          <span className="text-slate-500" title={sched ? `下次 ${fmtTime(sched.next_run_at)}` : undefined}>
                            {t.kind === "scheduled" ? "待运行" : "进行中"}
                          </span>
                        )}
                      </td>
                      <td className="px-1 py-1.5 text-right">
                        {t.artifact_count > 0 ? (
                          <button
                            type="button"
                            onClick={() => openArtifacts(t)}
                            className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] text-slate-600 hover:border-indigo-300 hover:text-indigo-600"
                            title="查看该任务的交付物"
                          >
                            📦 {t.artifact_count}
                          </button>
                        ) : (
                          <span className="text-[10px] text-slate-300">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {panel.tasks.length === 0 && doneTasks.length === 0 && (
              <p className="py-3 text-center text-xs text-slate-400">
                暂无任务——在会话页点「⭐ 保存为任务」,或创建定时任务
              </p>
            )}
            {doneTasks.length > 0 && (
              <button
                type="button"
                onClick={() => setShowDone((v) => !v)}
                className="mt-1.5 flex w-full items-center gap-1 text-[10px] font-semibold text-slate-400 hover:text-slate-600"
              >
                <span className={`transition ${showDone ? "rotate-90" : ""}`}>▶</span>
                已完成({doneTasks.length})
              </button>
            )}
          </div>
        )}
      </Card>

      {/* 某任务的交付物列表(多件时) */}
      {listFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs" onClick={() => setListFor(null)}>
          <div className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-900">📦 {listFor.task.title} · 交付物</h3>
              <button type="button" onClick={() => setListFor(null)} className="text-slate-400 hover:text-slate-600">✕</button>
            </div>
            <div className="max-h-72 space-y-1 overflow-y-auto">
              {listFor.items.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => {
                    setListFor(null);
                    if (a.kind === "report" && a.content) setPreview({ title: a.title, content: a.content });
                    else if (a.signed_url) window.open(a.signed_url, "_blank", "noopener");
                  }}
                  className="flex w-full items-center gap-2 rounded-lg border border-slate-100 px-3 py-2 text-left hover:bg-slate-50"
                >
                  <span>{KIND_ICON[a.kind] ?? "📦"}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs text-slate-800">{a.title}</span>
                    <span className="block text-[10px] text-slate-400">{fmtTime(a.created_at)}</span>
                  </span>
                  <span className="text-[10px] text-indigo-500">{a.kind === "report" ? "查看" : "打开"}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 交付物 Markdown 预览 */}
      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
              <h3 className="truncate text-sm font-bold text-slate-900">📄 {preview.title}</h3>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => onSaveToKb(preview.content)}
                  className="rounded-md border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-[11px] font-medium text-indigo-700 hover:bg-indigo-100"
                >
                  存 KB
                </button>
                <button type="button" onClick={() => setPreview(null)} className="text-slate-400 hover:text-slate-600">
                  ✕
                </button>
              </div>
            </div>
            <div className="overflow-y-auto px-5 py-4 text-sm">
              <MarkdownRenderer block={{ type: "markdown", data: { text: preview.content } }} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
