"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Navbar } from "../../components/layout/Navbar";
import { BlockRenderer } from "../../components/renderers/BlockRenderer";
import { apiDelete, apiGet, apiPatch, apiPost } from "../../lib/api/client";
import { isAuthed } from "../../lib/api/auth";
import type {
  BuiltinResourceInfo,
  CapabilitiesInfo,
  ContentBlock,
  ContentBlockDef,
  LlmEndpointInfo,
  PluginInfo,
} from "../../lib/types";

export default function DeveloperPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<
    "plugins" | "registry" | "widgets" | "guide" | "llm"
  >("plugins");

  // Capabilities state
  const [capabilities, setCapabilities] = useState<CapabilitiesInfo | null>(null);
  const [loadingCaps, setLoadingCaps] = useState(false);
  const [capFilter, setCapFilter] = useState<"all" | "skill" | "tool">("all");
  const [capSearch, setCapSearch] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [selectedSchemaRes, setSelectedSchemaRes] = useState<BuiltinResourceInfo | null>(null);

  // Widgets state
  const [widgetCategory, setWidgetCategory] = useState<"all" | "display" | "interactive" | "action">("all");
  const [selectedWidget, setSelectedWidget] = useState<ContentBlockDef | null>(null);
  const [interactLog, setInteractLog] = useState<string | null>(null);

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

    try {
      setLoadingCaps(true);
      const caps = await apiGet<CapabilitiesInfo>("/specs/capabilities");
      setCapabilities(caps);
      if (caps?.content_blocks?.length && !selectedWidget) {
        setSelectedWidget(caps.content_blocks[0]);
      }
    } catch {
      // ignore fallback
    } finally {
      setLoadingCaps(false);
    }
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
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

  const allPublicResources: (BuiltinResourceInfo & { kind: "tool" | "skill" })[] = [
    ...(capabilities?.builtin_tools || []).map((t) => ({ ...t, kind: "tool" as const })),
    ...(capabilities?.builtin_skills || []).map((s) => ({ ...s, kind: "skill" as const })),
  ];

  const filteredResources = allPublicResources.filter((r) => {
    if (capFilter !== "all" && r.kind !== capFilter) return false;
    if (capSearch) {
      const q = capSearch.toLowerCase();
      return r.id.toLowerCase().includes(q) || r.description.toLowerCase().includes(q) || r.name.toLowerCase().includes(q);
    }
    return true;
  });

  const filteredWidgets = (capabilities?.content_blocks || []).filter((w) => {
    if (widgetCategory === "all") return true;
    return w.category === widgetCategory;
  });

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Navbar />

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6">
        {/* Header Title */}
        <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
                🛠️ 开发者生态与管理中心
              </h1>
              <span className="rounded-full bg-indigo-50 border border-indigo-200 px-2.5 py-0.5 text-xs font-semibold text-indigo-700">
                AI-Native Hub
              </span>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              探索平台共享能力注册表、22 种富交互控件画廊、管理已部署插件与 LLM 端点。
            </p>
          </div>

          {/* Navigation Tabs */}
          <div className="flex flex-wrap rounded-xl border border-slate-200 bg-white p-1 shadow-xs">
            <button
              type="button"
              onClick={() => setActiveTab("plugins")}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-medium transition ${
                activeTab === "plugins"
                  ? "bg-slate-900 text-white shadow-xs font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              🧩 插件管理 ({plugins.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("registry")}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-medium transition ${
                activeTab === "registry"
                  ? "bg-slate-900 text-white shadow-xs font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              📚 共享能力注册表 ({allPublicResources.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("widgets")}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-medium transition ${
                activeTab === "widgets"
                  ? "bg-slate-900 text-white shadow-xs font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              🎨 22 种控件画廊
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("guide")}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-medium transition ${
                activeTab === "guide"
                  ? "bg-slate-900 text-white shadow-xs font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              📖 开发者与 AI 指南
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("llm")}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-medium transition ${
                activeTab === "llm"
                  ? "bg-slate-900 text-white shadow-xs font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              🤖 LLM 端点 ({endpoints.length})
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-6 rounded-xl bg-red-50 p-4 text-xs text-red-700 border border-red-200 shadow-xs">
            ⚠️ {error}
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 1: 插件管理 */}
        {/* ========================================================================= */}
        {activeTab === "plugins" && (
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-xs text-xs text-slate-600">
              <div className="flex items-center gap-2">
                <span className="text-base">💡</span>
                <span>
                  通过 CLI 命令 <code className="rounded bg-slate-100 px-2 py-0.5 font-mono font-semibold text-indigo-600">agentplatform deploy . --target http://localhost:8000</code> 快速部署助手。
                </span>
              </div>
              <button
                type="button"
                onClick={loadData}
                className="self-start sm:self-auto rounded-lg border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 transition"
              >
                🔄 刷新列表
              </button>
            </div>

            {loadingPlugins ? (
              <div className="py-16 text-center text-xs text-slate-400">正在加载已部署插件...</div>
            ) : plugins.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center text-slate-500 shadow-xs">
                <span className="text-3xl block mb-2">📦</span>
                <p className="text-sm font-semibold text-slate-800">暂无已部署插件</p>
                <p className="mt-1 text-xs text-slate-400">
                  可使用 <code className="font-mono bg-slate-100 px-1 py-0.5 rounded text-slate-700">agentplatform init my-plugin</code> 创建并部署首个助手。
                </p>
              </div>
            ) : (
              <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
                <table className="w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50/80 text-[11px] font-semibold text-slate-600">
                    <tr>
                      <th className="px-5 py-3.5">插件助手</th>
                      <th className="px-4 py-3.5">版本</th>
                      <th className="px-4 py-3.5">模型</th>
                      <th className="px-4 py-3.5">公共依赖</th>
                      <th className="px-4 py-3.5">状态</th>
                      <th className="px-4 py-3.5">部署时间</th>
                      <th className="px-5 py-3.5 text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {plugins.map((p) => (
                      <tr key={p.id} className="hover:bg-slate-50/70 transition">
                        <td className="px-5 py-3.5 font-semibold text-slate-900">
                          <div className="flex items-center gap-2">
                            <span className="text-base">🤖</span>
                            <div>
                              <div className="font-bold text-slate-900">{p.name}</div>
                              {p.manifest?.description && (
                                <div className="text-[11px] font-normal text-slate-400 truncate max-w-xs">
                                  {p.manifest.description}
                                </div>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3.5 font-mono text-slate-500">v{p.version}</td>
                        <td className="px-4 py-3.5 text-slate-600 font-mono text-[11px]">
                          {p.manifest?.model || "默认模型"}
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="flex flex-wrap gap-1 max-w-xs">
                            {(p.manifest?.depends_on || []).length > 0 ? (
                              (p.manifest.depends_on as string[]).map((dep) => (
                                <span
                                  key={dep}
                                  className="rounded bg-indigo-50 border border-indigo-100 px-1.5 py-0.5 text-[10px] font-mono text-indigo-700"
                                >
                                  {dep}
                                </span>
                              ))
                            ) : (
                              <span className="text-slate-400 text-[11px]">-</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3.5">
                          <span
                            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                              p.status === "active"
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : "bg-slate-100 text-slate-500 border border-slate-200"
                            }`}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${
                                p.status === "active" ? "bg-emerald-500" : "bg-slate-400"
                              }`}
                            />
                            {p.status === "active" ? "运行中" : "已停用"}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 text-slate-400 text-[11px]">
                          {new Date(p.deployed_at).toLocaleString("zh-CN")}
                        </td>
                        <td className="px-5 py-3.5 text-right space-x-1.5">
                          <button
                            type="button"
                            onClick={() => setSelectedManifest(p.manifest)}
                            className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-slate-700 hover:bg-slate-50 transition"
                          >
                            清单
                          </button>
                          <button
                            type="button"
                            onClick={() => handleTogglePlugin(p)}
                            className={`rounded-md px-2.5 py-1 transition font-medium border ${
                              p.status === "active"
                                ? "border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100"
                                : "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                            }`}
                          >
                            {p.status === "active" ? "停用" : "启用"}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleUninstall(p.id)}
                            className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1 text-rose-700 hover:bg-rose-100 transition"
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

        {/* ========================================================================= */}
        {/* TAB 2: 共享能力注册表 (Skill & Tool Registry) */}
        {/* ========================================================================= */}
        {activeTab === "registry" && (
          <div className="space-y-6">
            {/* Banner */}
            <div className="rounded-2xl border border-indigo-100 bg-gradient-to-r from-indigo-500/10 via-purple-500/10 to-pink-500/5 p-6 shadow-xs">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h2 className="text-lg font-bold text-slate-950 flex items-center gap-2">
                    <span>🌟</span> 平台第一特色 · 共享能力注册表 (Skill & Tool Ecosystem)
                  </h2>
                  <p className="mt-1.5 text-xs text-slate-600 max-w-3xl leading-relaxed">
                    平台维护高稳定性通用能力池。插件开发者<strong>无需重复造轮子</strong>，只需在 <code className="bg-white/80 border border-slate-200 px-1 py-0.5 rounded font-mono font-bold text-indigo-700">plugin.yaml</code> 的 <code className="bg-white/80 border border-slate-200 px-1 py-0.5 rounded font-mono font-bold text-indigo-700">depends_on</code> 列表中声明依赖版本约束（支持 <code className="font-mono text-slate-800">^</code>、<code className="font-mono text-slate-800">~</code>），运行时将自动完成解析与 Function Calling 挂载。
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="inline-flex items-center rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-xs">
                    已收录 {allPublicResources.length} 项公共资源
                  </span>
                </div>
              </div>
            </div>

            {/* Filter & Search Bar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex rounded-lg border border-slate-200 bg-white p-1 shadow-xs">
                <button
                  type="button"
                  onClick={() => setCapFilter("all")}
                  className={`rounded-md px-3 py-1 text-xs font-medium transition ${
                    capFilter === "all" ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  全部能力 ({allPublicResources.length})
                </button>
                <button
                  type="button"
                  onClick={() => setCapFilter("tool")}
                  className={`rounded-md px-3 py-1 text-xs font-medium transition ${
                    capFilter === "tool" ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  🔧 确定性工具 Tools ({(capabilities?.builtin_tools || []).length})
                </button>
                <button
                  type="button"
                  onClick={() => setCapFilter("skill")}
                  className={`rounded-md px-3 py-1 text-xs font-medium transition ${
                    capFilter === "skill" ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  🧠 领域技能 Skills ({(capabilities?.builtin_skills || []).length})
                </button>
              </div>

              <div className="relative">
                <input
                  type="text"
                  placeholder="搜索能力 ID、名称或功能描述..."
                  value={capSearch}
                  onChange={(e) => setCapSearch(e.target.value)}
                  className="w-full sm:w-72 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 shadow-xs focus:border-indigo-500 focus:outline-hidden"
                />
              </div>
            </div>

            {/* Resource Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredResources.map((res) => {
                const isTool = res.kind === "tool";
                const props = res.schema?.parameters?.properties || {};
                const paramKeys = Object.keys(props);

                return (
                  <div
                    key={res.id}
                    className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-5 shadow-xs hover:border-indigo-300 hover:shadow-md transition"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <span
                          className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                            isTool
                              ? "bg-blue-50 text-blue-700 border border-blue-200"
                              : "bg-purple-50 text-purple-700 border border-purple-200"
                          }`}
                        >
                          {isTool ? "🔧 TOOL (工具)" : "🧠 SKILL (技能)"}
                        </span>
                        <span className="font-mono text-xs text-slate-400">v{res.version}</span>
                      </div>

                      <h3 className="text-sm font-bold text-slate-900 font-mono flex items-center gap-1.5">
                        {res.id}
                      </h3>
                      <p className="mt-1.5 text-xs text-slate-600 leading-relaxed line-clamp-2">
                        {res.description}
                      </p>

                      {/* Parameters summary */}
                      <div className="mt-4 rounded-lg bg-slate-50 p-3 border border-slate-100">
                        <div className="text-[11px] font-semibold text-slate-600 mb-1.5">
                          📥 接受参数:
                        </div>
                        {paramKeys.length === 0 ? (
                          <span className="text-[11px] text-slate-400">无需参数</span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {paramKeys.map((k) => (
                              <span
                                key={k}
                                className="rounded bg-white border border-slate-200 px-1.5 py-0.5 text-[10px] font-mono text-slate-700"
                              >
                                {k}: <span className="text-indigo-600">{props[k]?.type || "any"}</span>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Bottom Actions */}
                    <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedSchemaRes(res)}
                        className="text-xs font-medium text-slate-600 hover:text-indigo-600 transition"
                      >
                        🔍 查看 Schema
                      </button>

                      <button
                        type="button"
                        onClick={() => copyToClipboard(res.dependency_example, res.id)}
                        className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition flex items-center gap-1 ${
                          copiedId === res.id
                            ? "bg-emerald-600 text-white"
                            : "bg-slate-900 text-white hover:bg-slate-800"
                        }`}
                      >
                        {copiedId === res.id ? "✓ 已复制依赖代码" : "📋 复制 depends_on"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: 22 种富交互控件画廊 (Widget & ContentBlock Showcase) */}
        {/* ========================================================================= */}
        {activeTab === "widgets" && (
          <div className="space-y-6">
            {/* Banner */}
            <div className="rounded-2xl border border-purple-100 bg-gradient-to-r from-purple-500/10 via-pink-500/10 to-indigo-500/5 p-6 shadow-xs">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h2 className="text-lg font-bold text-slate-950 flex items-center gap-2">
                    <span>🎨</span> 平台富交互能力 · 22 种 ContentBlock 控件画廊
                  </h2>
                  <p className="mt-1.5 text-xs text-slate-600 max-w-3xl leading-relaxed">
                    智能体在对话中可通过 <code className="bg-white/80 border border-slate-200 px-1 py-0.5 rounded font-mono font-bold text-purple-700">output_block(type, data)</code> 输出超越纯文本的富交互 UI 组件。支持卡片、表格、代码、Mermaid 图表，以及单选、多选、下拉、日期、文件上传、操作确认框与复合表单。
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="inline-flex items-center rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-semibold text-white shadow-xs">
                    全套 22 种组件就绪
                  </span>
                </div>
              </div>
            </div>

            {/* Category Filter */}
            <div className="flex rounded-lg border border-slate-200 bg-white p-1 shadow-xs w-fit">
              <button
                type="button"
                onClick={() => setWidgetCategory("all")}
                className={`rounded-md px-3 py-1 text-xs font-medium transition ${
                  widgetCategory === "all" ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                全部组件 (22)
              </button>
              <button
                type="button"
                onClick={() => setWidgetCategory("display")}
                className={`rounded-md px-3 py-1 text-xs font-medium transition ${
                  widgetCategory === "display" ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                📊 展示类 (8)
              </button>
              <button
                type="button"
                onClick={() => setWidgetCategory("interactive")}
                className={`rounded-md px-3 py-1 text-xs font-medium transition ${
                  widgetCategory === "interactive" ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                ✍️ 交互输入类 (11)
              </button>
              <button
                type="button"
                onClick={() => setWidgetCategory("action")}
                className={`rounded-md px-3 py-1 text-xs font-medium transition ${
                  widgetCategory === "action" ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                ⚡ 反馈动作类 (3)
              </button>
            </div>

            {/* Interactive Showcase Split Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
              {/* Left Selector List (4 cols) */}
              <div className="lg:col-span-4 space-y-2 max-h-[700px] overflow-y-auto pr-1">
                {filteredWidgets.map((w) => {
                  const isSelected = selectedWidget?.type === w.type;
                  return (
                    <button
                      key={w.type}
                      type="button"
                      onClick={() => {
                        setSelectedWidget(w);
                        setInteractLog(null);
                      }}
                      className={`w-full text-left rounded-xl p-3.5 transition border ${
                        isSelected
                          ? "bg-indigo-50/80 border-indigo-300 shadow-xs"
                          : "bg-white border-slate-200 hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-bold text-xs text-slate-900 font-mono">
                          {w.type}
                        </span>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                            w.category === "display"
                              ? "bg-blue-50 text-blue-700"
                              : w.category === "interactive"
                              ? "bg-amber-50 text-amber-700"
                              : "bg-emerald-50 text-emerald-700"
                          }`}
                        >
                          {w.category_name}
                        </span>
                      </div>
                      <div className="mt-1 text-xs font-semibold text-slate-800">
                        {w.name}
                      </div>
                      <div className="mt-0.5 text-[11px] text-slate-500 line-clamp-1">
                        {w.description}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Right Live Preview & Code Generator (8 cols) */}
              <div className="lg:col-span-8 space-y-4">
                {selectedWidget && (
                  <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-6">
                    {/* Header */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 border-b border-slate-100">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-base font-bold text-indigo-700">
                            {selectedWidget.type}
                          </span>
                          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 font-medium">
                            {selectedWidget.name}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          {selectedWidget.description}
                        </p>
                      </div>

                      <button
                        type="button"
                        onClick={() =>
                          copyToClipboard(
                            JSON.stringify(
                              {
                                type: selectedWidget.type,
                                data: selectedWidget.sample_data,
                              },
                              null,
                              2
                            ),
                            `payload-${selectedWidget.type}`
                          )
                        }
                        className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition shrink-0 ${
                          copiedId === `payload-${selectedWidget.type}`
                            ? "bg-emerald-600 text-white"
                            : "bg-slate-900 text-white hover:bg-slate-800"
                        }`}
                      >
                        {copiedId === `payload-${selectedWidget.type}` ? "✓ 已复制 Payload" : "📋 复制 JSON 数据"}
                      </button>
                    </div>

                    {/* Live Preview Box */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                          <span>👁️</span> 实时交互渲染预览 (Live Preview)
                        </span>
                        <span className="text-[10px] text-slate-400">支持真实点击与输入测试</span>
                      </div>

                      <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-5 min-h-[140px] flex flex-col justify-center">
                        <BlockRenderer
                          block={{
                            type: selectedWidget.type,
                            data: selectedWidget.sample_data,
                            meta: { id: "preview-block" },
                          }}
                          onInteract={(action, val, args) => {
                            setInteractLog(
                              `[交互回传触发] Action: ${action} | Value: ${JSON.stringify(val)} ${
                                args ? `| Args: ${JSON.stringify(args)}` : ""
                              }`
                            );
                          }}
                        />
                      </div>

                      {interactLog && (
                        <div className="mt-2 rounded-lg bg-emerald-50 border border-emerald-200 p-2.5 text-xs font-mono text-emerald-800">
                          ⚡ {interactLog}
                        </div>
                      )}
                    </div>

                    {/* Output Block Payload JSON */}
                    <div>
                      <div className="text-xs font-bold text-slate-700 mb-2">
                        💻 智能体调用 output_block 参数示例:
                      </div>
                      <pre className="rounded-xl bg-slate-950 p-4 text-xs font-mono text-emerald-400 overflow-x-auto">
                        {JSON.stringify(
                          {
                            type: selectedWidget.type,
                            data: selectedWidget.sample_data,
                          },
                          null,
                          2
                        )}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 4: 开发者与 AI 协同指南 (Developer & AI Guide) */}
        {/* ========================================================================= */}
        {activeTab === "guide" && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 shadow-xs space-y-8">
              <div>
                <h2 className="text-xl font-black tracking-tight text-slate-900 flex items-center gap-2">
                  <span>🚀</span> AgentPlatform 插件开发者与 AI 协同开发指南
                </h2>
                <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                  本平台采用 **Plugin 即 Assistant** 的轻量设计理念。您可借助 Antigravity、Claude Code、Cursor 或 Windsurf 等 AI 编程助手，通过全套 CLI 工具链实现零摩擦、自愈式的开发与发布。
                </p>
              </div>

              {/* Step 1-4 Workflow */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-2">
                  <div className="flex items-center gap-2 font-bold text-xs text-slate-900">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-white text-xs">1</span>
                    初始化脚手架
                  </div>
                  <p className="text-[11px] text-slate-500">
                    自动生成带依赖示例与 AI 规范的标准插件工程目录。
                  </p>
                  <code className="block rounded bg-white p-2 text-[11px] font-mono text-indigo-700 border border-slate-200">
                    agentplatform init my-assistant
                  </code>
                </div>

                <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-2">
                  <div className="flex items-center gap-2 font-bold text-xs text-slate-900">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-white text-xs">2</span>
                    声明依赖与编写
                  </div>
                  <p className="text-[11px] text-slate-500">
                    在 plugin.yaml 中复用平台 Tool/Skill，并用 @skill/@tool 编写能力。
                  </p>
                  <code className="block rounded bg-white p-2 text-[11px] font-mono text-indigo-700 border border-slate-200">
                    agentplatform registry
                  </code>
                </div>

                <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-2">
                  <div className="flex items-center gap-2 font-bold text-xs text-slate-900">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-white text-xs">3</span>
                    本地闭环调试与测试
                  </div>
                  <p className="text-[11px] text-slate-500">
                    无需远程服务器，本地直接启动 REPL 交互对话与用例校验。
                  </p>
                  <code className="block rounded bg-white p-2 text-[11px] font-mono text-indigo-700 border border-slate-200">
                    agentplatform dev .
                  </code>
                </div>

                <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-2">
                  <div className="flex items-center gap-2 font-bold text-xs text-slate-900">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-white text-xs">4</span>
                    一键部署上线
                  </div>
                  <p className="text-[11px] text-slate-500">
                    通过强制准入校验与依赖检查，自动注册入库助手市场。
                  </p>
                  <code className="block rounded bg-white p-2 text-[11px] font-mono text-indigo-700 border border-slate-200">
                    agentplatform deploy . --target http://localhost:8000
                  </code>
                </div>
              </div>

              {/* AI Interaction Protocol */}
              <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-5 space-y-3">
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <span>🤖</span> AI 助手人肉测试与双模式工作流规范
                </h3>
                <p className="text-xs text-slate-600 leading-relaxed">
                  当您使用 Claude Code / Cursor / Antigravity 与 AI 结对开发插件时，AI 默认支持以下暗号协议：
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div className="rounded-lg bg-white p-3 border border-indigo-100">
                    <div className="font-bold text-slate-800">🎯 人肉测试模式（触发词:「我来测」/「开始测试」）</div>
                    <div className="text-slate-500 mt-1">
                      AI 立即进入本插件助手角色，静默调用本地 tools/skills 执行真实对话，不输出任何命令或代码。
                    </div>
                  </div>
                  <div className="rounded-lg bg-white p-3 border border-indigo-100">
                    <div className="font-bold text-slate-800">🛠️ 开发者模式（触发词:「切回开发」/「修 bug」）</div>
                    <div className="text-slate-500 mt-1">
                      AI 恢复为资深研发伙伴，协助编写代码、单测与排查 validate 报错。
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 5: LLM 端点管理 */}
        {/* ========================================================================= */}
        {activeTab === "llm" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 shadow-xs text-xs text-slate-600">
              <span>
                🔑 平台统一维护 OpenAI 兼容格式的大模型网关，API Key 经加密存储。
              </span>
              <button
                type="button"
                onClick={() => setShowAddLlm(true)}
                className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 transition"
              >
                + 添加模型端点
              </button>
            </div>

            {showAddLlm && (
              <div className="rounded-xl border border-indigo-200 bg-indigo-50/40 p-5 shadow-xs">
                <form onSubmit={handleAddEndpoint} className="space-y-4 text-xs">
                  <div className="font-bold text-slate-800">配置新模型端点</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-slate-600 mb-1">端点标识名称</label>
                      <input
                        type="text"
                        required
                        placeholder="例如: deepseek-prod"
                        value={llmForm.name}
                        onChange={(e) => setLlmForm({ ...llmForm, name: e.target.value })}
                        className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 focus:border-indigo-500 focus:outline-hidden"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-600 mb-1">模型名称 (Model Identifier)</label>
                      <input
                        type="text"
                        required
                        placeholder="例如: DeepSeek-V3 或 gpt-4o"
                        value={llmForm.model}
                        onChange={(e) => setLlmForm({ ...llmForm, model: e.target.value })}
                        className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 focus:border-indigo-500 focus:outline-hidden"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-600 mb-1">Base URL (OpenAI 兼容)</label>
                      <input
                        type="text"
                        required
                        placeholder="https://api.openai.com/v1"
                        value={llmForm.base_url}
                        onChange={(e) => setLlmForm({ ...llmForm, base_url: e.target.value })}
                        className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 focus:border-indigo-500 focus:outline-hidden"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-600 mb-1">API Key</label>
                      <input
                        type="password"
                        required
                        placeholder="sk-..."
                        value={llmForm.api_key}
                        onChange={(e) => setLlmForm({ ...llmForm, api_key: e.target.value })}
                        className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 focus:border-indigo-500 focus:outline-hidden"
                      />
                    </div>
                  </div>
                  <div className="flex items-center justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => setShowAddLlm(false)}
                      className="rounded-md px-3 py-1.5 text-slate-600 hover:bg-slate-200"
                    >
                      取消
                    </button>
                    <button
                      type="submit"
                      className="rounded-md bg-indigo-600 px-4 py-1.5 font-semibold text-white hover:bg-indigo-500"
                    >
                      确认创建
                    </button>
                  </div>
                </form>
              </div>
            )}

            {loadingLlm ? (
              <div className="py-12 text-center text-xs text-slate-400">加载端点中...</div>
            ) : endpoints.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-200 bg-white p-12 text-center text-xs text-slate-400">
                暂无自定义模型端点，当前使用系统环境变量默认配置。
              </div>
            ) : (
              <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
                <table className="w-full text-left text-xs text-slate-700">
                  <thead className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-600">
                    <tr>
                      <th className="px-4 py-3">标识</th>
                      <th className="px-4 py-3">Model</th>
                      <th className="px-4 py-3">Base URL</th>
                      <th className="px-4 py-3">默认端点</th>
                      <th className="px-4 py-3 text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {endpoints.map((ep) => (
                      <tr key={ep.id} className="hover:bg-slate-50 transition">
                        <td className="px-4 py-3 font-semibold text-slate-900">{ep.name}</td>
                        <td className="px-4 py-3 font-mono text-slate-600">{ep.model}</td>
                        <td className="px-4 py-3 text-slate-400 font-mono text-[11px]">{ep.base_url}</td>
                        <td className="px-4 py-3">
                          {ep.is_default ? (
                            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 border border-emerald-200">
                              ✓ 默认
                            </span>
                          ) : (
                            <span className="text-slate-400 text-[11px]">-</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {!ep.is_default && (
                            <button
                              type="button"
                              onClick={() => handleSetDefaultLlm(ep.id)}
                              className="rounded px-2 py-1 text-indigo-600 hover:bg-indigo-50 font-medium transition"
                            >
                              设为默认
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Manifest Viewer Modal */}
      {selectedManifest && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-bold text-sm text-slate-900">📄 插件清单详情 (plugin.yaml)</h3>
              <button
                type="button"
                onClick={() => setSelectedManifest(null)}
                className="text-slate-400 hover:text-slate-600 text-sm"
              >
                ✕
              </button>
            </div>
            <pre className="max-h-96 overflow-y-auto rounded-xl bg-slate-950 p-4 text-xs font-mono text-emerald-400">
              {JSON.stringify(selectedManifest, null, 2)}
            </pre>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setSelectedManifest(null)}
                className="rounded-lg bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Schema Viewer Modal */}
      {selectedSchemaRes && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="font-bold text-sm text-slate-900 font-mono">
                  {selectedSchemaRes.id} (v{selectedSchemaRes.version})
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">{selectedSchemaRes.description}</p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedSchemaRes(null)}
                className="text-slate-400 hover:text-slate-600 text-sm"
              >
                ✕
              </button>
            </div>
            <pre className="max-h-96 overflow-y-auto rounded-xl bg-slate-950 p-4 text-xs font-mono text-emerald-400">
              {JSON.stringify(selectedSchemaRes.schema, null, 2)}
            </pre>
            <div className="flex justify-between items-center">
              <code className="text-xs font-mono text-indigo-600 bg-indigo-50 px-2 py-1 rounded border border-indigo-100">
                {selectedSchemaRes.dependency_example}
              </code>
              <button
                type="button"
                onClick={() => setSelectedSchemaRes(null)}
                className="rounded-lg bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
