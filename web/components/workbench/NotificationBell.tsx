"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { apiGet } from "../../lib/api/client";
import { listKbs, listSources, type DataSourceInfo } from "../../lib/api/kb";

/** 工作台通知铃铛(M14 P1.6 · T14.8):站内汇总式通知——同步失败源、未完成待办。
 *  数据前端聚合(无后端);未读以 localStorage 时间戳判定;P2 服务端事件源接入时 UI 现成。 */

const SEEN_KEY = "workbench_notifs_seen";

interface NotifItem {
  id: string;
  icon: string;
  title: string;
  detail?: string;
  tone: "danger" | "warn" | "info";
  ts: string;
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotifItem[]>([]);
  const [hasNew, setHasNew] = useState(false);
  const [loading, setLoading] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

  const collect = useCallback(async () => {
    const list: NotifItem[] = [];
    try {
      // 同步失败/部分失败的数据源(前 8 库)
      const kbs = await apiGet<{ id: string; name: string }[]>("/kb/kbs");
      const kbName = new Map(kbs.map((k) => [k.id, k.name]));
      const stats: DataSourceInfo[] = [];
      await Promise.all(
        kbs.slice(0, 8).map(async (kb) => {
          try {
            stats.push(...(await listSources(kb.id)));
          } catch {
            /* 单库失败忽略 */
          }
        })
      );
      for (const s of stats) {
        if (s.last_status === "failed" || s.last_status === "partial") {
          list.push({
            id: `sync-${s.id}`,
            icon: "🕸️",
            title: `数据源「${s.name}」同步${s.last_status === "failed" ? "失败" : "部分失败"}`,
            detail: s.last_error ?? (s.last_sync_at ? `最近同步 ${new Date(s.last_sync_at).toLocaleString("zh-CN")}` : undefined),
            tone: "danger",
            ts: s.last_sync_at ?? new Date().toISOString(),
          });
        }
      }
      void kbName;
    } catch {
      /* 未登录/接口失败:静默 */
    }
    try {
      const todos = await apiGet<{ text: string; done: boolean }[]>("/workbench/todos");
      const open = todos.filter((t) => !t.done);
      if (open.length > 0) {
        list.push({
          id: "todos-open",
          icon: "✅",
          title: `你有 ${open.length} 条未完成待办`,
          detail: open.slice(0, 3).map((t) => t.text).join(";"),
          tone: "info",
          ts: new Date().toISOString(),
        });
      }
    } catch {
      /* ignore */
    }
    // M15:失败的定时任务运行(验收 3:失败可见)
    try {
      const tasks = await apiGet<{ id: string; name: string; last_status: string; last_error: string | null; last_run_at: string | null }[]>(
        "/scheduler/tasks"
      );
      for (const t of tasks) {
        if (t.last_status === "failed") {
          list.push({
            id: `task-${t.id}`,
            icon: "⏰",
            title: `定时任务「${t.name}」运行失败`,
            detail: t.last_error ?? undefined,
            tone: "danger",
            ts: t.last_run_at ?? new Date().toISOString(),
          });
        }
      }
    } catch {
      /* ignore */
    }
    return list;
  }, []);

  // 未读判定 + 定时静默刷新(铃铛点数)
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      const list = await collect();
      if (cancelled) return;
      setItems(list);
      const seen = localStorage.getItem(SEEN_KEY);
      const seenTs = seen ? new Date(seen).getTime() : 0;
      setHasNew(list.some((n) => new Date(n.ts).getTime() > seenTs));
      timer = setTimeout(tick, 60000);
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [collect]);

  // 点外部关闭
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const markSeen = () => {
    localStorage.setItem(SEEN_KEY, new Date().toISOString());
    setHasNew(false);
  };

  const openPanel = async () => {
    const next = !open;
    setOpen(next);
    if (next) {
      setLoading(true);
      setItems(await collect());
      setLoading(false);
      markSeen();
    }
  };

  const toneCls: Record<NotifItem["tone"], string> = {
    danger: "text-rose-600",
    warn: "text-amber-600",
    info: "text-slate-600",
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => void openPanel()}
        className="relative rounded-lg px-2 py-1.5 text-base transition hover:bg-slate-100"
        title="通知"
      >
        🔔
        {hasNew && (
          <span className="absolute right-0.5 top-0.5 h-2 w-2 rounded-full bg-rose-500 ring-2 ring-white" />
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-50 w-80 rounded-2xl border border-slate-200 bg-white shadow-xl">
          <div className="border-b border-slate-100 px-4 py-2.5 text-xs font-bold text-slate-900">
            通知
            <span className="ml-2 text-[10px] font-normal text-slate-400">同步状态与待办汇总</span>
          </div>
          <div className="max-h-80 overflow-y-auto p-2">
            {loading && items.length === 0 ? (
              <div className="py-6 text-center text-[11px] text-slate-400">加载中...</div>
            ) : items.length === 0 ? (
              <div className="py-6 text-center text-[11px] text-slate-400">暂无通知,一切正常 ✓</div>
            ) : (
              <div className="space-y-1">
                {items.map((n) => (
                  <div key={n.id} className="rounded-lg px-2 py-2 transition hover:bg-slate-50">
                    <div className={`flex items-center gap-1.5 text-xs font-medium ${toneCls[n.tone]}`}>
                      <span>{n.icon}</span>
                      {n.title}
                    </div>
                    {n.detail && (
                      <div className="mt-0.5 truncate pl-5 text-[10px] text-slate-400" title={n.detail}>
                        {n.detail}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
