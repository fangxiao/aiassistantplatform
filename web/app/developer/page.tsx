"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Navbar } from "../../components/layout/Navbar";
import { apiDelete, apiGet, apiPatch, apiPost } from "../../lib/api/client";
import { isAuthed } from "../../lib/api/auth";
import type { LlmEndpointInfo, PluginInfo } from "../../lib/types";

export default function DeveloperPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<"plugins" | "llm">("plugins");

  // Plugins state
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loadingPlugins, setLoadingPlugins] = useState(false);
  const [selectedManifest, setSelectedManifest] = useState<any | null>(null);

  // LLM Endpoints state
  const [endpoints, setEndpoints] = useState<LlmEndpointInfo[]>([]);
  const [loadingLlm, setLoadingLlm] = useState(false);
  const [showAddLlm, setShowAddLlm] = useState(false);
  const [llmForm, setLlmForm] = useState({
    name: "",
    base_url: "",
    model: "",
    api_key: "",
    is_default: true,
  });

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthed()) {
      router.push("/auth");
      return;
    }
    loadData();
  }, [router]);

  const loadData = async () => {
    setError(null);
    try {
      setLoadingPlugins(true);
      const pluginList = await apiGet<PluginInfo[]>("/plugins");
      setPlugins(pluginList);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingPlugins(false);
    }

    try {
      setLoadingLlm(true);
      const llmList = await apiGet<LlmEndpointInfo[]>("/admin/llm-endpoints");
      setEndpoints(llmList);
    } catch {
      // ignore
    } finally {
      setLoadingLlm(false);
    }
  };

  // Plugin operations
  const handleTogglePlugin = async (p: PluginInfo) => {
    try {
      const action = p.status === "active" ? "disable" : "enable";
      await apiPost(`/plugins/${p.id}/${action}`, {});
      await loadData();
    } catch (err) {
      alert(`操作失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const handleUninstall = async (id: string) => {
    if (!confirm("确定要卸载该插件吗？关联的私有技能与工具将被清理。")) return;
    try {
      await apiDelete(`/plugins/${id}`);
      await loadData();
    } catch (err) {
      alert(`卸载失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  // LLM Endpoint operations
  const handleAddEndpoint = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiPost("/admin/llm-endpoints", llmForm);
      setShowAddLlm(false);
      setLlmForm({ name: "", base_url: "", model: "", api_key: "", is_default: true });
      await loadData();
    } catch (err) {
      alert(`创建端点失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const handleSetDefaultLlm = async (id: string) => {
    try {
      await apiPatch(`/admin/llm-endpoints/${id}`, { is_default: true });
      await loadData();
    } catch (err) {
      alert(`设为默认失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Navbar />

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              🛠️ 开发者与管理中心
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              管理已部署的插件智能体、私有扩展及大语言模型网关端点配置。
            </p>
          </div>

          <div className="flex rounded-lg border border-slate-200 bg-white p-1 shadow-xs">
            <button
              type="button"
              onClick={() => setActiveTab("plugins")}
              className={`rounded-md px-4 py-1.5 text-xs font-medium transition ${
                activeTab === "plugins"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              🧩 插件助手管理 ({plugins.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("llm")}
              className={`rounded-md px-4 py-1.5 text-xs font-medium transition ${
                activeTab === "llm"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              🤖 LLM 网关端点 ({endpoints.length})
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-6 rounded-lg bg-red-50 p-3 text-xs text-red-600 border border-red-200">
            {error}
          </div>
        )}

        {/* Tab 1: 插件管理 */}
        {activeTab === "plugins" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 shadow-xs text-xs text-slate-600">
              <span>
                💡 插件可使用 <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-slate-800">agentplatform deploy</code> CLI 命令一键打包部署。
              </span>
              <button
                type="button"
                onClick={loadData}
                className="rounded border border-slate-200 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50"
              >
                刷新列表
              </button>
            </div>

            {loadingPlugins ? (
              <div className="py-12 text-center text-xs text-slate-400">加载插件列表中...</div>
            ) : plugins.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-200 bg-white p-12 text-center text-xs text-slate-400">
                暂无已部署插件，您可使用 SDK 和 CLI 创建并部署助手插件。
              </div>
            ) : (
              <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
                <table className="w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-600">
                    <tr>
                      <th className="px-4 py-3">插件名称</th>
                      <th className="px-4 py-3">版本</th>
                      <th className="px-4 py-3">运行状态</th>
                      <th className="px-4 py-3">部署时间</th>
                      <th className="px-4 py-3 text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {plugins.map((p) => (
                      <tr key={p.id} className="hover:bg-slate-50 transition">
                        <td className="px-4 py-3 font-semibold text-slate-900">
                          <div className="flex items-center gap-2">
                            <span>🤖</span>
                            <span>{p.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 font-mono text-slate-500">v{p.version}</td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                              p.status === "active"
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : "bg-slate-100 text-slate-500 border border-slate-200"
                            }`}
                          >
                            <span className={`h-1.5 w-1.5 rounded-full ${p.status === "active" ? "bg-emerald-500" : "bg-slate-400"}`} />
                            {p.status === "active" ? "运行中" : "已停用"}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-400 text-[11px]">
                          {new Date(p.deployed_at).toLocaleString("zh-CN")}
                        </td>
                        <td className="px-4 py-3 text-right space-x-2">
                          <button
                            type="button"
                            onClick={() => setSelectedManifest(p.manifest)}
                            className="rounded px-2 py-1 text-slate-600 hover:bg-slate-100 transition"
                          >
                            查看清单
                          </button>
                          <button
                            type="button"
                            onClick={() => handleTogglePlugin(p)}
                            className={`rounded px-2 py-1 transition font-medium ${
                              p.status === "active"
                                ? "text-amber-600 hover:bg-amber-50"
                                : "text-emerald-600 hover:bg-emerald-50"
                            }`}
                          >
                            {p.status === "active" ? "停用" : "启用"}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleUninstall(p.id)}
                            className="rounded px-2 py-1 text-rose-600 hover:bg-rose-50 transition"
                          >
                            卸载
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: LLM 端点管理 */}
        {activeTab === "llm" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-xs text-slate-500">
                配置 OpenAI 兼容格式的大语言模型服务端点，供智能体执行调度。
              </p>
              <button
                type="button"
                onClick={() => setShowAddLlm(true)}
                className="rounded-lg bg-slate-900 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-slate-800 transition"
              >
                + 添加端点
              </button>
            </div>

            {loadingLlm ? (
              <div className="py-12 text-center text-xs text-slate-400">加载端点中...</div>
            ) : endpoints.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-200 bg-white p-12 text-center text-xs text-slate-400">
                暂未配置 LLM 端点。
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {endpoints.map((ep) => (
                  <div
                    key={ep.id}
                    className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-4 shadow-xs"
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <h4 className="font-bold text-slate-900 text-sm">{ep.name}</h4>
                        {ep.is_default && (
                          <span className="rounded bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700 border border-indigo-100">
                            ★ 默认模型
                          </span>
                        )}
                      </div>
                      <p className="mt-2 font-mono text-xs text-slate-600">
                        模型: <span className="font-semibold text-slate-800">{ep.model}</span>
                      </p>
                      <p className="mt-1 truncate text-xs text-slate-400 font-mono">
                        {ep.base_url}
                      </p>
                    </div>

                    <div className="mt-4 flex items-center justify-end border-t border-slate-100 pt-2">
                      {!ep.is_default && (
                        <button
                          type="button"
                          onClick={() => handleSetDefaultLlm(ep.id)}
                          className="text-xs text-indigo-600 hover:underline font-medium"
                        >
                          设为默认端点
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Manifest Modal */}
        {selectedManifest && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
            onClick={() => setSelectedManifest(null)}
          >
            <div
              className="max-h-[80vh] w-full max-w-lg overflow-hidden rounded-xl bg-white p-6 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b pb-3">
                <h3 className="text-sm font-bold text-slate-900">插件清单 Manifest (JSON)</h3>
                <button
                  type="button"
                  onClick={() => setSelectedManifest(null)}
                  className="rounded p-1 text-slate-400 hover:bg-slate-100"
                >
                  ✕
                </button>
              </div>
              <pre className="mt-4 max-h-96 overflow-auto rounded bg-slate-900 p-4 font-mono text-xs text-slate-100 leading-relaxed">
                {JSON.stringify(selectedManifest, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {/* Add LLM Modal */}
        {showAddLlm && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
            onClick={() => setShowAddLlm(false)}
          >
            <div
              className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b pb-3">
                <h3 className="text-sm font-bold text-slate-900">添加 OpenAI 兼容模型端点</h3>
                <button
                  type="button"
                  onClick={() => setShowAddLlm(false)}
                  className="rounded p-1 text-slate-400 hover:bg-slate-100"
                >
                  ✕
                </button>
              </div>

              <form onSubmit={handleAddEndpoint} className="mt-4 space-y-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">端点标识名称</label>
                  <input
                    type="text"
                    required
                    placeholder="如 glm-4-flash / gpt-4o"
                    value={llmForm.name}
                    onChange={(e) => setLlmForm({ ...llmForm, name: e.target.value })}
                    className="w-full rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-800 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">API Base URL</label>
                  <input
                    type="url"
                    required
                    placeholder="https://api.openai.com/v1"
                    value={llmForm.base_url}
                    onChange={(e) => setLlmForm({ ...llmForm, base_url: e.target.value })}
                    className="w-full rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-800 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">模型名称 (Model)</label>
                  <input
                    type="text"
                    required
                    placeholder="如 deepseek-v4-flash 或 gpt-4o"
                    value={llmForm.model}
                    onChange={(e) => setLlmForm({ ...llmForm, model: e.target.value })}
                    className="w-full rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-800 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">API Key (加密存储)</label>
                  <input
                    type="password"
                    required
                    placeholder="sk-••••••••"
                    value={llmForm.api_key}
                    onChange={(e) => setLlmForm({ ...llmForm, api_key: e.target.value })}
                    className="w-full rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-800 focus:outline-none"
                  />
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="is_default"
                    checked={llmForm.is_default}
                    onChange={(e) => setLlmForm({ ...llmForm, is_default: e.target.checked })}
                    className="rounded text-slate-800"
                  />
                  <label htmlFor="is_default" className="text-xs text-slate-700 cursor-pointer">
                    设为默认模型端点
                  </label>
                </div>

                <div className="mt-4 flex justify-end gap-2 pt-3 border-t">
                  <button
                    type="button"
                    onClick={() => setShowAddLlm(false)}
                    className="rounded px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100"
                  >
                    取消
                  </button>
                  <button
                    type="submit"
                    className="rounded bg-slate-900 px-4 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
                  >
                    保存端点
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
