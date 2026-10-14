"use client";

import React from "react";
import type { ContentBlock } from "../../../lib/types";

/** WaterfallBlock 渲染器(M38/RFC-05 组件 A):时序调用瀑布流。
 *  每个 span 按时间偏移水平排列,颜色区分成功/失败/警告。 */

interface Span {
  id: string;
  name: string;
  start_ms: number;
  duration_ms: number;
  status: "success" | "failed" | "warning" | "running";
  error_code?: string;
}

interface WaterfallData {
  title?: string;
  total_duration_ms?: number;
  spans: Span[];
}

const STATUS_COLOR: Record<Span["status"], string> = {
  success: "bg-emerald-400",
  failed: "bg-rose-500",
  warning: "bg-amber-400",
  running: "bg-indigo-400 animate-pulse",
};

function fmtMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function WaterfallRenderer({ block }: { block: ContentBlock }) {
  const data = (block.data ?? {}) as WaterfallData;
  const spans = data.spans ?? [];
  const total = data.total_duration_ms ?? Math.max(...spans.map((s) => s.start_ms + s.duration_ms), 0);

  if (!spans.length) return null;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      {data.title && (
        <div className="mb-3 flex items-baseline justify-between">
          <span className="text-xs font-bold text-slate-800">📊 {data.title}</span>
          <span className="text-[10px] font-mono text-slate-400">总计 {fmtMs(total)}</span>
        </div>
      )}
      <div className="space-y-1">
        {spans.map((span) => {
          const leftPct = total > 0 ? (span.start_ms / total) * 100 : 0;
          const widthPct = total > 0 ? Math.max((span.duration_ms / total) * 100, 1.5) : 1.5;
          return (
            <div key={span.id} className="group flex items-center gap-2 text-[10px]">
              <span className="w-32 shrink-0 truncate text-right font-mono text-slate-500" title={span.name}>
                {span.name}
              </span>
              <div className="relative h-4 flex-1 rounded bg-slate-50">
                <div
                  className={`absolute top-0.5 h-3 rounded ${STATUS_COLOR[span.status] ?? "bg-slate-300"} transition-all`}
                  style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                  title={`${span.name}: ${fmtMs(span.duration_ms)} (${span.status})`}
                />
              </div>
              <span className="w-12 shrink-0 font-mono text-slate-400">{fmtMs(span.duration_ms)}</span>
              {span.status === "failed" && span.error_code && (
                <span className="shrink-0 rounded bg-rose-50 px-1 text-[9px] font-medium text-rose-600">
                  {span.error_code}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
