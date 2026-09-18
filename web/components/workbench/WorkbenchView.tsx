"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { listKbs, listSources, syncSource, type DataSourceInfo } from "../../lib/api/kb";
import { TodoCard } from "./TodoCard";
import { MemoryCard } from "./MemoryCard";
import { BriefingCard } from "./BriefingCard";
import { SchedulerCard } from "./SchedulerCard";
import type { AssistantInfo, KbInfo, SessionInfo } from "../../lib/types";

/** 个人工作台视图(M14 · 设计 010):今日概览 dashboard。
 *  数据全部来自平台现有 API(P0 零后端改动);各卡片独立 loading/error,互不阻塞。 */

interface Props {
  assistants: AssistantInfo[];
  sessions: SessionInfo[];
  onNewSession: (assistantId?: string) => void;
  onContinue: (sessionId: string) => void;
  onOpenKb: () => void;
  onSaveToKb: (content: string) => void;
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 6) return "夜深了";
  if (h < 12) return "早上好";
  if (h < 14) return "中午好";
  if (h < 18) return "下午好";
  return "晚上好";
}

const SYNC_META: Record<string, { label: string; dot: string }> = {
  never: { label: "未同步", dot: "bg-slate-300" },
  running: { label: "同步中", dot: "bg-indigo-500 animate-pulse" },
  success: { label: "同步正常", dot: "bg-emerald-500" },
  partial: { label: "部分失败", dot: "bg-amber-500" },
  failed: { label: "同步失败", dot: "bg-rose-500" },
};

