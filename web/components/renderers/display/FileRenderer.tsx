"use client";

import React from "react";
import { ContentBlock } from "../../../lib/types";

function formatSize(bytes?: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FileRenderer({ block }: { block: ContentBlock }) {
  const name = String(block.data?.name ?? block.data?.filename ?? "附件文件");
  const url = block.data?.url ? String(block.data.url) : "#";
  const size = block.data?.size ? Number(block.data.size) : undefined;
  const mime = block.data?.mime ? String(block.data.mime) : "";

  return (
    <div className="my-2 flex items-center justify-between max-w-sm rounded-lg border border-slate-200 bg-white p-3 shadow-sm hover:border-slate-300 transition">
      <div className="flex items-center gap-3 overflow-hidden">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600 font-bold text-sm">
          📁
        </div>
        <div className="overflow-hidden">
          <p className="truncate text-xs font-semibold text-slate-800">{name}</p>
          <p className="text-[11px] text-slate-400">
            {formatSize(size)} {mime && `· ${mime}`}
          </p>
        </div>
      </div>
      <a
        href={url}
        download={name}
        target="_blank"
        rel="noreferrer"
        className="ml-3 shrink-0 rounded bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-200 transition"
      >
        下载
      </a>
    </div>
  );
}
