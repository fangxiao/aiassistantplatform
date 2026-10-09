"use client";

import React, { useCallback, useEffect, useState } from "react";
import { apiGet, apiPatch } from "../../lib/api/client";
import { Card } from "./WorkbenchView";

/** 任务中心(M25 需求 014 + M28 需求 017):我的任务(实体)/ 最近活动 / 定时 / 交付物。
 *  数据源 GET /workbench/tasks;60s 轮询与简报卡同节奏。
 *  实体区:完成/归档操作;交付物:点击打开(现签 URL)、跳会话续问、存知识库。 */

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
  tasks: TaskEntityItem[]; // M28:实体区优先
  done_tasks?: TaskEntityItem[]; // M30:已完成/已归档(折叠区)
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
  const [showDone, setShowDone] = useState(false);

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

  return (
    <Card title="📋 任务中心">
      {loading && <p className="py-2 text-center text-xs text-slate-400">加载中…</p>}
      {error && <p className="py-2 text-center text-xs text-rose-500">{error}</p>}
      {panel && (
        <div className="space-y-3">
          {/* 我的任务(M28 实体区):命名任务,可完成/归档 */}
          <section>
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-slate-400">我的任务</p>
            {panel.tasks.length === 0 ? (
              <p className="text-xs text-slate-400">
                暂无任务——在会话页点「⭐ 保存为任务」,或创建定时任务
              </p>
            ) : (
              <ul className="space-y-1">
                {panel.tasks.map((t) => {
                  // 定时任务关联的执行状态(运行中/成功/失败 + 下次运行)
                  const sched = t.scheduled_task_id
                    ? panel.scheduled.find((s) => s.id === t.scheduled_task_id)
                    : undefined;
                  return (
                    <li key={t.id} className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-50">
                      <span className="shrink-0 text-xs">{t.kind === "scheduled" ? "⏰" : "⭐"}</span>
                      <button
                        type="button"
                        onClick={() => {
                          const target = t.kind === "scheduled" ? (t.latest_session_id ?? t.session_id) : t.session_id;
                          if (target) onContinue(target);
                        }}
                        disabled={t.kind === "scheduled" ? !(t.latest_session_id ?? t.session_id) : !t.session_id}
                        className="min-w-0 flex-1 text-left disabled:cursor-default"
                        title={t.kind === "scheduled" ? "打开最近一次执行的会话(查看执行过程与产出)" : undefined}
                      >
                        <span className="block truncate text-xs font-medium text-slate-800">{t.title}</span>
                        <span className="block text-[10px] text-slate-400">
                          {t.kind === "scheduled" && sched
                            ? `${STATUS_BADGE[sched.last_status]?.label ?? sched.last_status} · 下次 ${fmtTime(sched.next_run_at)}`
                            : `${t.artifact_count > 0 ? `📦 ${t.artifact_count} 个交付物 · ` : ""}${fmtTime(t.created_at)}`}
                        </span>
                      </button>
                      {t.kind === "scheduled" && sched && STATUS_BADGE[sched.last_status] && (
                        <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-medium ${STATUS_BADGE[sched.last_status]!.cls}`}>
                          {sched.last_status === "running" && <span className="mr-0.5 inline-block animate-pulse">●</span>}
                          {STATUS_BADGE[sched.last_status]!.label}
                        </span>
                      )}
                      {t.kind === "manual" && (
                        <>
                          <button
                            type="button"
                            onClick={() => void patchTask(t.id, { status: "done" })}
                            className="shrink-0 rounded border border-emerald-200 px-1.5 py-0.5 text-[10px] text-emerald-700 hover:bg-emerald-50"
                            title="标记完成(手动任务用;定时任务随删除自动完结)"
                          >
                            ✓ 完成
                          </button>
                          <button
                            type="button"
                            onClick={() => void patchTask(t.id, { status: "archived" })}
                            className="shrink-0 rounded border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-500 hover:bg-slate-100"
                            title="归档(不出现在默认列表)"
                          >
                            归档
                          </button>
                        </>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {(panel.done_tasks?.length ?? 0) > 0 && (
            <section>
              <button
                type="button"
                onClick={() => setShowDone((v) => !v)}
                className="flex w-full items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-slate-400 hover:text-slate-600"
              >
                <span className={`transition ${showDone ? "rotate-90" : ""}`}>▶</span>
                已完成({panel.done_tasks!.length})
              </button>
              {showDone && (
                <ul className="mt-1 space-y-1">
                  {panel.done_tasks!.map((t) => (
                    <li key={t.id} className="flex items-center gap-2 rounded-lg px-2 py-1 opacity-75 hover:bg-slate-50">
                      <span className="shrink-0 text-xs">{t.kind === "scheduled" ? "⏰" : "⭐"}</span>
                      <button
                        type="button"
                        onClick={() => t.session_id && onContinue(t.session_id)}
                        disabled={!t.session_id}
                        className="min-w-0 flex-1 text-left disabled:cursor-default"
                      >
                        <span className="block truncate text-xs text-slate-600">
                          {t.status === "archived" ? "📦 " : ""}
                          {t.title}
                        </span>
                        <span className="block text-[10px] text-slate-400">
                          {t.completed_at ? `完成于 ${fmtTime(t.completed_at)}` : fmtTime(t.created_at)}
                          {t.artifact_count > 0 ? ` · 📦 ${t.artifact_count}` : ""}
                        </span>
                      </button>
                      {t.status === "done" && (
                        <button
                          type="button"
                          onClick={() => void patchTask(t.id, { status: "active" })}
                          className="shrink-0 rounded border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-500 hover:bg-slate-100"
                          title="重新打开"
                        >
                          重开
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {/* 最近活动(M25 聚合:未提升为任务的会话与运行) */}
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
