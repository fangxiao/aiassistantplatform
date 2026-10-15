"use client";

/** 我的文件(20261015):用户上传过的全部附件,一键转存知识库。
 *  - 公共库(有写权限)或个人默认库(建/复用「我的知识库」,随对话自动挂载)
 *  - 工作台汇总模式限 5 条 + 查看全部;专属页 /files 全量 */

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiPost } from "../../lib/api/client";
import { Card } from "./WorkbenchView";

interface MyFile {
  id: string;
  name: string;
  size: number;
  mime: string;
  url: string;
  created_at: string;
}

interface KbOption {
  id: string;
  name: string;
  visibility: string;
  can_write: boolean;
  personal_default: boolean;
}

const fmtSize = (n: number) =>
  n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)}MB` : `${Math.ceil(n / 1024)}KB`;

const fmtTime = (iso: string) => {
  const d = new Date(iso);
  return `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

export function MyFilesCard({ full = false }: { full?: boolean }) {
  const [files, setFiles] = useState<MyFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [ingestTarget, setIngestTarget] = useState<MyFile | null>(null);
  const [kbs, setKbs] = useState<KbOption[]>([]);
  const [selectedKb, setSelectedKb] = useState<string>("__personal__");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setFiles(await apiGet<MyFile[]>("/files/mine"));
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

  const openIngest = async (f: MyFile) => {
    setIngestTarget(f);
    setMsg(null);
    try {
      const all = await apiGet<KbOption[]>("/kb/kbs");
      setKbs(all.filter((k) => k.can_write));
    } catch {
      setKbs([]); // 库列表拉不到时仍可走「我的知识库」
    }
  };

  const doIngest = async () => {
    if (!ingestTarget) return;
    setBusy(true);
    try {
      const r = await apiPost<{ kb_name: string; personal_default: boolean }>(
        `/files/${ingestTarget.id}/ingest`,
        { kb_id: selectedKb === "__personal__" ? null : selectedKb },
      );
      setMsg(
        r.personal_default
          ? `✅ 已入库「${r.kb_name}」(随对话自动挂载,今后每次对话都可检索)`
          : `✅ 已入库「${r.kb_name}」`,
      );
      setIngestTarget(null);
    } catch (err) {
      setMsg(`❌ ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(false);
    }
  };

  const shown = full ? files : files.slice(0, 5);

  return (
    <Card title="📁 我的文件" moreLink={full ? undefined : "/files"}>
      {loading && <p className="py-2 text-center text-xs text-slate-400">加载中…</p>}
      {error && <p className="py-2 text-center text-xs text-rose-500">{error}</p>}
      {msg && (
        <p className="mb-2 rounded-lg border border-slate-100 bg-slate-50 px-2.5 py-1.5 text-[11px] text-slate-600">
          {msg}
        </p>
      )}
      {shown.length === 0 && !loading && (
        <p className="py-3 text-center text-xs text-slate-400">
          还没有上传过文件——对话里点 📎 或粘贴图片,传过的都在这里
        </p>
      )}
      {shown.length > 0 && (
        <div className="flex flex-col divide-y divide-slate-50">
          {shown.map((f) => (
            <div key={f.id} className="flex items-center gap-2 py-1.5">
              <span className="truncate text-xs font-medium text-slate-800" title={f.name}>
                {f.mime.startsWith("image/") ? "🖼️" : "📄"} {f.name}
              </span>
              <span className="ml-auto shrink-0 font-mono text-[10px] text-slate-400">
                {fmtSize(f.size)} · {fmtTime(f.created_at)}
              </span>
              <a
                href={f.url}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 text-[10px] text-slate-400 hover:text-indigo-600"
                title="预览"
              >
                预览
              </a>
              {/* 知识库管道仅收文档(docx/md/pdf/txt/xlsx);图片不可入库 */}
              {!f.mime.startsWith("image/") && (
                <button
                  type="button"
                  onClick={() => void openIngest(f)}
                  className="shrink-0 rounded-md border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[10px] font-medium text-indigo-600 hover:bg-indigo-100"
                  title="转存知识库,供助手长期检索"
                >
                  ⬆️ 入库
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {ingestTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setIngestTarget(null)}>
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-bold text-slate-800">⬆️ 入库:{ingestTarget.name}</h3>
            <p className="mt-1 text-[11px] text-slate-400">入库后助手可长期检索该文件内容</p>
            <div className="mt-4 space-y-2">
              <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-slate-200 p-3 hover:border-indigo-300">
                <input
                  type="radio"
                  checked={selectedKb === "__personal__"}
                  onChange={() => setSelectedKb("__personal__")}
                />
                <div>
                  <div className="text-xs font-medium text-slate-800">🔒 我的知识库(个人)</div>
                  <div className="text-[10px] text-slate-400">
                    仅自己可见;随对话自动挂载,今后所有助手都能检索(可关)
                  </div>
                </div>
              </label>
              {kbs.filter((k) => k.visibility !== "private").map((k) => (
                <label key={k.id} className="flex cursor-pointer items-center gap-2 rounded-xl border border-slate-200 p-3 hover:border-indigo-300">
                  <input
                    type="radio"
                    checked={selectedKb === k.id}
                    onChange={() => setSelectedKb(k.id)}
                  />
                  <div className="min-w-0">
                    <div className="truncate text-xs font-medium text-slate-800">
                      {k.visibility === "public" ? "🌐" : "👥"} {k.name}
                    </div>
                  </div>
                </label>
              ))}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setIngestTarget(null)}
                className="rounded-lg border border-slate-200 px-4 py-1.5 text-xs text-slate-600"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void doIngest()}
                disabled={busy}
                className="rounded-lg bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-40"
              >
                {busy ? "入库中…" : "确认入库"}
              </button>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
