"use client";

import React, { useState } from "react";
import { ContentBlock } from "../../../lib/types";

export function TableRenderer({ block }: { block: ContentBlock }) {
  const columns: (string | { key: string; label: string })[] =
    block.data?.columns ?? block.data?.headers ?? [];
  const rawRows: any[] = block.data?.rows ?? [];

  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(true);

  const colDefs = columns.map((col, idx) =>
    typeof col === "string"
      ? { key: col, label: col, index: idx }
      : { ...col, index: idx }
  );

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const rows = [...rawRows].sort((a, b) => {
    if (!sortKey) return 0;
    const targetCol = colDefs.find((c) => c.key === sortKey);
    const colIdx = targetCol ? targetCol.index : -1;
    const va = Array.isArray(a) ? (colIdx >= 0 ? a[colIdx] ?? "" : "") : a[sortKey] ?? "";
    const vb = Array.isArray(b) ? (colIdx >= 0 ? b[colIdx] ?? "" : "") : b[sortKey] ?? "";
    if (va < vb) return sortAsc ? -1 : 1;
    if (va > vb) return sortAsc ? 1 : -1;
    return 0;
  });

  return (
    <div className="my-3 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      {block.data?.title && (
        <div className="border-b border-slate-200 bg-slate-50 px-3.5 py-2 text-xs font-semibold text-slate-700">
          {block.data.title}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-700">
          <thead className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-600">
            <tr>
              {colDefs.map((c) => (
                <th
                  key={c.key}
                  onClick={() => handleSort(c.key)}
                  className="cursor-pointer px-3.5 py-2.5 hover:bg-slate-100 transition select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>{c.label}</span>
                    {sortKey === c.key && (
                      <span className="text-slate-400">
                        {sortAsc ? "▲" : "▼"}
                      </span>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r, i) => (
              <tr
                key={i}
                className={i % 2 === 0 ? "bg-white hover:bg-slate-50" : "bg-slate-50/50 hover:bg-slate-100/50"}
              >
                {colDefs.map((c) => {
                  const val = Array.isArray(r) ? r[c.index] : r?.[c.key];
                  return (
                    <td key={c.key} className="px-3.5 py-2 whitespace-nowrap">
                      {val !== undefined && val !== null ? String(val) : ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
