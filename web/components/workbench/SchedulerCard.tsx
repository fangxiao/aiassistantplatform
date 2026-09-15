"use client";

import React, { useCallback, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost } from "../../lib/api/client";
import { Card, Placeholder } from "./WorkbenchView";

/** ⏰ 定时任务卡(M15 T15.5):用户级定时 agent 任务管理。
 *  列表(下次运行/状态)/新建编辑弹窗/启停/跑一次/运行记录(产出全文)。 */

interface SchedTask {
  id: string;
  name: string;
  kind: string;
  prompt: string;
  schedule_type: string;
  daily_at: string | null;
  interval_minutes: number | null;
  auto_save_kb: boolean;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: string;
  last_error: string | null;
}

interface SchedRun {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  output: string | null;
  session_id: string | null;
  error: string | null;
}

const KIND_META: Record<string, { icon: string; label: string }> = {
  briefing: { icon: "📰", label: "每日晨报" },
  inspection: { icon: "🔍", label: "巡检" },
  custom: { icon: "🧩", label: "自定义" },
};

const STATUS_META: Record<string, { label: string; dot: string }> = {
  never: { label: "未运行", dot: "bg-slate-300" },
  running: { label: "运行中", dot: "bg-indigo-500 animate-pulse" },
  success: { label: "正常", dot: "bg-emerald-500" },
  failed: { label: "失败", dot: "bg-rose-500" },
};

