"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  createSource,
  deleteSource,
  listSources,
  listSyncRuns,
  syncSource,
  updateSource,
  type DataSourceInfo,
  type SyncRunInfo,
} from "../../lib/api/kb";

/** 数据源管理面板(内容型连接器, M13 T13.6, 设计 009 §8)。
 *  管理权限由后端校验;无管理权时后端写操作报 404,前端仅隐藏新建入口。 */

const TYPE_META: Record<string, { icon: string; label: string }> = {
  web: { icon: "🕸️", label: "网页/站点" },
  feishu: { icon: "📌", label: "飞书文档" },
  confluence: { icon: "📘", label: "Confluence" },
  github: { icon: "🐙", label: "GitHub" },
};

const SYNC_STATUS_META: Record<string, { label: string; cls: string; dot: string }> = {
  never: { label: "未同步", cls: "text-slate-400", dot: "bg-slate-300" },
  running: { label: "同步中", cls: "text-indigo-600 animate-pulse", dot: "bg-indigo-500 animate-ping" },
  success: { label: "成功", cls: "text-emerald-600", dot: "bg-emerald-500" },
  partial: { label: "部分失败", cls: "text-amber-600", dot: "bg-amber-500" },
  failed: { label: "失败", cls: "text-rose-600", dot: "bg-rose-500" },
};

const POLL_OPTIONS = [
  { value: "", label: "仅手动" },
  { value: "60", label: "每小时" },
  { value: "1440", label: "每天" },
];

interface Props {
  kbId: string;
  canManage: boolean;
  onChanged?: () => void;
}

