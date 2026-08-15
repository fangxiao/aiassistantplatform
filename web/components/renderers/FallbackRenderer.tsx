"use client";

import React, { useState } from "react";
import { ContentBlock } from "../../lib/types";

interface FallbackRendererProps {
  block: ContentBlock;
  reason?: string;
}

export function FallbackRenderer({ block, reason }: FallbackRendererProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="my-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 shadow-sm">
      <div
        className="flex cursor-pointer items-center justify-between font-medium text-amber-800"
        onClick={() => setOpen(!open)}
      >
        <div className="flex items-center gap-1.5">
          <span className="text-amber-600">⚠️</span>
          <span>
            组件降级显示: <code className="rounded bg-amber-100 px-1 py-0.5 font-mono">{block.type}</code>
          </span>
          {reason && <span className="text-amber-600">({reason})</span>}
        </div>
        <span className="text-[10px] text-amber-600 underline">
          {open ? "收起数据" : "查看原始数据"}
        </span>
      </div>
      {open && (
        <pre className="mt-2 max-h-48 overflow-auto rounded bg-white p-2 font-mono text-[11px] text-slate-700 border border-amber-200">
          {JSON.stringify(block.data, null, 2)}
        </pre>
      )}
    </div>
  );
}