export function SchedulerCard({ onContinue }: { onContinue: (sessionId: string) => void }) {
  const [tasks, setTasks] = useState<SchedTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<SchedTask | null>(null);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const [runs, setRuns] = useState<Record<string, SchedRun[]>>({});
  const [running, setRunning] = useState<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    try {
      setTasks(await apiGet<SchedTask[]>("/scheduler/tasks"));
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

  // 运行中轮询
  useEffect(() => {
    if (!tasks.some((t) => t.last_status === "running")) return;
    const t = setTimeout(() => void refresh(), 4000);
    return () => clearTimeout(t);
  }, [tasks, refresh]);

  const toggleEnabled = async (t: SchedTask) => {
    try {
      await apiPatch(`/scheduler/tasks/${t.id}`, { ...t, enabled: !t.enabled });
      await refresh();
    } catch (err) {
      alert(`操作失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const runNow = async (t: SchedTask) => {
    setRunning((prev) => new Set(prev).add(t.id));
    try {
      await apiPost(`/scheduler/tasks/${t.id}/run`, {});
      await refresh();
    } catch (err) {
      alert(`触发失败: ${err instanceof Error ? err.message : err}`);
    } finally {
      setRunning((prev) => {
        const next = new Set(prev);
        next.delete(t.id);
        return next;
      });
    }
  };

  const remove = async (t: SchedTask) => {
    if (!confirm(`删除定时任务「${t.name}」?历史运行记录将保留。`)) return;
    try {
      await apiDelete(`/scheduler/tasks/${t.id}`);
      await refresh();
    } catch (err) {
      alert(`删除失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const toggleRuns = async (t: SchedTask) => {
    if (expandedRun === t.id) {
      setExpandedRun(null);
      return;
    }
    setExpandedRun(t.id);
    try {
      const list = await apiGet<SchedRun[]>(`/scheduler/tasks/${t.id}/runs`);
      setRuns((prev) => ({ ...prev, [t.id]: list }));
    } catch {
      setRuns((prev) => ({ ...prev, [t.id]: [] }));
    }
  };

  const freqLabel = (t: SchedTask) =>
    t.schedule_type === "daily" ? `每天 ${t.daily_at ?? "--:--"}` : `每 ${t.interval_minutes} 分钟`;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-xs">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <span className="text-xs font-bold text-slate-900">
          ⏰ 定时任务
          <span className="ml-2 text-[10px] font-normal text-slate-400">到点自动唤醒 agent,产出送达工作台</span>
        </span>
        <button
          type="button"
          onClick={() => setShowForm(true)}
          className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
        >
          ＋ 新建任务
        </button>
      </div>

      {error && (
        <div className="mx-4 mt-2 rounded-lg bg-red-50 border border-red-200 p-2 text-[10px] text-red-700">⚠️ {error}</div>
      )}

      {loading ? (
        <Placeholder text="加载任务..." />
      ) : tasks.length === 0 ? (
        <Placeholder text="暂无定时任务;创建晨报任务,每天早上自动收到简报" />
      ) : (
        <div className="divide-y divide-slate-100">
          {tasks.map((t) => {
            const kind = KIND_META[t.kind] ?? { icon: "🧩", label: t.kind };
            const st = STATUS_META[t.last_status] ?? STATUS_META.never;
            return (
              <div key={t.id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span>{kind.icon}</span>
                      <span className="truncate text-xs font-bold text-slate-900">{t.name}</span>
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] text-slate-500">{kind.label}</span>
                      {!t.enabled && (
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] text-slate-400">已停用</span>
                      )}
                      {t.auto_save_kb && (
                        <span className="rounded bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 text-[9px] text-emerald-700" title="产出自动存入知识库">
                          📥
                        </span>
                      )}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-slate-400">
                      <span>🕐 {freqLabel(t)}</span>
                      {t.next_run_at && t.enabled && (
                        <span>下次 {new Date(t.next_run_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                      )}
                      <span className={`inline-flex items-center gap-1 ${st.label === "失败" ? "text-rose-600" : st.label === "正常" ? "text-emerald-600" : "text-slate-500"}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} />
                        {st.label}
                      </span>
                      {t.last_error && (
                        <span className="truncate max-w-xs text-rose-500" title={t.last_error}>{t.last_error}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => void toggleRuns(t)}
                      className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[10px] text-slate-700 hover:bg-slate-50"
                    >
                      {expandedRun === t.id ? "收起" : "记录"}
                    </button>
                    <button
                      type="button"
                      disabled={t.last_status === "running" || running.has(t.id)}
                      onClick={() => void runNow(t)}
                      className="rounded-md bg-slate-900 px-2 py-1 text-[10px] font-semibold text-white hover:bg-slate-800 disabled:opacity-40"
                    >
                      跑一次
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditing(t)}
                      className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[10px] text-slate-700 hover:bg-slate-50"
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      onClick={() => void remove(t)}
                      className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[10px] text-rose-700 hover:bg-rose-100"
                    >
                      删除
                    </button>
                  </div>
                </div>

                {expandedRun === t.id && (
                  <div className="mt-2 space-y-1 rounded-lg bg-slate-50 p-2">
                    {(runs[t.id] ?? []).length === 0 ? (
                      <div className="text-center text-[10px] text-slate-400">暂无运行记录</div>
                    ) : (
                      runs[t.id].slice(0, 5).map((r) => (
                        <div key={r.id} className="rounded-md bg-white p-2">
                          <div className="flex items-center gap-2 text-[10px]">
                            <span className="font-mono text-slate-500">
                              {new Date(r.started_at).toLocaleString("zh-CN")}
                            </span>
                            <span className={r.status === "success" ? "font-medium text-emerald-600" : "font-medium text-rose-600"}>
                              {r.status === "success" ? "成功" : r.status === "failed" ? "失败" : "运行中"}
                            </span>
                            {r.session_id && (
                              <button
                                type="button"
                                onClick={() => onContinue(r.session_id!)}
                                className="text-indigo-500 hover:text-indigo-700"
                              >
                                继续追问 →
                              </button>
                            )}
                          </div>
                          {r.error && <div className="mt-0.5 text-[10px] text-rose-600">{r.error}</div>}
                          {r.output && (
                            <div className="mt-1 line-clamp-3 whitespace-pre-wrap text-[10px] text-slate-600">{r.output}</div>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {(showForm || editing) && (
        <TaskFormModal
          task={editing}
          onClose={() => {
            setShowForm(false);
            setEditing(null);
          }}
          onSaved={async () => {
            setShowForm(false);
            setEditing(null);
            await refresh();
          }}
        />
      )}
    </div>
  );
}

function TaskFormModal({
  task,
  onClose,
  onSaved,
}: {
  task: SchedTask | null;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const isEdit = !!task;
  const [form, setForm] = useState(() => ({
    name: task?.name ?? "",
    kind: task?.kind ?? "briefing",
    prompt: task?.prompt ?? "",
    schedule_type: task?.schedule_type ?? "daily",
    daily_at: task?.daily_at ?? "08:00",
    interval_minutes: String(task?.interval_minutes ?? 60),
    auto_save_kb: task?.auto_save_kb ?? false,
  }));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const body = {
        name: form.name.trim() || (form.kind === "briefing" ? "每日晨报" : "定时任务"),
        kind: form.kind,
        prompt: form.prompt,
        schedule_type: form.schedule_type,
        daily_at: form.schedule_type === "daily" ? form.daily_at : null,
        interval_minutes: form.schedule_type === "interval" ? parseInt(form.interval_minutes, 10) || 60 : null,
        auto_save_kb: form.auto_save_kb,
        enabled: task?.enabled ?? true,
      };
      if (isEdit && task) {
        await apiPatch(`/scheduler/tasks/${task.id}`, body);
      } else {
        await apiPost("/scheduler/tasks", body);
      }
      await onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
      <div className="w-full max-w-md space-y-4 rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div>
            <h3 className="text-sm font-bold text-slate-900">{isEdit ? "编辑定时任务" : "新建定时任务"}</h3>
            <p className="text-[11px] text-slate-400">到点以你的身份自动运行一次助手,产出送达工作台</p>
          </div>
          <button type="button" onClick={onClose} className="text-sm text-slate-400 hover:text-slate-600">✕</button>
        </div>

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-2.5 text-[11px] text-red-700">⚠️ {error}</div>
        )}

        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-[11px] font-semibold text-slate-600">任务名称</span>
            <input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="例如: 每日晨报"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[11px] font-semibold text-slate-600">任务模板</span>
            <select
              value={form.kind}
              onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value }))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
            >
              <option value="briefing">📰 每日晨报(聚合知识库动态 + 待办)</option>
              <option value="inspection">🔍 巡检(仅报告异常与建议)</option>
              <option value="custom">🧩 自定义指令</option>
            </select>
          </label>

          {form.kind === "custom" ? (
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-slate-600">任务指令(必填)</span>
              <textarea
                value={form.prompt}
                onChange={(e) => setForm((f) => ({ ...f, prompt: e.target.value }))}
                rows={4}
                placeholder="到点让助手做什么,例如: 总结我知识库里最近一周新增的内容"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
              />
            </label>
          ) : (
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-slate-600">补充要求(可选)</span>
              <input
                value={form.prompt}
                onChange={(e) => setForm((f) => ({ ...f, prompt: e.target.value }))}
                placeholder="例如: 重点关照场景贷知识库"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
              />
            </label>
          )}

          <div className="flex gap-3">
            <label className="block flex-1">
              <span className="mb-1 block text-[11px] font-semibold text-slate-600">调度方式</span>
              <select
                value={form.schedule_type}
                onChange={(e) => setForm((f) => ({ ...f, schedule_type: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
              >
                <option value="daily">每天固定时刻</option>
                <option value="interval">固定间隔</option>
              </select>
            </label>
            {form.schedule_type === "daily" ? (
              <label className="block flex-1">
                <span className="mb-1 block text-[11px] font-semibold text-slate-600">执行时刻</span>
                <input
                  type="time"
                  value={form.daily_at}
                  onChange={(e) => setForm((f) => ({ ...f, daily_at: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
                />
              </label>
            ) : (
              <label className="block flex-1">
                <span className="mb-1 block text-[11px] font-semibold text-slate-600">间隔(分钟)</span>
                <input
                  type="number"
                  min={1}
                  value={form.interval_minutes}
                  onChange={(e) => setForm((f) => ({ ...f, interval_minutes: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
                />
              </label>
            )}
          </div>

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.auto_save_kb}
              onChange={(e) => setForm((f) => ({ ...f, auto_save_kb: e.target.checked }))}
              className="h-3.5 w-3.5 accent-indigo-600"
            />
            <span className="text-[11px] text-slate-600">产出自动存入知识库</span>
          </label>
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="rounded-md px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-200">
            取消
          </button>
          <button
            type="button"
            disabled={saving || (form.kind === "custom" && !form.prompt.trim())}
            onClick={() => void submit()}
            className="rounded-md bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {saving ? "保存中..." : isEdit ? "保存修改" : "创建任务"}
          </button>
        </div>
      </div>
    </div>
  );
}
