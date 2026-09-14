"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Navbar } from "../../components/layout/Navbar";
import { KbMembersModal } from "../../components/kb/KbMembersModal";
import { DataSourcesPanel } from "../../components/kb/DataSourcesPanel";
import { isAuthed, getUser } from "../../lib/api/auth";
import {
  createKb,
  deleteDocument,
  deleteKb,
  listDocuments,
  listKbs,
  publishKb,
  retryDocument,
  searchKb,
  uploadDocument,
} from "../../lib/api/kb";
import type {
  KbDocumentInfo,
  KbInfo,
  KbSearchHit,
} from "../../lib/types";

// 可见性展示元数据(设计 008 §12):private 仅自己 / shared owner+成员 / public 全员
const VIS_META: Record<string, { icon: string; label: string; cls: string }> = {
  private: { icon: "🔒", label: "私有", cls: "bg-slate-100 text-slate-500 border-slate-200" },
  shared: { icon: "👥", label: "共享", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  public: { icon: "🌐", label: "公共", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
};

const INTERMEDIATE_STATUSES = new Set(["pending", "parsing", "embedding"]);

const DOC_STATUS_META: Record<string, { label: string; cls: string }> = {
  pending: { label: "排队中", cls: "bg-slate-100 text-slate-600 border-slate-200" },
  parsing: { label: "解析中", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  embedding: { label: "向量化中", cls: "bg-blue-50 text-blue-700 border-blue-200" },
  ready: { label: "已就绪", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  failed: { label: "失败", cls: "bg-rose-50 text-rose-700 border-rose-200" },
  deleted: { label: "已删除", cls: "bg-slate-100 text-slate-400 border-slate-200" },
};

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function KbPage() {
  const router = useRouter();
  const [kbs, setKbs] = useState<KbInfo[]>([]);
  const [selected, setSelected] = useState<KbInfo | null>(null);
  const [docs, setDocs] = useState<KbDocumentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [role, setRole] = useState<string>("user");

  // 新建库表单
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ name: "", slug: "", visibility: "private", description: "" });
  const [creating, setCreating] = useState(false);

  // 文档上传
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);

  // 检索调试框
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchHits, setSearchHits] = useState<KbSearchHit[] | null>(null);
  const [searchHint, setSearchHint] = useState<string | null>(null);

  // 成员管理弹窗(shared 库,设计 008 §12.3)
  const [membersFor, setMembersFor] = useState<KbInfo | null>(null);

  const hasIntermediateDoc = docs.some((d) => INTERMEDIATE_STATUSES.has(d.status));

  useEffect(() => {
    if (!isAuthed()) {
      router.replace("/auth");
      return;
    }
    const u = getUser();
    if (u?.role) setRole(u.role);
    void refreshKbs();
  }, [router]);

  // 选中库后拉文档列表;存在处理中文档时轮询直到全部到达终态
  useEffect(() => {
    if (!selected) {
      setDocs([]);
      return;
    }
    let timer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const poll = async () => {
      try {
        const list = await listDocuments(selected.id);
        if (cancelled) return;
        setDocs(list);
        timer = list.some((d) => INTERMEDIATE_STATUSES.has(d.status))
          ? setTimeout(poll, 2500)
          : null;
      } catch {
        if (!cancelled) timer = setTimeout(poll, 5000);
      }
    };
    void poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [selected]);

  const refreshKbs = async (preferId?: string) => {
    setError(null);
    try {
      setLoading(true);
      const list = await listKbs();
      setKbs(list);
      setSelected((prev) => {
        const targetId = preferId ?? prev?.id;
        return list.find((k) => k.id === targetId) ?? list[0] ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleCreateKb = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      const kb = await createKb({
        name: createForm.name.trim(),
        slug: createForm.slug.trim(),
        visibility: createForm.visibility as "private" | "shared" | "public",
        description: createForm.description.trim() || undefined,
      });
      setShowCreate(false);
      setCreateForm({ name: "", slug: "", visibility: "private", description: "" });
      await refreshKbs(kb.id);
    } catch (err) {
      alert(`创建知识库失败: ${err instanceof Error ? err.message : err}`);
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteKb = async (kb: KbInfo) => {
    if (!confirm(`确定删除知识库「${kb.name}」吗？其下所有文档与片段将一并清除。`)) return;
    try {
      await deleteKb(kb.id);
      await refreshKbs();
    } catch (err) {
      alert(`删除失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const handlePublish = async (kb: KbInfo) => {
    if (!confirm(`将「${kb.name}」发布为公共知识库 (v${kb.version} → 新版本)？所有用户将可挂载检索。`)) return;
    try {
      await publishKb(kb.id);
      await refreshKbs(kb.id);
    } catch (err) {
      alert(`发布失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const handleUpload = async (files: FileList | null) => {
    if (!selected || !files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        await uploadDocument(selected.id, file);
      }
      setDocs(await listDocuments(selected.id));
      await refreshKbs(selected.id);
    } catch (err) {
      alert(`上传失败: ${err instanceof Error ? err.message : err}`);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDeleteDoc = async (doc: KbDocumentInfo) => {
    if (!selected) return;
    if (!confirm(`删除文档「${doc.filename}」？`)) return;
    try {
      await deleteDocument(selected.id, doc.id);
      setDocs(await listDocuments(selected.id));
      await refreshKbs(selected.id);
    } catch (err) {
      alert(`删除失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const handleRetryDoc = async (doc: KbDocumentInfo) => {
    if (!selected) return;
    try {
      await retryDocument(selected.id, doc.id);
      setDocs(await listDocuments(selected.id));
    } catch (err) {
      alert(`重试失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected || !searchQuery.trim()) return;
    setSearching(true);
    setSearchHits(null);
    setSearchHint(null);
    try {
      const resp = await searchKb(selected.id, searchQuery.trim());
      setSearchHits(resp.results);
      setSearchHint(resp.hint ?? null);
    } catch (err) {
      alert(`检索失败: ${err instanceof Error ? err.message : err}`);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Navbar />

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6">
        {/* Header */}
        <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">📚 知识库</h1>
              <span className="rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
                RAG 检索
              </span>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              上传文档（md / txt / pdf）自动切分向量化；会话中挂载后，智能体可通过 <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] text-indigo-600">tool:kb_search</code> 检索引用。
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowCreate(!showCreate)}
            className="self-start rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 transition shadow-xs"
          >
            ＋ 新建知识库
          </button>
        </div>

        {error && (
          <div className="mb-6 rounded-xl bg-red-50 p-4 text-xs text-red-700 border border-red-200 shadow-xs">⚠️ {error}</div>
        )}

        {/* 新建库表单 */}
        {showCreate && (
          <form
            onSubmit={handleCreateKb}
            className="mb-6 rounded-2xl border border-indigo-200 bg-indigo-50/40 p-5 shadow-xs space-y-4 text-xs"
          >
            <div className="font-bold text-slate-800">新建知识库</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label className="block text-slate-600 mb-1">库名称</label>
                <input
                  type="text"
                  required
                  placeholder="例如: 产品手册"
                  value={createForm.name}
                  onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 focus:border-indigo-500 focus:outline-hidden"
                />
              </div>
              <div>
                <label className="block text-slate-600 mb-1">Slug（英文标识，发布后作为 kb:slug）</label>
                <input
                  type="text"
                  required
                  pattern="[a-z][a-z0-9_-]*"
                  title="小写字母开头，仅含小写字母、数字、下划线、连字符"
                  placeholder="product-manual"
                  value={createForm.slug}
                  onChange={(e) => setCreateForm({ ...createForm, slug: e.target.value })}
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 font-mono focus:border-indigo-500 focus:outline-hidden"
                />
              </div>
              <div>
                <label className="block text-slate-600 mb-1">可见性</label>
                <select
                  value={createForm.visibility}
                  onChange={(e) => setCreateForm({ ...createForm, visibility: e.target.value })}
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 focus:border-indigo-500 focus:outline-hidden"
                >
                  <option value="private">私有（仅自己）</option>
                  <option value="shared">共享（owner + 邀请成员）</option>
                  {role === "developer" && <option value="public">公共（所有用户可挂载）</option>}
                </select>
              </div>
              <div>
                <label className="block text-slate-600 mb-1">描述（可选）</label>
                <input
                  type="text"
                  placeholder="知识库用途说明"
                  value={createForm.description}
                  onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 focus:border-indigo-500 focus:outline-hidden"
                />
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="rounded-md px-3 py-1.5 text-slate-600 hover:bg-slate-200"
              >
                取消
              </button>
              <button
                type="submit"
                disabled={creating}
                className="rounded-md bg-indigo-600 px-4 py-1.5 font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {creating ? "创建中..." : "确认创建"}
              </button>
            </div>
          </form>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* 左侧：库列表 */}
          <div className="lg:col-span-4 space-y-3">
            {loading ? (
              <div className="py-16 text-center text-xs text-slate-400">正在加载知识库...</div>
            ) : kbs.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500 shadow-xs">
                <span className="text-3xl block mb-2">📚</span>
                <p className="text-sm font-semibold text-slate-800">暂无知识库</p>
                <p className="mt-1 text-xs text-slate-400">点击右上角「新建知识库」创建第一个库。</p>
              </div>
            ) : (
              kbs.map((kb) => {
                const isSelected = selected?.id === kb.id;
                const vis = VIS_META[kb.visibility] ?? VIS_META.private;
                return (
                  <div
                    key={kb.id}
                    onClick={() => {
                      setSelected(kb);
                      setSearchHits(null);
                      setSearchHint(null);
                    }}
                    className={`cursor-pointer rounded-2xl border p-4 shadow-xs transition ${
                      isSelected
                        ? "border-indigo-300 bg-indigo-50/70 shadow-md"
                        : "border-slate-200 bg-white hover:border-indigo-200 hover:shadow-md"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-base shrink-0">{vis.icon}</span>
                        <span className="truncate text-sm font-bold text-slate-900">{kb.name}</span>
                      </div>
                      <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold border ${vis.cls}`}>
                        {vis.label}
                      </span>
                    </div>
                    <div className="mt-1 font-mono text-[10px] text-slate-400 truncate">
                      kb:{kb.slug} · v{kb.version}
                    </div>
                    {kb.description && (
                      <p className="mt-1.5 text-[11px] text-slate-500 line-clamp-2">{kb.description}</p>
                    )}
                    <div className="mt-2.5 flex items-center gap-3 text-[11px] text-slate-500">
                      <span>📄 {kb.doc_count} 文档</span>
                      <span>🧩 {kb.chunk_count} 片段</span>
                      <span>💾 {fmtSize(kb.size_bytes)}</span>
                    </div>
                    <div className="mt-2.5 pt-2 border-t border-slate-100 flex gap-1.5">
                      {kb.visibility === "shared" ? (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setMembersFor(kb);
                          }}
                          className="rounded-md border border-amber-200 bg-white px-2 py-1 text-[11px] font-medium text-amber-700 hover:bg-amber-50 transition"
                          title="管理共享库成员"
                        >
                          👥 成员
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handlePublish(kb);
                          }}
                          className="rounded-md border border-indigo-200 bg-white px-2 py-1 text-[11px] font-medium text-indigo-700 hover:bg-indigo-50 transition"
                          title="发布为公共库版本，其他用户可挂载"
                        >
                          🚀 发布
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleDeleteKb(kb);
                        }}
                        className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] font-medium text-rose-700 hover:bg-rose-100 transition"
                      >
                        🗑️ 删除
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* 右侧：文档管理 + 检索调试 */}
          <div className="lg:col-span-8 space-y-5">
            {!selected ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center text-xs text-slate-400 shadow-xs">
                ← 请先选择一个知识库
              </div>
            ) : (
              <>
                {/* 数据源(内容型连接器,M13) */}
                <DataSourcesPanel kbId={selected.id} canManage={!!selected.can_manage} onChanged={() => void refreshKbs(selected.id)} />

                {/* 文档列表 */}
                <div className="rounded-2xl border border-slate-200 bg-white shadow-xs">
                  <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-slate-900">📄 文档管理</span>
                      <span className="text-[11px] text-slate-400">{selected.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {hasIntermediateDoc && (
                        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-indigo-600 animate-pulse">
                          <span className="h-1.5 w-1.5 rounded-full bg-indigo-600 animate-ping" />
                          处理中
                        </span>
                      )}
                      <input
                        ref={fileInputRef}
                        type="file"
                        multiple
                        accept=".md,.markdown,.txt,.pdf,text/markdown,text/plain,application/pdf"
                        className="hidden"
                        onChange={(e) => void handleUpload(e.target.files)}
                      />
                      <button
                        type="button"
                        disabled={uploading}
                        onClick={() => fileInputRef.current?.click()}
                        className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 transition disabled:opacity-50"
                      >
                        {uploading ? "上传中..." : "⬆️ 上传文档"}
                      </button>
                    </div>
                  </div>

                  {docs.length === 0 ? (
                    <div className="p-10 text-center text-xs text-slate-400">
                      暂无文档，点击「上传文档」添加 md / txt / pdf 文件
                    </div>
                  ) : (
                    <table className="w-full text-left text-xs text-slate-700">
                      <thead className="border-b border-slate-200 bg-slate-50/80 text-[11px] font-semibold text-slate-600">
                        <tr>
                          <th className="px-5 py-3">文件名</th>
                          <th className="px-4 py-3">大小</th>
                          <th className="px-4 py-3">创建时间</th>
                          <th className="px-4 py-3">状态</th>
                          <th className="px-5 py-3 text-right">操作</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {docs.map((doc) => {
                          const meta = DOC_STATUS_META[doc.status] ?? DOC_STATUS_META.pending;
                          return (
                            <tr key={doc.id} className="hover:bg-slate-50/70 transition align-top">
                              <td className="px-5 py-3">
                                <div className="flex items-center gap-1.5">
                                  <span className="font-semibold text-slate-900 max-w-xs truncate">{doc.filename}</span>
                                  {doc.origin === "session" && (
                                    <span
                                      className="shrink-0 rounded bg-violet-50 border border-violet-200 px-1.5 py-0.2 text-[9px] font-medium text-violet-700"
                                      title={doc.source_app ? `来源应用: ${doc.source_app}` : "会话产出"}
                                    >
                                      会话{doc.source_app ? `·${doc.source_app}` : ""}
                                    </span>
                                  )}
                                  {doc.origin === "connector" && (
                                    <a
                                      href={doc.external_url ?? undefined}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="shrink-0 rounded bg-sky-50 border border-sky-200 px-1.5 py-0.2 text-[9px] font-medium text-sky-700 hover:bg-sky-100"
                                      title={doc.external_url ? `来自数据源 ${doc.source_app ?? ""}，点击打开原文` : "连接器同步"}
                                    >
                                      🔗{doc.source_app ?? "连接器"}
                                    </a>
                                  )}
                                </div>
                                <div className="font-mono text-[10px] text-slate-400">{doc.mime}</div>
                                {doc.status === "failed" && doc.error && (
                                  <div className="mt-1 rounded bg-rose-50 border border-rose-100 px-2 py-1 text-[10px] text-rose-700 max-w-xs break-words">
                                    {doc.error}
                                  </div>
                                )}
                              </td>
                              <td className="px-4 py-3 text-slate-500">{fmtSize(doc.size_bytes)}</td>
                              <td className="px-4 py-3 text-slate-500 text-[11px]">
                                {doc.created_at ? new Date(doc.created_at).toLocaleString("zh-CN") : "-"}
                              </td>
                              <td className="px-4 py-3">
                                <span
                                  className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${meta.cls}`}
                                  title={
                                    doc.status === "ready"
                                      ? "解析、切分、向量化均已完成，可被智能体检索引用"
                                      : doc.status === "pending"
                                        ? "已入库，等待后台处理"
                                        : doc.status === "parsing"
                                          ? "正在解析原文"
                                          : doc.status === "embedding"
                                            ? "正在调用 embedding 模型向量化"
                                            : doc.status === "failed"
                                              ? "处理失败，可重试"
                                              : undefined
                                  }
                                >
                                  {meta.label}
                                </span>
                              </td>
                              <td className="px-5 py-3 text-right space-x-1.5">
                                {doc.status === "failed" && (
                                  <button
                                    type="button"
                                    onClick={() => void handleRetryDoc(doc)}
                                    className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1 text-slate-700 hover:bg-amber-100 transition"
                                  >
                                    重试
                                  </button>
                                )}
                                <button
                                  type="button"
                                  onClick={() => void handleDeleteDoc(doc)}
                                  className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1 text-rose-700 hover:bg-rose-100 transition"
                                >
                                  删除
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>

                {/* 检索调试 */}
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-3">
                  <div className="text-sm font-bold text-slate-900">🔍 检索调试</div>
                  <p className="text-[11px] text-slate-500">
                    与智能体的 tool:kb_search 走同一条检索链路，可先用它验证向量质量。
                  </p>
                  <form onSubmit={handleSearch} className="flex gap-2">
                    <input
                      type="text"
                      placeholder="输入检索问题，例如: 平台的消息信封是什么结构？"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-indigo-500 focus:outline-hidden"
                    />
                    <button
                      type="submit"
                      disabled={searching || !searchQuery.trim()}
                      className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
                    >
                      {searching ? "检索中..." : "检索"}
                    </button>
                  </form>

                  {searchHint && (
                    <div className="rounded-lg bg-amber-50 border border-amber-200 p-2.5 text-[11px] text-amber-800">
                      💡 {searchHint}
                    </div>
                  )}
                  {searchHits && searchHits.length > 0 && (
                    <div className="space-y-2">
                      {searchHits.map((hit, i) => (
                        <div key={i} className="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
                          <div className="flex items-center justify-between gap-2 text-[11px]">
                            <span className="font-semibold text-slate-700 truncate">
                              {hit.document_name} · chunk #{hit.chunk_index}
                            </span>
                            <span className="shrink-0 rounded-full bg-indigo-50 border border-indigo-200 px-2 py-0.5 font-mono text-[10px] font-semibold text-indigo-700">
                              score {hit.score}
                            </span>
                          </div>
                          <p className="mt-1.5 text-xs text-slate-600 leading-relaxed line-clamp-4 whitespace-pre-wrap">
                            {hit.text}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </main>

      {membersFor && (
        <KbMembersModal
          kbId={membersFor.id}
          kbName={membersFor.name}
          onClose={() => setMembersFor(null)}
          onChanged={() => void refreshKbs(membersFor.id)}
        />
      )}
    </div>
  );
}
