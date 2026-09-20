"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "../../components/layout/Navbar";

/** 系统诊断页(产品打磨①):一键体检——部署排障 30 秒定位。 */

interface Check {
  name: string;
  ok: boolean;
  latency_ms: number | null;
  detail: string;
}

const META: Record<string, { icon: string; label: string; fix: string }> = {
  database: { icon: "🐘", label: "数据库", fix: "docker compose up -d pg" },
  redis: { icon: "⚡", label: "缓存", fix: "docker compose up -d redis" },
  llm: { icon: "🧠", label: "LLM 网关", fix: "检查 OPENAI_BASE_URL/OPENAI_API_KEY" },
  embedding: { icon: "🔢", label: "向量化", fix: "管理台添加 embedding 端点(如 Ollama bge-m3)" },
  search: { icon: "🔍", label: "联网搜索", fix: "WEB_SEARCH_PROVIDER=searxng + SEARXNG_BASE_URL" },
  scheduler: { icon: "⏰", label: "任务调度器", fix: "重启 api 容器(单副本常驻)" },
};

export default function StatusPage() {
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setChecks(null);
    setError(null);
    try {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api"}/diagnostics`
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setChecks(await resp.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    void run();
  }, []);

  const allOk = checks?.every((c) => c.ok) ?? false;

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <div className="mx-auto max-w-2xl px-4 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-900">🩺 系统诊断</h1>
            <p className="mt-1 text-xs text-slate-400">部署排障:逐项探测关键依赖连通性</p>
          </div>
          <button
            type="button"
            onClick={() => void run()}
            className="rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800"
          >
            重新检查
          </button>
        </div>

        {checks && (
          <div
            className={`mb-4 rounded-2xl border p-4 text-center text-sm font-semibold ${
              allOk
                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : "border-amber-200 bg-amber-50 text-amber-700"
            }`}
          >
            {allOk ? "✅ 全部正常" : `⚠️ ${checks.filter((c) => !c.ok).length} 项异常`}
          </div>
        )}

        {error && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
            诊断接口不可达:{error}(后端未启动?)
          </div>
        )}

        {!checks && !error && <div className="py-16 text-center text-sm text-slate-400">检测中...</div>}

        <div className="space-y-2">
          {checks?.map((c) => {
            const m = META[c.name] ?? { icon: "🔧", label: c.name, fix: "查看文档" };
            return (
              <div
                key={c.name}
                className={`rounded-2xl border p-4 ${c.ok ? "border-slate-200 bg-white" : "border-rose-200 bg-rose-50"}`}
              >
                <div className="flex items-center gap-3">
                  <span className="text-lg">{m.icon}</span>
                  <span className="text-sm font-semibold text-slate-900">{m.label}</span>
                  <span className={`text-xs font-bold ${c.ok ? "text-emerald-600" : "text-rose-600"}`}>
                    {c.ok ? "✓ 正常" : "✗ 异常"}
                  </span>
                  {c.ok && c.latency_ms != null && (
                    <span className="ml-auto font-mono text-[10px] text-slate-400">{c.latency_ms}ms</span>
                  )}
                </div>
                <div className="mt-1 pl-9 text-xs text-slate-500">{c.detail}</div>
                {!c.ok && (
                  <div className="mt-2 ml-9 rounded-lg bg-white/70 px-3 py-1.5 text-[11px] text-slate-500">
                    💡 修复建议:<code className="font-mono">{m.fix}</code>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
