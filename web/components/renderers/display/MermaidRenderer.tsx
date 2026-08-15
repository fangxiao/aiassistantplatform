"use client";

import React, { useState } from "react";
import { ContentBlock } from "../../../lib/types";

export function MermaidRenderer({ block }: { block: ContentBlock }) {
  const [showCode, setShowCode] = useState(false);
  const source = String(block.data?.source ?? block.data?.code ?? "");
  const caption = block.data?.caption ? String(block.data.caption) : null;

  return (
    <div className="my-3 overflow-hidden rounded-lg border border-indigo-200 bg-indigo-50/40 p-3 shadow-sm">
      <div className="flex items-center justify-between border-b border-indigo-100 pb-2 text-xs text-indigo-900 font-medium">
        <div className="flex items-center gap-1.5">
          <span>📊 图表渲染 (Mermaid)</span>
          {caption && <span className="text-slate-500 font-normal">· {caption}</span>}
        </div>
        <button
          type="button"
          onClick={() => setShowCode(!showCode)}
          className="rounded px-2 py-0.5 text-[11px] text-indigo-600 hover:bg-indigo-100 transition"
        >
          {showCode ? "折叠源码" : "查看源码"}
        </button>
      </div>

      <div className="my-3 flex justify-center overflow-x-auto rounded bg-white p-4 border border-indigo-100">
        <pre className="font-mono text-xs text-slate-700 leading-relaxed whitespace-pre-wrap">
          {source}
        </pre>
      </div>

      {showCode && (
        <pre className="mt-2 max-h-40 overflow-auto rounded bg-slate-900 p-2 font-mono text-[11px] text-slate-200">
          <code>{source}</code>
        </pre>
      )}
    </div>
  );
}
