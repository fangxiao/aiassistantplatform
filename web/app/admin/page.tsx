"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Navbar } from "../../components/layout/Navbar";
import { apiFetch, apiGet } from "../../lib/api/client";
import { getUser, isAuthed } from "../../lib/api/auth";
import type { PluginInfo, ReviewStatus, UserAdminInfo } from "../../lib/types";

const REVIEW_BADGE: Record<ReviewStatus, { label: string; cls: string }> = {
  pending_review: { label: "待审核", cls: "bg-amber-100 text-amber-700 border-amber-200" },
  approved: { label: "已过审", cls: "bg-emerald-100 text-emerald-700 border-emerald-200" },
  rejected: { label: "已驳回", cls: "bg-rose-100 text-rose-700 border-rose-200" },
};

interface BotInfo {
  id: string;
  name: string;
  app_id: string;
  allowed_plugins: string[] | null;
  enabled: boolean;
}

const ROLE_LABEL: Record<UserAdminInfo["role"], string> = {
  admin: "平台管理员",
  developer: "开发者",
  user: "普通用户",
};

export default function AdminPage() {
  const router = useRouter();
  // useState 惰性初始化:getUser() 每次 JSON.parse 返回新对象,若直接赋值并
  // 进入下方 useEffect 依赖,会导致"渲染→effect→setState→渲染"死循环
  // (20260929 事故:admin 页 3 分钟打出 2 万次 /admin/users 请求)
  const [me] = useState(() => getUser());
  const [tab, setTab] = useState<"review" | "users" | "bots">("review");
  // 飞书机器人(P2-4):凭证绑定 + 助手授权
  const [bots, setBots] = useState<BotInfo[]>([]);
  const [botForm, setBotForm] = useState({ name: "", app_id: "", app_secret: "", allowed_plugins: [] as string[] });
  // 可选助手(复选框数据源):审批通过的 active 插件
  const [selectablePlugins, setSelectablePlugins] = useState<{ name: string; label: string }[]>([]);

  const loadBots = useCallback(async () => {
    try {
      setBots(await apiGet<BotInfo[]>("/channel/feishu/bots"));
      const ps = await apiGet<{ name: string; display_name?: string | null; review_status: string; status: string }[]>("/plugins");
      setSelectablePlugins(
        ps
          .filter((x) => x.review_status === "approved" && x.status === "active")
          .map((x) => ({ name: x.name, label: x.display_name || x.name })),
      );
    } catch (err) {
      alert(`加载机器人失败: ${err instanceof Error ? err.message : err}`);
    }
  }, []);

  // 助手审批
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [rejectTarget, setRejectTarget] = useState<PluginInfo | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [busy, setBusy] = useState(false);

  // 用户管理
  const [users, setUsers] = useState<UserAdminInfo[]>([]);
  const [query, setQuery] = useState("");

  const loadPlugins = useCallback(async () => {
    try {
      setPlugins(await apiGet<PluginInfo[]>("/plugins"));
    } catch (err) {
      alert(`加载插件失败: ${err instanceof Error ? err.message : err}`);
    }
  }, []);

  const loadUsers = useCallback(async (q: string) => {
    try {
      setUsers(await apiGet<UserAdminInfo[]>(`/admin/users${q ? `?q=${encodeURIComponent(q)}` : ""}`));
    } catch (err) {
      alert(`加载用户失败: ${err instanceof Error ? err.message : err}`);
    }
  }, []);

  useEffect(() => {
    if (!isAuthed()) {
      router.push("/auth");
      return;
    }
    if (me?.role !== "admin") {
      router.push("/");
      return;
    }
    void loadPlugins();
    void loadUsers("");
    if (tab === "bots") void loadBots();
  }, [router, me, loadPlugins, loadUsers, loadBots, tab]);

  const review = async (plugin: PluginInfo, action: "approve" | "reject", reason?: string) => {
    try {
      setBusy(true);
      const updated = await apiFetch<PluginInfo>(`/plugins/${plugin.id}/review`, {
        method: "POST",
        body: { action, reason },
      });
      setPlugins((prev) => prev.map((p) => (p.id === plugin.id ? { ...p, ...updated } : p)));
      setRejectTarget(null);
      setRejectReason("");
    } catch (err) {
      alert(`审批失败: ${err instanceof Error ? err.message : err}`);
    } finally {
      setBusy(false);
    }
  };

  const toggleStatus = async (plugin: PluginInfo) => {
    try {
      setBusy(true);
      const next = plugin.status === "active" ? "disable" : "enable";
      const updated = await apiFetch<PluginInfo>(`/plugins/${plugin.id}/${next}`, { method: "POST" });
      setPlugins((prev) => prev.map((p) => (p.id === plugin.id ? { ...p, ...updated } : p)));
    } catch (err) {
      alert(`操作失败: ${err instanceof Error ? err.message : err}`);
    } finally {
      setBusy(false);
    }
  };

  const patchUser = async (user: UserAdminInfo, body: { role?: string; disabled?: boolean }) => {
    try {
      setBusy(true);
      const updated = await apiFetch<UserAdminInfo>(`/admin/users/${user.id}`, {
        method: "PATCH",
        body,
      });
      setUsers((prev) => prev.map((u) => (u.id === user.id ? updated : u)));
    } catch (err) {
      alert(`操作失败: ${err instanceof Error ? err.message : err}`);
    } finally {
      setBusy(false);
    }
  };

  const pending = plugins.filter((p) => p.review_status === "pending_review");
  const others = plugins.filter((p) => p.review_status !== "pending_review");

  const pluginRow = (p: PluginInfo) => {
    const badge = REVIEW_BADGE[(p.review_status ?? "approved") as ReviewStatus];
    return (
      <div key={p.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-900">{p.display_name || p.name}</h3>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium border ${badge.cls}`}>{badge.label}</span>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium border ${p.status === "active" ? "bg-slate-100 text-slate-600 border-slate-200" : "bg-slate-200 text-slate-500 border-slate-300"}`}>
                {p.status === "active" ? "运行中" : "已下架"}
              </span>
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-slate-400">
              {p.name} · v{p.version} · owner {p.owner_id ?? "—"}
            </div>
            {p.last_review_reason && (
              <p className="mt-1 text-[11px] text-rose-600">驳回原因:{p.last_review_reason}</p>
            )}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-1.5">
            {p.review_status === "pending_review" && (
              <>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void review(p, "approve")}
                  className="rounded-lg bg-emerald-600 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-emerald-700 transition disabled:opacity-40"
                >
                  ✓ 通过
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => { setRejectTarget(p); setRejectReason(""); }}
                  className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-[11px] font-medium text-rose-600 hover:bg-rose-100 transition disabled:opacity-40"
                >
                  ✕ 驳回
                </button>
              </>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() => void toggleStatus(p)}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-[11px] font-medium text-slate-600 hover:border-slate-400 transition disabled:opacity-40"
            >
              {p.status === "active" ? "下架" : "启用"}
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Navbar />

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">⚙️ 管理后台</h1>
        <p className="mt-1 text-sm text-slate-500">助手发布审批与用户角色管理(仅平台管理员)。</p>

        <div className="mt-5 flex gap-1 rounded-xl border border-slate-200 bg-white p-1 w-fit">
          {([
            ["review", `📋 助手审批${pending.length ? ` (${pending.length})` : ""}`],
            ["users", "👥 用户管理"],
            ["bots", `🤖 飞书机器人${bots.length ? ` (${bots.length})` : ""}`],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`rounded-lg px-4 py-1.5 text-xs font-medium transition ${
                tab === key ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === "review" && (
          <div className="mt-6 space-y-6">
            <section>
              <h2 className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-400">待审核({pending.length})</h2>
              {pending.length === 0 ? (
                <p className="rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center text-xs text-slate-400">
                  暂无待审助手
                </p>
              ) : (
                <div className="space-y-3">{pending.map(pluginRow)}</div>
              )}
            </section>
            <section>
              <h2 className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-400">历史({others.length})</h2>
              <div className="space-y-3">{others.map(pluginRow)}</div>
            </section>
          </div>
        )}

        {tab === "bots" && (
          <div className="mt-6">
            <p className="mb-4 text-xs text-slate-500">
              绑定已有飞书自建应用:开放平台创建应用 → 开机器人能力 → 事件订阅选「长连接」订阅 im.message.receive_v1
              → 权限开通 im:message → 发布版本后填入凭证。<b>助手授权</b>留空 = 该机器人可用全部助手,填插件名(逗号分隔)即白名单。
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              <input type="text" value={botForm.name} onChange={(e) => setBotForm({ ...botForm, name: e.target.value })} placeholder="机器人名称(如:团队入口)" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs shadow-xs" />
              <input type="text" value={botForm.app_id} onChange={(e) => setBotForm({ ...botForm, app_id: e.target.value })} placeholder="App ID(cli_...)" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs shadow-xs" />
              <input type="password" value={botForm.app_secret} onChange={(e) => setBotForm({ ...botForm, app_secret: e.target.value })} placeholder="App Secret" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs shadow-xs" />
            
            </div>
            <div className="mt-2">
              <p className="mb-1 text-[11px] font-semibold text-slate-600">助手白名单(不勾 = 全部可用)</p>
              <div className="flex flex-wrap gap-2">
                {selectablePlugins.map((pl) => (
                  <label key={pl.name} className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[11px] text-slate-700 shadow-xs has-[:checked]:border-indigo-400 has-[:checked]:bg-indigo-50">
                    <input
                      type="checkbox"
                      checked={botForm.allowed_plugins.includes(pl.name)}
                      onChange={(e) =>
                        setBotForm((f) => ({
                          ...f,
                          allowed_plugins: e.target.checked
                            ? [...f.allowed_plugins, pl.name]
                            : f.allowed_plugins.filter((x) => x !== pl.name),
                        }))
                      }
                    />
                    {pl.label}
                  </label>
                ))}
                {selectablePlugins.length === 0 && <span className="text-[11px] text-slate-400">暂无已过审助手</span>}
              </div>
            </div>
            <button
              type="button"
              onClick={async () => {
                try {
                  await apiFetch("/channel/feishu/bots", {
                    method: "POST",
                    body: {
                      name: botForm.name,
                      app_id: botForm.app_id,
                      app_secret: botForm.app_secret,
                      allowed_plugins: botForm.allowed_plugins.length ? botForm.allowed_plugins : null,
                      enabled: true,
                    },
                  });
                  setBotForm({ name: "", app_id: "", app_secret: "", allowed_plugins: [] });
                  await loadBots();
                } catch (err) {
                  alert(`创建失败: ${err instanceof Error ? err.message : err}`);
                }
              }}
              className="mt-3 rounded-lg bg-slate-900 px-4 py-2 text-xs font-medium text-white hover:bg-slate-800"
            >
              ＋ 绑定机器人(立即生效)
            </button>
            <div className="mt-5 space-y-2">
              {bots.map((b) => (
                <div key={b.id} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-xs">
                  <div>
                    <p className="text-xs font-semibold text-slate-800">{b.name} <span className="ml-2 font-mono text-[10px] text-slate-400">{b.app_id}</span></p>
                    <p className="mt-0.5 text-[11px] text-slate-500">助手白名单:{b.allowed_plugins?.join("、") ?? "不限(全部助手)"}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] ${b.enabled ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                      {b.enabled ? "已启用" : "已停用"}
                    </span>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await apiFetch(`/channel/feishu/bots/${b.id}`, { method: "DELETE" });
                          await loadBots();
                        } catch (err) {
                          alert(`删除失败: ${err instanceof Error ? err.message : err}`);
                        }
                      }}
                      className="rounded-md border border-rose-200 px-2 py-1 text-[10px] text-rose-600 hover:bg-rose-50"
                    >
                      解绑
                    </button>
                  </div>
                </div>
              ))}
              {bots.length === 0 && <p className="text-center text-xs text-slate-400">暂无 DB 绑定的机器人(settings 全局凭证的默认机器人仍可用)</p>}
            </div>
          </div>
        )}

        {tab === "users" && (
          <div className="mt-6">
            <div className="mb-4 flex gap-2">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") void loadUsers(query); }}
                placeholder="搜索邮箱或昵称..."
                className="w-72 rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs text-slate-800 shadow-xs focus:border-slate-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => void loadUsers(query)}
                className="rounded-lg bg-slate-900 px-4 py-2 text-xs font-medium text-white hover:bg-slate-800 transition"
              >
                搜索
              </button>
            </div>
            <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-xs">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                  <tr>
                    <th className="px-4 py-3">邮箱</th>
                    <th className="px-4 py-3">昵称</th>
                    <th className="px-4 py-3">角色</th>
                    <th className="px-4 py-3">状态</th>
                    <th className="px-4 py-3">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} className="border-b border-slate-50 last:border-0">
                      <td className="px-4 py-3 font-medium text-slate-800">{u.email}</td>
                      <td className="px-4 py-3 text-slate-600">{u.nickname ?? "—"}</td>
                      <td className="px-4 py-3">
                        <select
                          value={u.role}
                          disabled={busy}
                          onChange={(e) => void patchUser(u, { role: e.target.value })}
                          className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700"
                        >
                          <option value="user">普通用户</option>
                          <option value="developer">开发者</option>
                          <option value="admin">平台管理员</option>
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium border ${u.disabled ? "bg-rose-100 text-rose-700 border-rose-200" : "bg-emerald-50 text-emerald-700 border-emerald-200"}`}>
                          {u.disabled ? "已禁用" : "正常"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void patchUser(u, { disabled: !u.disabled })}
                          className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-600 hover:border-slate-400 transition disabled:opacity-40"
                        >
                          {u.disabled ? "启用" : "禁用"}
                        </button>
                      </td>
                    </tr>
                  ))}
                  {users.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-slate-400">无匹配用户</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      {rejectTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setRejectTarget(null)}>
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-bold text-slate-800">✕ 驳回「{rejectTarget.display_name || rejectTarget.name}」</h3>
            <p className="mt-1 text-[11px] text-slate-500">驳回必填原因,开发者可见后可修改并重新提交。</p>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={4}
              placeholder="例如:提示词包含未声明的数据外发行为…"
              className="mt-3 w-full rounded-lg border border-slate-300 p-3 text-xs text-slate-800 focus:border-slate-500 focus:outline-none"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setRejectTarget(null)} className="rounded-lg border border-slate-200 px-4 py-1.5 text-xs text-slate-600">
                取消
              </button>
              <button
                type="button"
                disabled={busy || !rejectReason.trim()}
                onClick={() => void review(rejectTarget, "reject", rejectReason.trim())}
                className="rounded-lg bg-rose-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-rose-700 transition disabled:opacity-40"
              >
                确认驳回
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
