"use client";

// 共享库成员管理(设计 008 §12.3):成员可读可写文档,管理(加/移除)仅 owner,服务端把关。

import React, { useEffect, useState } from "react";
import { addKbMemberByEmail, listKbMembers, removeKbMember } from "../../lib/api/kb";
import type { KbMemberInfo } from "../../lib/types";

interface Props {
  kbId: string;
  kbName: string;
  onClose: () => void;
  onChanged?: () => void;
}

export function KbMembersModal({ kbId, kbName, onClose, onChanged }: Props) {
  const [members, setMembers] = useState<KbMemberInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  const refresh = async () => {
    try {
      setLoading(true);
      setMembers(await listKbMembers(kbId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await addKbMemberByEmail(kbId, email.trim());
      setEmail("");
      await refresh();
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleRemove = async (m: KbMemberInfo) => {
    if (!confirm(`移除成员 ${m.email ?? m.user_id}?移除后其将无法访问该知识库。`)) return;
    try {
      await removeKbMember(kbId, m.user_id);
      await refresh();
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-slate-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <div>
            <div className="text-sm font-bold text-slate-900">👥 成员管理</div>
            <div className="mt-0.5 text-[11px] text-slate-400">{kbName} · 成员可查看并写入文档</div>
          </div>
          <button type="button" onClick={onClose} className="rounded-md px-2 py-1 text-slate-400 hover:bg-slate-100">
            ✕
          </button>
        </div>

        {error && (
          <div className="mx-5 mt-3 rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-[11px] text-rose-700">
            {error}
          </div>
        )}

        <form onSubmit={handleAdd} className="flex gap-2 px-5 pt-4">
          <input
            type="email"
            required
            placeholder="按邮箱添加成员"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs focus:border-indigo-500 focus:outline-hidden"
          />
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            添加
          </button>
        </form>

        <div className="max-h-64 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="py-6 text-center text-xs text-slate-400">加载中...</div>
          ) : members.length === 0 ? (
            <div className="py-6 text-center text-xs text-slate-400">暂无成员,通过上方输入框按邮箱添加</div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {members.map((m) => (
                <li key={m.user_id} className="flex items-center justify-between py-2.5">
                  <div className="min-w-0">
                    <div className="truncate text-xs font-medium text-slate-800">{m.email ?? m.user_id}</div>
                    <div className="text-[10px] text-slate-400">{m.role}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleRemove(m)}
                    className="ml-3 shrink-0 rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1 text-[11px] font-medium text-rose-700 hover:bg-rose-100 transition"
                  >
                    移除
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
