"use client";

import React, { useEffect, useState } from "react";
import { apiGet } from "../../lib/api/client";
import { createSession, sendMessage } from "../../lib/api/chat";
import { listKbs, listSources, type DataSourceInfo } from "../../lib/api/kb";
import type { KbInfo } from "../../lib/types";

/** 每日简报(M14 P1,需求 007 U7):按钮触发,前端聚合平台动态注入 prompt,
 *  复用会话链路生成;产出可收藏入库。非定时推送——主动唤醒属 P2 平台能力。
 *  T14.8:生成完成自动归档(本地保留近 7 份),卡片可展开回看历史。 */

const ARCHIVE_KEY = "workbench_briefings";

interface BriefingArchiveItem {
  date: string;
  text: string;
  session_id: string | null;
  created_at: string;
}

function loadArchive(): BriefingArchiveItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(ARCHIVE_KEY);
    const list = raw ? (JSON.parse(raw) as BriefingArchiveItem[]) : [];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function saveToArchive(item: BriefingArchiveItem) {
  // 同日覆盖(每日一份语义),其余保留,总量限近 7 份
  const list = loadArchive().filter(
    (x) => x.date !== item.date
  );
  list.unshift(item);
  localStorage.setItem(ARCHIVE_KEY, JSON.stringify(list.slice(0, 7)));
}

interface Props {
  onContinue: (sessionId: string) => void;
  onSaveToKb: (content: string) => void;
}

type Phase = "idle" | "streaming" | "done" | "error";

export function BriefingCard({ onContinue, onSaveToKb }: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [text, setText] = useState("");
  const [sid, setSid] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [archive, setArchive] = useState<BriefingArchiveItem[]>([]);
  const [showArchive, setShowArchive] = useState(false);

  useEffect(() => {
    setArchive(loadArchive());
  }, []);

  const generate = async () => {
    setPhase("streaming");
    setText("");
    setError(null);
    try {
      // 1. 前端聚合平台动态(与知识库动态卡同源数据)
      const kbs: KbInfo[] = await listKbs();
      const sourceStats: DataSourceInfo[] = [];
      await Promise.all(
        kbs.slice(0, 8).map(async (kb) => {
          try {
            sourceStats.push(...(await listSources(kb.id)));
          } catch {
            /* 单库失败不影响简报 */
          }
        })
      );
      // 待办(T14.5 联动):未完成事项注入简报,提醒用户
      let pending: { count: number; items: string[] } = { count: 0, items: [] };
      try {
        const todos = await apiGet<{ id: string; text: string; done: boolean }[]>("/workbench/todos");
        const open = todos.filter((t) => !t.done);
        pending = { count: open.length, items: open.slice(0, 5).map((t) => t.text) };
      } catch {
        /* 待办拉取失败不阻断简报 */
      }

      const payload = {
        date: new Date().toLocaleDateString("zh-CN"),
        kbs: kbs.map((k) => ({ name: k.name, docs: k.doc_count, chunks: k.chunk_count })),
        syncs: sourceStats.map((s) => ({
          source: s.name,
          status: s.last_status,
          last_sync_at: s.last_sync_at,
          error: s.last_error,
        })),
        pending_todos: pending,
      };

      // 2. 复用会话链路:新建会话(默认助手)发送聚合 prompt,流式接收
      const session = await createSession();
      setSid(session.id);
      const prompt =
        `你是平台工作台助手。请根据以下平台动态数据生成一段中文每日简报(180 字以内),` +
        `包含:①知识库概览;②需要关注的异常(同步失败/部分失败,指出是哪个源与原因);` +
        `③未完成待办提醒(pending_todos,有则点出最紧要的 1-2 条);④1-2 条行动建议。` +
        `直接输出简报正文,不要开场白。数据:\n${JSON.stringify(payload)}`;

      let acc = "";
      for await (const ev of sendMessage(session.id, prompt)) {
        if (ev.event === "delta") {
          const d = ev.data as { text?: string };
          acc += d.text ?? "";
          setText(acc);
        } else if (ev.event === "error") {
          throw new Error(String((ev.data as { message?: string })?.message ?? "生成失败"));
        }
      }
      if (!acc.trim()) throw new Error("模型未返回内容");
      // T14.8:完成即归档(同日覆盖,保留近 7 份)
      saveToArchive({
        date: new Date().toLocaleDateString("zh-CN"),
        text: acc,
        session_id: session.id,
        created_at: new Date().toISOString(),
      });
      setArchive(loadArchive());
      setPhase("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPhase("error");
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-xs">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <span className="text-xs font-bold text-slate-900">
          📰 每日简报
          <span className="ml-2 text-[10px] font-normal text-slate-400">聚合平台动态,由助手生成</span>
        </span>
        <div className="flex items-center gap-2">
          {phase === "done" && sid && (
            <button
              type="button"
              onClick={() => onContinue(sid)}
              className="text-[11px] font-medium text-indigo-600 hover:text-indigo-700"
            >
              继续追问 →
            </button>
          )}
          {phase !== "streaming" && (
            <button
              type="button"
              onClick={() => void generate()}
              className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
            >
              {phase === "done" ? "重新生成" : "生成今日简报"}
            </button>
          )}
        </div>
      </div>

      <div className="p-4">
        {phase === "idle" && (
          <div className="py-4 text-center text-[11px] text-slate-400">
            点击生成,助手将汇总知识库规模与连接器同步状态
          </div>
        )}
        {phase === "streaming" && (
          <div className="py-4 text-center text-[11px] text-indigo-600 animate-pulse">生成中,请稍候...</div>
        )}
        {phase === "error" && (
          <div className="rounded-lg bg-rose-50 border border-rose-200 p-2.5 text-[11px] text-rose-700">⚠️ {error}</div>
        )}
        {phase === "done" && (
          <div>
            <div className="whitespace-pre-wrap text-xs leading-relaxed text-slate-700">{text}</div>
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={() => onSaveToKb(text)}
                className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[11px] font-medium text-emerald-700 hover:bg-emerald-100"
              >
                📚 存入知识库
              </button>
            </div>
          </div>
        )}

        {/* T14.8:历史归档(本地近 7 份) */}
        {archive.length > 0 && (
          <div className="mt-3 border-t border-slate-100 pt-2">
            <button
              type="button"
              onClick={() => setShowArchive((v) => !v)}
              className="text-[10px] font-medium text-slate-400 hover:text-slate-600"
            >
              {showArchive ? "收起历史" : `历史简报(${archive.length})`}
            </button>
            {showArchive && (
              <div className="mt-1.5 space-y-1">
                {archive.map((b) => (
                  <div key={b.created_at} className="rounded-lg bg-slate-50 p-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-medium text-slate-600">{b.date}</span>
                      {b.session_id && (
                        <button
                          type="button"
                          onClick={() => onContinue(b.session_id!)}
                          className="text-[9px] text-indigo-500 hover:text-indigo-700"
                        >
                          继续追问 →
                        </button>
                      )}
                    </div>
                    <div className="mt-0.5 line-clamp-2 whitespace-pre-wrap text-[10px] text-slate-500">{b.text}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