export function DataSourcesPanel({ kbId, canManage, onChanged }: Props) {
  const [sources, setSources] = useState<DataSourceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<DataSourceInfo | null>(null);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const [runs, setRuns] = useState<Record<string, SyncRunInfo[]>>({});
  const [syncing, setSyncing] = useState<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    try {
      setSources(await listSources(kbId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [kbId]);

  useEffect(() => {
    setSources([]);
    setLoading(true);
    void refresh();
  }, [refresh]);

  // 有 running 源时轮询刷新
  useEffect(() => {
    if (!sources.some((s) => s.last_status === "running")) return;
    const t = setTimeout(() => void refresh(), 3000);
    return () => clearTimeout(t);
  }, [sources, refresh]);

  const handleSync = async (s: DataSourceInfo) => {
    setSyncing((prev) => new Set(prev).add(s.id));
    try {
      await syncSource(kbId, s.id);
      await refresh();
      onChanged?.();
    } catch (err) {
      alert(`同步触发失败: ${err instanceof Error ? err.message : err}`);
    } finally {
      setSyncing((prev) => {
        const next = new Set(prev);
        next.delete(s.id);
        return next;
      });
    }
  };

  const handleDelete = async (s: DataSourceInfo) => {
    if (!confirm(`删除数据源「${s.name}」?已同步的文档会保留在库中。`)) return;
    try {
      await deleteSource(kbId, s.id);
      await refresh();
      onChanged?.();
    } catch (err) {
      alert(`删除失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const toggleRuns = async (sourceId: string) => {
    if (expandedRun === sourceId) {
      setExpandedRun(null);
      return;
    }
    setExpandedRun(sourceId);
    try {
      const list = await listSyncRuns(kbId, sourceId);
      setRuns((prev) => ({ ...prev, [sourceId]: list }));
    } catch {
      setRuns((prev) => ({ ...prev, [sourceId]: [] }));
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-xs">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-slate-900">🔗 数据源</span>
          <span className="text-[11px] text-slate-400">连接外部系统,自动同步进本知识库</span>
        </div>
        {canManage && (
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 transition"
          >
            ＋ 添加数据源
          </button>
        )}
      </div>

      {error && (
        <div className="mx-5 mt-3 rounded-lg bg-red-50 border border-red-200 p-2.5 text-[11px] text-red-700">⚠️ {error}</div>
      )}

      {loading ? (
        <div className="p-8 text-center text-xs text-slate-400">加载数据源...</div>
      ) : sources.length === 0 ? (
        <div className="p-8 text-center text-xs text-slate-400">
          暂无数据源;添加后可从网页/飞书/GitHub 等自动同步内容
        </div>
      ) : (
        <div className="divide-y divide-slate-100">
          {sources.map((s) => {
            const meta = TYPE_META[s.type] ?? { icon: "🔗", label: s.type };
            const st = SYNC_STATUS_META[s.last_status] ?? SYNC_STATUS_META.never;
            return (
              <div key={s.id} className="px-5 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span>{meta.icon}</span>
                      <span className="text-xs font-bold text-slate-900">{s.name}</span>
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-medium text-slate-500">
                        {meta.label}
                      </span>
                      {s.poll_interval_minutes != null && (
                        <span className="text-[10px] text-slate-400">
                          每 {s.poll_interval_minutes >= 1440 ? `${s.poll_interval_minutes / 1440} 天` : `${s.poll_interval_minutes} 分钟`}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-[11px]">
                      <span className={`inline-flex items-center gap-1 ${st.cls}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} />
                        {st.label}
                      </span>
                      {s.last_sync_at && (
                        <span className="text-slate-400">
                          最近同步 {new Date(s.last_sync_at).toLocaleString("zh-CN")}
                        </span>
                      )}
                      {s.last_error && (
                        <span className="truncate max-w-xs text-rose-500" title={s.last_error}>
                          {s.last_error}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => void toggleRuns(s.id)}
                      className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] text-slate-700 hover:bg-slate-50 transition"
                    >
                      {expandedRun === s.id ? "收起记录" : "运行记录"}
                    </button>
                    {canManage && (
                      <>
                        <button
                          type="button"
                          onClick={() => setEditing(s)}
                          className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] text-slate-700 hover:bg-slate-50 transition"
                        >
                          编辑
                        </button>
                        <button
                          type="button"
                          disabled={syncing.has(s.id) || s.last_status === "running"}
                          onClick={() => void handleSync(s)}
                          className="rounded-md bg-slate-900 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-slate-800 transition disabled:opacity-40"
                        >
                          {s.last_status === "running" ? "同步中..." : "立即同步"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(s)}
                          className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1 text-[11px] text-rose-700 hover:bg-rose-100 transition"
                        >
                          删除
                        </button>
                      </>
                    )}
                  </div>
                </div>
                {expandedRun === s.id && (
                  <div className="mt-2 space-y-1 rounded-lg bg-slate-50 p-2.5">
                    {(runs[s.id] ?? []).length === 0 ? (
                      <div className="text-center text-[10px] text-slate-400">暂无运行记录</div>
                    ) : (
                      runs[s.id].slice(0, 5).map((r) => (
                        <div key={r.id} className="flex items-center gap-2 text-[10px] text-slate-600">
                          <span className="font-mono">{new Date(r.started_at).toLocaleString("zh-CN")}</span>
                          <span className={`font-medium ${(SYNC_STATUS_META[r.status] ?? SYNC_STATUS_META.never).cls}`}>
                            {(SYNC_STATUS_META[r.status] ?? SYNC_STATUS_META.never).label}
                          </span>
                          <span>
                            新增 {r.added} · 更新 {r.updated} · 删除 {r.deleted} · 跳过 {r.skipped}
                            {r.failed_docs > 0 && <span className="text-rose-500"> · 失败 {r.failed_docs}</span>}
                          </span>
                          {r.error && <span className="truncate max-w-xs text-rose-500">{r.error}</span>}
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

      {showCreate && (
        <SourceFormModal
          kbId={kbId}
          onClose={() => setShowCreate(false)}
          onSaved={async () => {
            setShowCreate(false);
            await refresh();
            onChanged?.();
          }}
        />
      )}

      {editing && (
        <SourceFormModal
          kbId={kbId}
          source={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await refresh();
            onChanged?.();
          }}
        />
      )}
    </div>
  );
}

function SourceFormModal({
  kbId,
  source,
  onClose,
  onSaved,
}: {
  kbId: string;
  source?: DataSourceInfo; // 传入 = 编辑模式(PATCH);缺省 = 创建(POST)
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const isEdit = !!source;
  const [type] = useState<string>(source?.type ?? "web"); // M13 P0 仅网页;后续类型随 adapter 发布解锁
  const [form, setForm] = useState(() => ({
    name: source?.name ?? "",
    urls: ((source?.config?.urls as string[]) ?? []).join("\n"),
    sitemap: (source?.config?.sitemap as string) ?? "",
    max_depth: String(source?.config?.max_depth ?? 2),
    max_pages: String(source?.config?.max_pages ?? 200),
    poll: source?.poll_interval_minutes != null ? String(source.poll_interval_minutes) : "",
  }));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setSaving(true);
    setError(null);
    try {
      const urls = form.urls
        .split("\n")
        .map((u) => u.trim())
        .filter(Boolean);
      const config: Record<string, any> = {
        urls,
        max_depth: Math.max(0, parseInt(form.max_depth, 10) || 0),
        max_pages: Math.max(1, parseInt(form.max_pages, 10) || 200),
        respect_robots: true,
      };
      if (form.sitemap.trim()) config.sitemap = form.sitemap.trim();
      const poll = form.poll ? parseInt(form.poll, 10) : null;
      if (isEdit && source) {
        await updateSource(kbId, source.id, {
          name: form.name.trim() || source.name,
          config,
          poll_interval_minutes: poll,
        });
      } else {
        await createSource(kbId, {
          type,
          name: form.name.trim() || "网页数据源",
          config,
          poll_interval_minutes: poll,
        });
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
          <div className="flex items-center gap-2">
            <span className="text-xl">🕸️</span>
            <div>
              <h3 className="text-sm font-bold text-slate-900">
                {isEdit ? `编辑数据源 · ${source?.name}` : "添加数据源 · 网页/站点"}
              </h3>
              <p className="text-[11px] text-slate-400">同域抓取,自动去噪转 Markdown 入库(遵循 robots.txt)</p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="text-sm text-slate-400 hover:text-slate-600">
            ✕
          </button>
        </div>

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-2.5 text-[11px] text-red-700">⚠️ {error}</div>
        )}

        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-[11px] font-semibold text-slate-600">名称</span>
            <input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="例如: 产品文档站"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] font-semibold text-slate-600">
              种子 URL(每行一个;从这些页面沿同域链接扩展)
            </span>
            <textarea
              value={form.urls}
              onChange={(e) => setForm((f) => ({ ...f, urls: e.target.value }))}
              rows={3}
              placeholder={"https://docs.example.com/guide\nhttps://docs.example.com/api"}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs outline-none focus:border-indigo-400"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] font-semibold text-slate-600">sitemap.xml(可选)</span>
            <input
              value={form.sitemap}
              onChange={(e) => setForm((f) => ({ ...f, sitemap: e.target.value }))}
              placeholder="https://docs.example.com/sitemap.xml"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs outline-none focus:border-indigo-400"
            />
          </label>
          <div className="flex gap-3">
            <label className="block flex-1">
              <span className="mb-1 block text-[11px] font-semibold text-slate-600">抓取深度</span>
              <input
                type="number"
                min={0}
                value={form.max_depth}
                onChange={(e) => setForm((f) => ({ ...f, max_depth: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
              />
            </label>
            <label className="block flex-1">
              <span className="mb-1 block text-[11px] font-semibold text-slate-600">页数上限</span>
              <input
                type="number"
                min={1}
                max={200}
                value={form.max_pages}
                onChange={(e) => setForm((f) => ({ ...f, max_pages: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
              />
            </label>
            <label className="block flex-1">
              <span className="mb-1 block text-[11px] font-semibold text-slate-600">定时同步</span>
              <select
                value={form.poll}
                onChange={(e) => setForm((f) => ({ ...f, poll: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
              >
                {POLL_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-200"
          >
            取消
          </button>
          <button
            type="button"
            disabled={saving || (!isEdit && !form.urls.trim())}
            onClick={() => void handleSubmit()}
            className="rounded-md bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {saving ? "保存中..." : isEdit ? "保存修改" : "创建数据源"}
          </button>
        </div>
      </div>
    </div>
  );
}
