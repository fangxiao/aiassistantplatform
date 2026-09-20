"use client";

import React, { useEffect, useState } from "react";
import { apiGet } from "../../lib/api/client";

/** 开发者中心「洞察」面板(产品成熟度①②):成本汇总 + 平台总览 + 用户管理。 */

interface CostSummary {
  total_tokens: number;
  chat_tokens: number;
  task_tokens: number;
  last_7d_tokens: number;
  by_day: { date: string; tokens: number }[];
  by_assistant: { name: string; tokens: number; sessions: number }[];
  by_task: { name: string; tokens: number; runs: number }[];
}

interface AdminUser {
  id: string;
  email: string;
  role: string;
  created_at: string;
  session_count: number;
  message_tokens: number;
  task_count: number;
}

interface ActionLog {
  id: string;
  user_id: string;
  method: string;
  url: string;
  outcome: string;
  status_code: number | null;
  detail: string | null;
  created_at: string;
}

interface Overview {
  users: number;
  sessions: number;
  assistants: number;
  knowledge_bases: number;
  scheduled_tasks_active: number;
  documents_ready: number;
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function InsightsPanel() {
  const [costs, setCosts] = useState<CostSummary | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [actions, setActions] = useState<ActionLog[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [c, o, u, a] = await Promise.all([
          apiGet<CostSummary>("/insights/costs?days=30"),
          apiGet<Overview>("/insights/admin/overview"),
          apiGet<AdminUser[]>("/insights/admin/users"),
          apiGet<ActionLog[]>("/insights/actions?limit=30"),
        ]);
        setCosts(c);
        setOverview(o);
        setUsers(u);
        setActions(a);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes("403")) setForbidden(true);
        else setError(msg);
      }
    })();
  }, []);

  if (forbidden) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-400">
        洞察面板仅对 developer 角色开放
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">⚠️ {error}</div>
    );
  }

  const maxDay = Math.max(1, ...(costs?.by_day || []).map((d) => d.tokens));

  return (
    <div className="space-y-6">
      {/* 平台总览 */}
      {overview && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {[
            { label: "用户", value: overview.users, icon: "👤" },
            { label: "会话", value: overview.sessions, icon: "💬" },
            { label: "助手", value: overview.assistants, icon: "🤖" },
            { label: "知识库", value: overview.knowledge_bases, icon: "📚" },
            { label: "活跃定时任务", value: overview.scheduled_tasks_active, icon: "⏰" },
            { label: "就绪文档", value: overview.documents_ready, icon: "📄" },
          ].map((c) => (
            <div key={c.label} className="rounded-2xl border border-slate-200 bg-white p-4 text-center">
              <div className="text-lg">{c.icon}</div>
              <div className="mt-1 text-xl font-bold text-slate-900">{c.value}</div>
              <div className="text-[10px] text-slate-400">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* 成本汇总 */}
      {costs && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900">💰 Token 消耗(近 30 天)</h3>
            <span className="text-xs text-slate-400">
              总计 {fmtTokens(costs.total_tokens)} · 近 7 天 {fmtTokens(costs.last_7d_tokens)}
            </span>
          </div>
          <div className="mb-4 flex gap-4 text-xs">
            <span className="rounded-lg bg-indigo-50 px-3 py-1.5 text-indigo-700">
              对话 {fmtTokens(costs.chat_tokens)}
            </span>
            <span className="rounded-lg bg-emerald-50 px-3 py-1.5 text-emerald-700">
              定时任务 {fmtTokens(costs.task_tokens)}
            </span>
          </div>
          {/* 按日条形 */}
          {costs.by_day.length > 0 && (
            <div className="mb-4 flex h-24 items-end gap-1">
              {costs.by_day.map((d) => (
                <div
                  key={d.date}
                  title={`${d.date}: ${d.tokens}`}
                  className="flex-1 rounded-t bg-indigo-400/80 hover:bg-indigo-500"
                  style={{ height: `${(d.tokens / maxDay) * 100}%` }}
                />
              ))}
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <div className="mb-2 text-[11px] font-semibold text-slate-600">按助手</div>
              {costs.by_assistant.length === 0 ? (
                <div className="text-[11px] text-slate-400">暂无消耗</div>
              ) : (
                costs.by_assistant.map((a) => (
                  <div key={a.name} className="flex items-center justify-between py-1 text-xs">
                    <span className="truncate text-slate-600">{a.name}</span>
                    <span className="ml-2 shrink-0 font-mono text-slate-400">
                      {fmtTokens(a.tokens)} · {a.sessions} 会话
                    </span>
                  </div>
                ))
              )}
            </div>
            <div>
              <div className="mb-2 text-[11px] font-semibold text-slate-600">按定时任务</div>
              {costs.by_task.length === 0 ? (
                <div className="text-[11px] text-slate-400">暂无消耗</div>
              ) : (
                costs.by_task.map((t) => (
                  <div key={t.name} className="flex items-center justify-between py-1 text-xs">
                    <span className="truncate text-slate-600">{t.name}</span>
                    <span className="ml-2 shrink-0 font-mono text-slate-400">
                      {fmtTokens(t.tokens)} · {t.runs} 次
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* 用户管理 */}
      <div className="rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-5 py-3 text-sm font-bold text-slate-900">
          👥 用户与用量
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-100 bg-slate-50/80 text-[11px] font-semibold text-slate-600">
              <tr>
                <th className="px-5 py-3">邮箱</th>
                <th className="px-4 py-3">角色</th>
                <th className="px-4 py-3">注册时间</th>
                <th className="px-4 py-3">会话</th>
                <th className="px-4 py-3">Token 消耗</th>
                <th className="px-4 py-3">定时任务</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-slate-50/70">
                  <td className="px-5 py-3 font-medium text-slate-800">{u.email}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] ${
                        u.role === "developer"
                          ? "bg-indigo-50 text-indigo-700"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      {u.role === "developer" ? "开发者" : "用户"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {new Date(u.created_at).toLocaleDateString("zh-CN")}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{u.session_count}</td>
                  <td className="px-4 py-3 font-mono text-slate-600">{fmtTokens(u.message_tokens)}</td>
                  <td className="px-4 py-3 text-slate-600">{u.task_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {/* 动作审计 */}
      <div className="rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-5 py-3 text-sm font-bold text-slate-900">
          🛡️ 动作审计(http_request 调用留痕)
        </div>
        {actions.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-400">暂无动作调用记录</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-100 bg-slate-50/80 text-[11px] font-semibold text-slate-600">
                <tr>
                  <th className="px-5 py-3">时间</th>
                  <th className="px-4 py-3">用户</th>
                  <th className="px-4 py-3">请求</th>
                  <th className="px-4 py-3">结果</th>
                  <th className="px-4 py-3">说明</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {actions.map((a) => (
                  <tr key={a.id} className="hover:bg-slate-50/70">
                    <td className="px-5 py-2.5 text-slate-400">
                      {new Date(a.created_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                    </td>
                    <td className="px-4 py-2.5 text-slate-500">{a.user_id.slice(0, 8)}</td>
                    <td className="px-4 py-2.5 font-mono text-slate-700">
                      <span className="mr-1.5 rounded bg-slate-100 px-1 py-0.5 text-[10px]">{a.method}</span>
                      {a.url.length > 50 ? a.url.slice(0, 50) + "…" : a.url}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] ${
                          a.outcome === "executed" || a.outcome === "confirmed"
                            ? "bg-emerald-50 text-emerald-700"
                            : a.outcome === "cancelled" || a.outcome === "pending"
                              ? "bg-amber-50 text-amber-700"
                              : "bg-rose-50 text-rose-700"
                        }`}
                      >
                        {a.outcome}
                        {a.status_code ? ` ${a.status_code}` : ""}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 max-w-xs truncate text-slate-400" title={a.detail ?? ""}>
                      {a.detail ?? "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
