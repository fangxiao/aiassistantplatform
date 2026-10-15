"use client";

// Mermaid 图表渲染(20261015 工单 20261015-1539-e50fd0):
// ```mermaid 代码块 → 矢量 SVG;失败平滑降级为源码 + 异常提示。
// 动态 import——mermaid 体积大,不进首屏 bundle;安全用 strict 沙箱。

import React, { useEffect, useRef, useState } from "react";

let mermaidReady: Promise<typeof import("mermaid").default> | null = null;

function loadMermaid() {
  if (!mermaidReady) {
    mermaidReady = import("mermaid").then((m) => {
      const mermaid = m.default;
      mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
      return mermaid;
    });
  }
  return mermaidReady;
}

export function MermaidBlock({ code }: { code: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const counter = useRef(0);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    loadMermaid()
      .then(async (mermaid) => {
        counter.current += 1;
        const id = `mermaid-${Date.now()}-${counter.current}`;
        const { svg: out } = await mermaid.render(id, code);
        if (!cancelled) setSvg(out);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (failed) {
    return (
      <div className="my-2 overflow-hidden rounded-lg border border-amber-200 bg-amber-50">
        <div className="border-b border-amber-200 px-3 py-1.5 text-[11px] text-amber-700">
          📊 图表渲染异常,以下为原始定义
        </div>
        <pre className="overflow-x-auto p-3 text-xs text-slate-700">
          <code>{code}</code>
        </pre>
      </div>
    );
  }

  if (svg === null) {
    return (
      <div className="my-2 flex items-center justify-center rounded-lg border border-slate-200 bg-slate-50 py-6 text-xs text-slate-400">
        📊 图表渲染中…
      </div>
    );
  }

  return (
    <div
      className="my-2 overflow-x-auto rounded-lg border border-slate-200 bg-white p-3"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
