"use client";

import React from "react";
import type { ContentBlock } from "../../../lib/types";

/** MetricStatBlock 渲染器(M38/RFC-05 组件 B):通用指标看板卡片。
 *  大数值 + 趋势(↑↓) + 变化率 + 状态色。 */

interface MetricStatData {
  label: string;
  value: string | number;
  unit?: string;
  sub_label?: string;
  trend?: "up" | "down" | "flat";
  change_rate?: string;
  status?: "success" | "warning" | "error" | "info";
}

const STATUS_CLS: Record<string, { text: string; bg: string }> = {
  success: { text: "text-emerald-600", bg: "bg-emerald-50" },
  warning: { text: "text-amber-600", bg: "bg-amber-50" },
  error: { text: "text-rose-600", bg: "bg-rose-50" },
  info: { text: "text-indigo-600", bg: "bg-indigo-50" },
};

const TREND_ICON: Record<string, string> = {
  up: "↑",
  down: "↓",
  flat: "→",
};

export function MetricStatRenderer({ block }: { block: ContentBlock }) {
  const data = (block.data ?? {}) as MetricStatData;
  const cls = STATUS_CLS[data.status ?? "info"] ?? STATUS_CLS.info;
  const trendIcon = data.trend ? TREND_ICON[data.trend] : "";

  return (
    <div className={`rounded-xl border border-slate-200 ${cls.bg} p-4`}>
      <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{data.label}</p>
      <div className="mt-1 flex items-baseline gap-1">
        <span className={`text-2xl font-black ${cls.text}`}>
          {typeof data.value === "number" ? data.value.toLocaleString() : data.value}
        </span>
        {data.unit && <span className="text-xs text-slate-400">{data.unit}</span>}
        {data.change_rate && (
          <span
            className={`ml-2 text-xs font-semibold ${
              data.trend === "down" ? "text-emerald-500" : data.trend === "up" ? "text-rose-500" : "text-slate-400"
            }`}
          >
            {trendIcon} {data.change_rate}
          </span>
        )}
      </div>
      {data.sub_label && <p className="mt-1 text-[10px] text-slate-400">{data.sub_label}</p>}
    </div>
  );
}
