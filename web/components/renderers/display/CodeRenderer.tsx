"use client";

import React, { useState } from "react";
import { ContentBlock } from "../../../lib/types";

export function CodeRenderer({ block }: { block: ContentBlock }) {
  const [copied, setCopied] = useState(false);
  const lang = String(block.data?.lang ?? "text");
  const source = String(block.data?.source ?? block.data?.code ?? "");
  const filename = block.data?.filename ? String(block.data.filename) : null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(source);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
    }
  };

  return (
    <div className="my-3 overflow-hidden rounded-lg border border-slate-700 bg-slate-900 text-xs shadow-md">
      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950 px-3.5 py-1.5 text-slate-400">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-slate-600" />
          <span className="font-mono font-medium text-slate-300">
            {filename ?? lang}
          </span>
        </div>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 rounded px-2 py-0.5 text-[11px] text-slate-300 hover:bg-slate-800 transition"
        >
          {copied ? (
            <span className="text-emerald-400">✓ 已复制</span>
          ) : (
            <span>复制</span>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-3.5 font-mono leading-relaxed text-slate-100">
        <code>{source}</code>
      </pre>
    </div>
  );
}