export function WorkbenchView({ assistants, sessions, onNewSession, onContinue, onOpenKb, onSaveToKb }: Props) {
  return (
    <div className="h-full overflow-y-auto bg-slate-50">
      <div className="mx-auto max-w-5xl px-6 py-8">
        {/* 问候头 */}
        <div className="mb-6">
          <h1 className="text-xl font-bold text-slate-900">
            {greeting()} 👋
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            {new Date().toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" })}
            ·这里汇总你的助手、会话与知识库动态
          </p>
        </div>

        {/* 快捷操作 */}
        <div className="mb-6 grid grid-cols-3 gap-3">
          <QuickAction icon="💬" title="新会话" desc="选一个助手开始" onClick={() => onNewSession()} />
          <QuickAction icon="📖" title="问知识库" desc="检索调试 / 管理库" onClick={onOpenKb} />
          <QuickAction icon="⬆️" title="上传文档" desc="进知识库页选择库" onClick={onOpenKb} />
        </div>

        {/* 空状态三步引导(T14.8):新用户首次进入时替代"空卡片"观感 */}
        {assistants.length === 0 && sessions.length <= 1 && <OnboardingCard onOpenKb={onOpenKb} />}

        <div className="grid gap-5 lg:grid-cols-2">
          {/* 我的待办(P1) + 助手记忆(打磨①) */}
          <TodoCard />
          <MemoryCard />
          {/* 每日简报(P1) */}
          <BriefingCard onContinue={onContinue} onSaveToKb={onSaveToKb} />

          {/* 我的助手 */}
          <Card title="🤖 我的助手" action={{ label: "新会话", onClick: () => onNewSession() }}>
            {assistants.length === 0 ? (
              <Placeholder text="暂无助手;开发者部署插件后出现在这里" />
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {assistants.slice(0, 6).map((a) => (
                  <div
                    key={a.id}
                    className="group relative rounded-xl border border-slate-200 bg-white p-3 text-left transition hover:border-indigo-300 hover:bg-indigo-50/60"
                  >
                    <button
                      type="button"
                      onClick={() => onNewSession(a.id)}
                      className="block w-full text-left"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className="truncate text-xs font-bold text-slate-900">
                          {a.display_name || a.name}
                        </span>
                        {(a.mounted_kb_ids?.length ?? 0) > 0 && (
                          <span
                            className="shrink-0 rounded bg-emerald-50 border border-emerald-200 px-1 py-0.5 text-[9px] font-medium text-emerald-700"
                            title={`挂载了 ${a.mounted_kb_ids!.length} 个知识库`}
                          >
                            📚{a.mounted_kb_ids!.length}
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 truncate text-[10px] text-slate-400">
                        {a.description || "点击开始对话"}
                      </div>
                    </button>
                    {/* T14.8:管理入口 hover 浮现,跳开发者中心 */}
                    <Link
                      href="/developer"
                      className="absolute right-2 top-2 text-[9px] font-medium text-slate-300 opacity-0 transition group-hover:opacity-100 hover:text-indigo-600"
                      title="前往开发者中心管理"
                    >
                      管理 →
                    </Link>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* 最近会话 */}
          <Card title="🕘 最近会话">
            {sessions.length === 0 ? (
              <Placeholder text="暂无会话,从「新会话」开始" />
            ) : (
              <div className="space-y-1">
                {sessions.slice(0, 8).map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => onContinue(s.id)}
                    className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left transition hover:bg-slate-100"
                  >
                    <span className="truncate text-xs text-slate-700">
                      {s.title || "未命名会话"}
                    </span>
                    <span className="ml-2 shrink-0 text-[10px] text-slate-400">
                      {s.updated_at ? new Date(s.updated_at).toLocaleDateString("zh-CN") : ""}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* 定时任务(M15) + 知识库动态 */}
        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <SchedulerCard onContinue={onContinue} />
          <KbActivityCard onOpenKb={onOpenKb} />
        </div>
      </div>
    </div>
  );
}

function QuickAction({ icon, title, desc, onClick }: { icon: string; title: string; desc: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-xs transition hover:border-indigo-300 hover:shadow-sm"
    >
      <span className="text-xl">{icon}</span>
      <span>
        <span className="block text-xs font-bold text-slate-900">{title}</span>
        <span className="block text-[10px] text-slate-400">{desc}</span>
      </span>
    </button>
  );
}

export function Card({
  title,
  action,
  children,
}: {
  title: string;
  action?: { label: string; onClick: () => void };
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-xs">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <span className="text-xs font-bold text-slate-900">{title}</span>
        {action && (
          <button type="button" onClick={action.onClick} className="text-[11px] font-medium text-indigo-600 hover:text-indigo-700">
            {action.label} →
          </button>
        )}
      </div>
      <div className="p-3">{children}</div>
    </div>
  );
}

export function Placeholder({ text }: { text: string }) {
  return <div className="py-6 text-center text-[11px] text-slate-400">{text}</div>;
}

/** 知识库动态:各库文档规模 + 连接器最近同步状态(独立拉取与降级);失败源可就地重试。 */
function KbActivityCard({ onOpenKb }: { onOpenKb: () => void }) {
  const [kbs, setKbs] = useState<KbInfo[]>([]);
  const [sources, setSources] = useState<Record<string, DataSourceInfo[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const load = async () => {
      try {
        const kbList = await listKbs();
        if (cancelled) return;
        setKbs(kbList);
        setError(null);
        // 拉各库连接器状态(前 8 个库,避免请求爆炸)
        const next: Record<string, DataSourceInfo[]> = {};
        await Promise.all(
          kbList.slice(0, 8).map(async (kb) => {
            try {
              next[kb.id] = await listSources(kb.id);
            } catch {
              next[kb.id] = [];
            }
          })
        );
        if (cancelled) return;
        setSources(next);
        // 存在同步中的源 → 短轮询刷新
        const hasRunning = Object.values(next).some((list) =>
          list.some((s) => s.last_status === "running")
        );
        timer = setTimeout(load, hasRunning ? 3000 : 15000);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          timer = setTimeout(load, 15000);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [reloadTick]);

  // T14.8:失败/部分失败的源就地重试(触发同步后轮询机制自动跟进)
  const handleRetry = async (kbId: string, s: DataSourceInfo) => {
    setRetrying(s.id);
    try {
      await syncSource(kbId, s.id);
      setReloadTick((v) => v + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRetrying(null);
    }
  };

  return (
    <Card title="📚 知识库动态" action={{ label: "管理", onClick: onOpenKb }}>
      {loading && kbs.length === 0 ? (
        <Placeholder text="加载知识库..." />
      ) : error && kbs.length === 0 ? (
        <Placeholder text={`加载失败: ${error}`} />
      ) : kbs.length === 0 ? (
        <Placeholder text="暂无知识库,去「知识库」页创建" />
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {kbs.slice(0, 9).map((kb) => {
            const srcs = sources[kb.id] ?? [];
            // 取最近同步的一个源作为库的动态摘要
            const latest = srcs
              .filter((s) => s.last_sync_at)
              .sort((a, b) => (a.last_sync_at! < b.last_sync_at! ? 1 : -1))[0];
            const meta = latest ? SYNC_META[latest.last_status] ?? SYNC_META.never : null;
            return (
              <button
                key={kb.id}
                type="button"
                onClick={onOpenKb}
                className="rounded-xl border border-slate-200 bg-white p-3 text-left transition hover:border-indigo-300 hover:bg-indigo-50/60"
              >
                <div className="flex items-center gap-1.5">
                  <span>{kb.visibility === "public" ? "🌐" : kb.visibility === "shared" ? "👥" : "🔒"}</span>
                  <span className="truncate text-xs font-bold text-slate-900">{kb.name}</span>
                </div>
                <div className="mt-1 text-[10px] text-slate-400">
                  📄 {kb.doc_count} 文档 · 🧩 {kb.chunk_count} 片段
                </div>
                {meta ? (
                  <div className="mt-0.5 flex items-center gap-1.5 text-[10px]">
                    <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
                    <span className="text-slate-500">{meta.label}</span>
                    <span className="text-slate-400">
                      {latest!.last_sync_at ? new Date(latest!.last_sync_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : ""}
                    </span>
                    {(latest!.last_status === "failed" || latest!.last_status === "partial") && !retrying && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleRetry(kb.id, latest!);
                        }}
                        className="ml-auto shrink-0 rounded bg-rose-50 border border-rose-200 px-1.5 py-0.5 text-[9px] font-medium text-rose-700 hover:bg-rose-100"
                      >
                        重试
                      </button>
                    )}
                    {retrying === latest!.id && (
                      <span className="ml-auto text-[9px] text-indigo-600 animate-pulse">重试中...</span>
                    )}
                  </div>
                ) : (
                  <div className="mt-0.5 text-[10px] text-slate-300">尚无数据源同步</div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </Card>
  );
}

/** 空状态三步引导(T14.8):新用户首次进入时降低上手门槛。 */
function OnboardingCard({ onOpenKb }: { onOpenKb: () => void }) {
  const steps: {
    icon: string;
    title: string;
    desc: string;
    action?: { label: string; onClick?: () => void; href?: string };
  }[] = [
    {
      icon: "1️⃣",
      title: "选一个助手开始对话",
      desc: "点上方「💬 新会话」;通用助手可直接问答、记待办",
    },
    {
      icon: "2️⃣",
      title: "给知识库喂点资料",
      desc: "上传文档或配置数据源自动同步",
      action: { label: "去知识库", onClick: onOpenKb },
    },
    {
      icon: "3️⃣",
      title: "让助手懂你的业务",
      desc: "开发者部署插件、给助手挂知识库",
      action: { label: "开发者中心", href: "/developer" },
    },
  ];
  return (
    <div className="mb-5 rounded-2xl border border-indigo-200 bg-gradient-to-r from-indigo-50 to-white p-5">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-sm font-bold text-slate-900">👋 三步上手</span>
        <span className="text-[10px] text-slate-400">完成即可忽略本卡</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {steps.map((s) => (
          <div key={s.title} className="rounded-xl border border-slate-200 bg-white p-3">
            <div className="flex items-center gap-1.5 text-xs font-bold text-slate-900">
              <span>{s.icon}</span>
              {s.title}
            </div>
            <div className="mt-1 text-[10px] leading-relaxed text-slate-400">{s.desc}</div>
            {s.action &&
              (s.action.href ? (
                <Link
                  href={s.action.href}
                  className="mt-1.5 block text-[10px] font-medium text-indigo-600 hover:text-indigo-700"
                >
                  {s.action.label} →
                </Link>
              ) : (
                <button
                  type="button"
                  onClick={s.action.onClick}
                  className="mt-1.5 text-[10px] font-medium text-indigo-600 hover:text-indigo-700"
                >
                  {s.action.label} →
                </button>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}
