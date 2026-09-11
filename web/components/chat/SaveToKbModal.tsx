"use client";

import React, { useEffect, useMemo, useState } from "react";
import { listKbs, saveTextDocument } from "../../lib/api/kb";
import type { KbInfo } from "../../lib/types";

interface SaveToKbModalProps {
  content: string;
  source?: { app: string; session_id?: string; message_id?: string };
  onClose: () => void;
}

const HTML_MIME = "text/html" as const;
const MD_MIME = "text/markdown" as const;
const SHARED_KB_SLUG = "shared_workspace"; // 跨项目默认共享库(008 §11.3);存在则默认选中

/** 粗判:内容以 HTML 标签开头(如 SwiftShip 富文本文章)按 html 入库,pipeline 会去标签 */
function guessMime(content: string): "text/markdown" | "text/html" {
  return /^\s*<(!doctype|html|section|article|div|p|h[1-6])\b/i.test(content) ? HTML_MIME : MD_MIME;
}

/** 默认标题:首个 markdown 标题 / 首行截断(设计 008 §11.4) */
function defaultTitle(content: string): string {
  const heading = content.match(/^#{1,6}\s+(.+)$/m);
  const line = (heading ? heading[1] : content.trim().split("\n")[0] || "").trim();
  return line.replace(/[#*`>]/g, "").slice(0, 60) || "未命名收藏";
}

/** 会话产出收藏到知识库 (M12 增补, 设计 008 §11):仅列可写库,标题可改,保存走 from-text。 */
export function SaveToKbModal({ content, source, onClose }: SaveToKbModalProps) {
  const [kbs, setKbs] = useState<KbInfo[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [title, setTitle] = useState(defaultTitle(content));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const list = (await listKbs()).filter((k) => k.can_write);
        setKbs(list);
        const shared = list.find((k) => k.slug === SHARED_KB_SLUG);
        setSelectedId(shared?.id ?? list[0]?.id ?? null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const mime = useMemo(() => guessMime(content), [content]);

  const handleSave = async () => {
    if (!selectedId) return;
    setSaving(true);
    setError(null);
    try {
      await saveTextDocument(selectedId, { title: title.trim() || "未命名收藏", content, mime, source });
      setDone(true);
      setTimeout(onClose, 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <span className="text-xl">📚</span>
            <div>
              <h3 className="font-bold text-sm text-slate-900">收藏到知识库</h3>
              <p className="text-[11px] text-slate-400">保存后将在后台自动切分并向量化,可供智能体检索</p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600 text-sm">
            ✕
          </button>
        </div>

        {done ? (
          <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-3 text-xs text-emerald-700">
            ✅ 已收藏,正在后台处理...
          </div>
        ) : (
          <>
            {error && (
              <div className="rounded-lg bg-red-50 border border-red-200 p-2.5 text-[11px] text-red-700">⚠️ {error}</div>
            )}

            <div>
              <label className="mb-1 block text-[11px] font-semibold text-slate-600">标题</label>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs focus:border-indigo-400 focus:outline-none"
                placeholder="文档标题"
              />
            </div>

            <div>
              <label className="mb-1 block text-[11px] font-semibold text-slate-600">
                保存到 <span className="text-slate-400">({mime === HTML_MIME ? "HTML 正文" : "Markdown 正文"})</span>
              </label>
              <div className="max-h-40 space-y-1.5 overflow-y-auto">
                {loading ? (
                  <div className="py-6 text-center text-xs text-slate-400">加载知识库列表...</div>
                ) : kbs.length === 0 ? (
                  <div className="py-6 text-center text-xs text-slate-400">
                    暂无可写入的知识库(公共库需 developer 角色;或先创建私有库)
                  </div>
                ) : (
                  kbs.map((kb) => (
                    <button
                      key={kb.id}
                      type="button"
                      onClick={() => setSelectedId(kb.id)}
                      className={`flex w-full items-center gap-2.5 rounded-xl border p-2.5 text-left transition ${
                        selectedId === kb.id
                          ? "border-indigo-300 bg-indigo-50/70"
                          : "border-slate-200 bg-white hover:bg-slate-50"
                      }`}
                    >
                      <span className="text-sm shrink-0">{kb.visibility === "public" ? "🌐" : "🔒"}</span>
                      <span className="min-w-0 flex-1 truncate text-xs font-bold text-slate-900">{kb.name}</span>
                      <span className="shrink-0 text-[10px] text-slate-400">🧩 {kb.chunk_count}</span>
                    </button>
                  ))
                )}
              </div>
            </div>

            <div>
              <label className="mb-1 block text-[11px] font-semibold text-slate-600">内容预览</label>
              <div className="max-h-28 overflow-y-auto rounded-lg border border-slate-100 bg-slate-50 p-2.5 font-mono text-[10px] leading-4 whitespace-pre-wrap text-slate-600">
                {content.slice(0, 600)}
                {content.length > 600 ? "\n..." : ""}
              </div>
            </div>
          </>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-200"
          >
            {done ? "关闭" : "取消"}
          </button>
          {!done && (
            <button
              type="button"
              disabled={saving || loading || !selectedId}
              onClick={() => void handleSave()}
              className="rounded-md bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {saving ? "保存中..." : "收藏"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
