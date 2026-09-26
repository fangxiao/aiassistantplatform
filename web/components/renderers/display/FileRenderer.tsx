"use client";

import React, { useEffect, useState } from "react";
import { ContentBlock } from "../../../lib/types";
import { API_BASE, getAuthHeader } from "../../../lib/api/client";

function formatSize(bytes?: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FileRenderer({ block }: { block: ContentBlock }) {
  const rawPath = String(
    block.data?.path ?? block.data?.filepath ?? block.data?.url ?? ""
  );
  const name = String(
    block.data?.name ??
      block.data?.filename ??
      rawPath.split("/").pop() ??
      "附件文件"
  );
  const size = block.data?.size ? Number(block.data.size) : undefined;
  const mime = block.data?.mime ? String(block.data.mime) : "";
  const isHtml =
    name.toLowerCase().endsWith(".html") ||
    name.toLowerCase().endsWith(".htm") ||
    mime.includes("html");

  const [copied, setCopied] = useState(false);

  // 文件链接需要鉴权(Bearer),而 <a> 新标签页无法携带请求头——
  // 统一改为:带鉴权 fetch 内容 → blob object URL 供打开/下载;
  // 顺带修复 NEXT_PUBLIC_API_BASE=/api 时拼出 /api/api/files/raw 的 404。
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const backendBase = API_BASE;
  let previewUrl = rawPath;
  let downloadUrl = rawPath;

  if (rawPath && !rawPath.startsWith("http://") && !rawPath.startsWith("https://")) {
    previewUrl = `${backendBase}/files/raw?path=${encodeURIComponent(rawPath)}`;
    downloadUrl = `${backendBase}/files/download?path=${encodeURIComponent(rawPath)}`;
  }

  const needsAuthFetch = Boolean(
    rawPath && !rawPath.startsWith("http://") && !rawPath.startsWith("https://")
  );

  useEffect(() => {
    if (!needsAuthFetch) return;
    let revoked: string | null = null;
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch(previewUrl, { headers: getAuthHeader() });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        // 显式指定 charset:HTML 无 <meta charset> 时,部分浏览器对 blob 会猜错编码导致乱码
        const buf = await resp.arrayBuffer();
        const ctype = resp.headers.get("content-type") ?? "application/octet-stream";
        const isHtmlFile = /\.(html?|htm)$/i.test(rawPath) || ctype.includes("html");
        const type = isHtmlFile && !/charset/i.test(ctype) ? "text/html;charset=utf-8" : ctype;
        const blob = new Blob([buf], { type });
        if (cancelled) {
          URL.revokeObjectURL(URL.createObjectURL(blob));
          return;
        }
        revoked = URL.createObjectURL(blob);
        setBlobUrl(revoked);
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "加载失败");
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsAuthFetch, previewUrl]);

  const handleCopyPath = () => {
    if (!rawPath) return;
    navigator.clipboard.writeText(rawPath);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-3 max-w-lg rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-slate-300 transition">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 overflow-hidden">
          <div
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl font-bold text-lg ${
              isHtml
                ? "bg-emerald-50 text-emerald-600 border border-emerald-200"
                : "bg-blue-50 text-blue-600 border border-blue-200"
            }`}
          >
            {isHtml ? "🌐" : "📄"}
          </div>
          <div className="overflow-hidden">
            <div className="flex items-center gap-2">
              <p className="truncate text-xs font-bold text-slate-800" title={name}>
                {name}
              </p>
              {isHtml && (
                <span className="rounded bg-emerald-50 px-1.5 py-0.2 text-[10px] font-medium text-emerald-700 border border-emerald-200">
                  HTML网页
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5 truncate" title={rawPath}>
              {rawPath || (formatSize(size) ? `${formatSize(size)} ${mime && `· ${mime}`}` : "本地生成文件")}
            </p>
          </div>
        </div>
      </div>

      {/* 快捷操作动作条 */}
      <div className="mt-3.5 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3 text-xs">
        {needsAuthFetch && loadError && (
          <span className="rounded bg-rose-50 px-2 py-1 text-rose-700 border border-rose-200">
            ⚠️ 文件加载失败: {loadError}
          </span>
        )}
        {needsAuthFetch && !blobUrl && !loadError && (
          <span className="rounded bg-slate-50 px-2 py-1 text-slate-500">文件加载中...</span>
        )}
        {isHtml && (rawPath.startsWith("http") ? Boolean(previewUrl) : Boolean(blobUrl)) && (
          <a
            href={blobUrl ?? previewUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 font-medium text-white shadow-2xs hover:bg-emerald-700 transition"
          >
            <span>🚀 浏览器直接打开</span>
          </a>
        )}

        {(rawPath.startsWith("http") ? Boolean(downloadUrl) : Boolean(blobUrl)) && (
          <a
            href={blobUrl ?? downloadUrl}
            download={name}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-200 transition"
          >
            <span>📥 下载文件</span>
          </a>
        )}

        {rawPath && (
          <button
            type="button"
            onClick={handleCopyPath}
            className="inline-flex items-center gap-1 rounded-lg bg-slate-50 border border-slate-200 px-2.5 py-1.5 font-medium text-slate-600 hover:bg-slate-100 transition"
          >
            <span>{copied ? "✅ 路径已复制" : "📋 复制本地路径"}</span>
          </button>
        )}
      </div>
    </div>
  );
}
