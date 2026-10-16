"use client";

/** 我的订阅(20261017 批次 1):当前用户绑定该助手的定时任务,可启停/删除。
 *  数据即 scheduler 任务(user_id 绑定),此处按 plugin_id 过滤展示。 */

import React, { useCallback, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPatch } from "../../lib/api/client";
import { Card } from "./WorkbenchView";

interface TaskInfo {
  id: string;
  name: string;
  plugin_id?: string | null;
  enabled: boolean;
  schedule_type: string;
  daily_at?: string | null;
  interval_minutes?: number | null;
  last_status?: string;
}

const fmtSchedule = (t: TaskInfo) =>
  t.schedule_type === "daily"
    ? `每天 ${t.daily_at ?? ""}`
    : t.schedule_type === "weekly"
      ? `每周 ${t.daily_at ?? ""}`
      : t.interval_minutes
        ? `每 ${t.interval_minutes} 分钟`
        : t.schedule_type;

export function MySubscriptionsCard({ pluginId }: { pluginId: string }) {
  const [tasks, setTasks] = useState<TaskInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!pluginId) return;
    try {
      const all = await apiGet<TaskInfo[]>("/scheduler/tasks");
      setTasks(all.filter((t) => !t.plugin_id || t.plugin_id === pluginId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [pluginId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const toggle = async (t: TaskInfo) => {
    await apiPatch(`/scheduler/tasks/${t.id}`, { enabled: !t.enabled });
    void refresh();
  };
  const remove = async (t: TaskInfo) => {
    await apiDelete(`/scheduler/tasks/${t.id}`);
    void refresh();
  };

  if (!pluginId) return null;
  return (
    <Card title="🔔 我的订阅">
      {tasks === null && <p className="py-2 text-center text-xs text-slate-400">加载中…</p>}
      {error && <p className="py-2 text-center text-xs text-rose-500">{error}</p>}
      {tasks !== null && tasks.length === 0 && (
        <p className="py-3 text-center text-xs text-slate-400">
          暂无订阅——点右上角「🔔 订阅」开启每日自动复习
        </p>
      )}
      {tasks !== null && tasks.length > 0 && (
        <div className="flex flex-col divide-y divide-slate-50">
          {tasks.map((t) => (
            <div key={t.id} className="flex items-center gap-2 py-1.5">
              <span className="truncate text-xs font-medium text-slate-800">{t.name}</span>
              <span className="ml-auto shrink-0 font-mono text-[10px] text-slate-400">
                {fmtSchedule(t)}
              </span>
              <span
                className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium ${
                  t.enabled
                    ? "border border-emerald-200 bg-emerald-50 text-emerald-600"
                    : "border border-slate-200 bg-slate-100 text-slate-400"
                }`}
              >
                {t.enabled ? "运行中" : "已停用"}
              </span>
              <button
                type="button"
                onClick={() => void toggle(t)}
                className="shrink-0 text-[10px] text-slate-400 hover:text-indigo-600"
              >
                {t.enabled ? "停用" : "启用"}
              </button>
              <button
                type="button"
                onClick={() => void remove(t)}
                className="shrink-0 text-[10px] text-slate-400 hover:text-rose-500"
              >
                删除
              </button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
