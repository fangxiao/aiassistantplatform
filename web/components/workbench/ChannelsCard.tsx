"use client";

import React, { useCallback, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost } from "../../lib/api/client";
import { Card, Placeholder } from "./WorkbenchView";

/** 📣 通知通道(产品化):平台级(管理员配,全员共享)+ 个人级;
 *  定时任务按通道引用,配置一次处处复用。 */

interface Channel {
  id: string;
  name: string;
  type: string; // feishu_webhook | webhook | email
  platform: boolean;
  enabled: boolean;
}

const TYPE_META: Record<string, { icon: string; label: string }> = {
  feishu_webhook: { icon: "💬", label: "飞书机器人" },
  webhook: { icon: "🔗", label: "Webhook" },
  email: { icon: "📧", label: "邮件" },
};

export function ChannelsCard({ isDeveloper }: { isDeveloper?: boolean }) {
  const [developer, setDeveloper] = useState(Boolean(isDeveloper));
  useEffect(() => {
    if (isDeveloper === undefined) {
      try {
        const u = JSON.parse(localStorage.getItem("agentplatform_user") || "{}");
        setDeveloper(u?.role === "developer");
      } catch {
        setDeveloper(false);
      }
    }
  }, [isDeveloper]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", type: "feishu_webhook", url: "", email: "", platform: false });
  const [testing, setTesting] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setChannels(await apiGet<Channel[]>("/notify/channels"));
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

  const add = async () => {
    setError(null);
    const config = form.type === "email" ? { email: form.email } : { url: form.url };
    try {
      await apiPost("/notify/channels", { name: form.name.trim(), type: form.type, config, platform: form.platform });
      setShowForm(false);
      setForm({ name: "", type: "feishu_webhook", url: "", email: "", platform: false });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const remove = async (c: Channel) => {
    if (!confirm(`删除通道「${c.name}」?引用它的任务将跳过此通道。`)) return;
    try {
      await apiDelete(`/notify/channels/${c.id}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const test = async (c: Channel) => {
    setTesting(c.id);
    try {
      const r = await apiPost<{ ok: boolean }>(`/notify/channels/${c.id}/test`, {});
      alert(r.ok ? "✅ 测试消息已发送,请到群/邮箱查收" : "❌ 发送失败,检查地址或平台 SMTP 配置");
    } catch (err) {
      alert(`测试失败: ${err instanceof Error ? err.message : err}`);
    } finally {
      setTesting(null);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-xs">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <span className="text-xs font-bold text-slate-900">
          📣 通知通道
          <span className="ml-2 text-[10px] font-normal text-slate-400">定时任务产出推送到这里;平台级通道全员共享</span>
        </span>
        <button
          type="button"
          onClick={() => setShowForm(true)}
          className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
        >
          ＋ 添加
        </button>
      </div>
      <div className="p-3">
        {error && <div className="mb-2 rounded-lg bg-red-50 border border-red-200 p-2 text-[10px] text-red-700">⚠️ {error}</div>}
        {loading ? (
          <Placeholder text="加载通道..." />
        ) : channels.length === 0 ? (
          <Placeholder text="暂无通道;添加飞书群机器人地址,定时任务即可推送到群" />
        ) : (
          <div className="space-y-1">
            {channels.map((c) => {
              const m = TYPE_META[c.type] ?? { icon: "🔗", label: c.type };
              return (
                <div key={c.id} className="group flex items-center gap-2 rounded-lg px-2 py-2 transition hover:bg-slate-50">
                  <span>{m.icon}</span>
                  <span className="truncate text-xs text-slate-700">{c.name}</span>
                  {c.platform && (
                    <span className="shrink-0 rounded bg-indigo-50 border border-indigo-200 px-1 py-0.5 text-[9px] text-indigo-700">平台</span>
                  )}
                  <span className="shrink-0 text-[10px] text-slate-400">{m.label}</span>
                  <div className="ml-auto flex shrink-0 gap-1.5 opacity-0 transition group-hover:opacity-100">
                    <button
                      type="button"
                      disabled={testing === c.id}
                      onClick={() => void test(c)}
                      className="rounded border border-slate-200 px-2 py-0.5 text-[10px] text-slate-600 hover:bg-slate-100"
                    >
                      {testing === c.id ? "发送中..." : "测试"}
                    </button>
                    <button
                      type="button"
                      onClick={() => void remove(c)}
                      className="rounded border border-rose-200 bg-rose-50 px-2 py-0.5 text-[10px] text-rose-600 hover:bg-rose-100"
                    >
                      删除
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md space-y-3 rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="text-sm font-bold text-slate-900">添加通知通道</h3>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-slate-600">名称</span>
              <input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="如: 项目群机器人"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-slate-600">类型</span>
              <select
                value={form.type}
                onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
              >
                <option value="feishu_webhook">💬 飞书群机器人(webhook)</option>
                <option value="webhook">🔗 通用 Webhook(JSON)</option>
                <option value="email">📧 邮件(需平台 SMTP)</option>
              </select>
            </label>
            {form.type === "email" ? (
              <label className="block">
                <span className="mb-1 block text-[11px] font-semibold text-slate-600">收件邮箱</span>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-indigo-400"
                />
              </label>
            ) : (
              <label className="block">
                <span className="mb-1 block text-[11px] font-semibold text-slate-600">Webhook 地址</span>
                <input
                  value={form.url}
                  onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
                  placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs outline-none focus:border-indigo-400"
                />
              </label>
            )}
            {developer && (
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.platform}
                  onChange={(e) => setForm((f) => ({ ...f, platform: e.target.checked }))}
                  className="h-3.5 w-3.5 accent-indigo-600"
                />
                <span className="text-[11px] text-slate-600">平台级通道(全员可用,仅开发者可删)</span>
              </label>
            )}
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setShowForm(false)} className="rounded-md px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-200">取消</button>
              <button
                type="button"
                disabled={!form.name.trim() || (form.type === "email" ? !form.email : !form.url)}
                onClick={() => void add()}
                className="rounded-md bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
              >
                保存通道
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
