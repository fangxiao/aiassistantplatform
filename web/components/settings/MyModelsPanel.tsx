"use client";

import React, { useCallback, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost } from "../../lib/api/client";

/** 我的模型(用户自定义 LLM 端点,OpenAI 格式)——个人密钥仅本人可用;
 *  统一模型目录 = 个人 + 平台共享 + 默认,助手选模型的数据源。 */

interface MyEndpoint {
  id: string;
  name: string;
  base_url: string;
  model: string;
  is_default: boolean;
  endpoint_type?: string;
}

interface CatalogModel {
  model: string;
  source: "personal" | "platform" | "env_default";
  endpoint_id: string | null;
  is_default: boolean;
}

export function MyModelsPanel() {
  const [mine, setMine] = useState<MyEndpoint[]>([]);
  const [catalog, setCatalog] = useState<CatalogModel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", base_url: "", model: "", api_key: "", is_default: false });

  const refresh = useCallback(async () => {
    try {
      const [m, c] = await Promise.all([
        apiGet<MyEndpoint[]>("/llm/endpoints"),
        apiGet<{ models: CatalogModel[] }>("/llm/models"),
      ]);
      setMine(m);
      setCatalog(c.models);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const add = async () => {
    setError(null);
    try {
      await apiPost("/llm/endpoints", form);
      setShowForm(false);
      setForm({ name: "", base_url: "", model: "", api_key: "", is_default: false });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const remove = async (id: string) => {
    if (!confirm("删除该自定义模型?")) return;
    try {
      await apiDelete(`/llm/endpoints/${id}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const setDefault = async (id: string) => {
    try {
      await apiPost(`/llm/endpoints/${id}`, { is_default: true });
      await refresh();
    } catch (err) {
      alert(`设置失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const inputCls = "w-full rounded-lg border border-slate-300 px-3 py-2 text-xs outline-none focus:border-indigo-400";

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="mb-1 text-sm font-bold text-slate-900">🧠 可用模型目录</h3>
        <p className="mb-3 text-[11px] text-slate-400">
          个人自定义 + 平台共享 + 平台默认;助手与对话可按模型名选用
        </p>
        <div className="flex flex-wrap gap-2">
          {catalog.map((m) => (
            <span
              key={m.model}
              title={m.source === "personal" ? "我的自定义模型" : m.source === "platform" ? "平台共享端点" : "环境默认"}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] ${
                m.source === "personal"
                  ? "border-indigo-200 bg-indigo-50 text-indigo-700"
                  : m.source === "platform"
                    ? "border-slate-200 bg-white text-slate-600"
                    : "border-emerald-200 bg-emerald-50 text-emerald-700"
              }`}
            >
              {m.source === "personal" ? "👤" : m.source === "platform" ? "🏢" : "⚙️"}
              <span className="font-mono">{m.model}</span>
              {m.is_default && <span className="text-[9px]">默认</span>}
            </span>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <div>
            <span className="text-sm font-bold text-slate-900">🔑 我的模型</span>
            <span className="ml-2 text-[10px] text-slate-400">OpenAI 兼容端点,密钥加密存储仅本人可用</span>
          </div>
          <button
            type="button"
            onClick={() => setShowForm(true)}
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
          >
            ＋ 添加模型
          </button>
        </div>
        <div className="p-3">
          {error && <div className="mb-2 rounded-lg bg-red-50 border border-red-200 p-2 text-[10px] text-red-700">⚠️ {error}</div>}
          {mine.length === 0 ? (
            <div className="py-6 text-center text-xs text-slate-400">
              暂无自定义模型;填入任意 OpenAI 兼容端点(base_url + api_key + 模型名)即可
            </div>
          ) : (
            <div className="space-y-1">
              {mine.map((e) => (
                <div key={e.id} className="group flex items-center gap-2 rounded-lg px-2 py-2 hover:bg-slate-50">
                  <span className="text-xs font-medium text-slate-700">{e.name}</span>
                  <span className="font-mono text-[10px] text-slate-400">{e.model}</span>
                  <span className="truncate font-mono text-[10px] text-slate-300">{e.base_url}</span>
                  {e.is_default && (
                    <span className="rounded bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 text-[9px] text-emerald-700">我的默认</span>
                  )}
                  <div className="ml-auto flex gap-1.5 opacity-0 transition group-hover:opacity-100">
                    {!e.is_default && (
                      <button type="button" onClick={() => void setDefault(e.id)} className="rounded border border-slate-200 px-2 py-0.5 text-[10px] text-slate-600 hover:bg-slate-100">
                        设为我的默认
                      </button>
                    )}
                    <button type="button" onClick={() => void remove(e.id)} className="rounded border border-rose-200 bg-rose-50 px-2 py-0.5 text-[10px] text-rose-600 hover:bg-rose-100">
                      删除
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md space-y-3 rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="text-sm font-bold text-slate-900">添加我的模型(OpenAI 兼容)</h3>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-slate-600">名称</span>
              <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="如: 我的 GPT" className={inputCls} />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-slate-600">Base URL</span>
              <input value={form.base_url} onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))} placeholder="https://api.openai.com/v1" className={inputCls} />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-slate-600">模型名</span>
              <input value={form.model} onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))} placeholder="如 gpt-4o / glm-5.3-flash" className={inputCls} />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-slate-600">API Key(加密存储,不回显)</span>
              <input type="password" value={form.api_key} onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))} placeholder="sk-..." className={inputCls} />
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={form.is_default} onChange={(e) => setForm((f) => ({ ...f, is_default: e.target.checked }))} className="h-3.5 w-3.5 accent-slate-800" />
              <span className="text-[11px] text-slate-600">设为我的默认模型(仅影响我自己)</span>
            </label>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setShowForm(false)} className="rounded-md px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-200">取消</button>
              <button type="button" disabled={!form.name || !form.base_url || !form.model || !form.api_key} onClick={() => void add()} className="rounded-md bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50">
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
