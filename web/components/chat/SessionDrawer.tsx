"use client";

import React, { useState } from "react";
import type { AssistantInfo, SessionInfo } from "../../lib/types";

interface SessionDrawerProps {
  sessions: SessionInfo[];
  assistants?: AssistantInfo[];
  currentId: string | null;
  onSelect: (id: string) => void;
  onCreate: (pluginId?: string | null) => void;
  onRename: (id: string, title: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onShare?: (id: string) => Promise<void>;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export function SessionDrawer({
  sessions,
  assistants = [],
  currentId,
  onSelect,
  onCreate,
  onRename,
  onDelete,
  onShare,
  collapsed,
  onToggleCollapse,
}: SessionDrawerProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);

  const getAssistantName = (pluginId?: string | null) => {
    if (!pluginId) return null;
    const found = assistants.find((a) => a.id === pluginId);
    return found ? (found.display_name || found.name) : "插件助手";
  };

  const getAssistantIcon = (asstName: string, pluginId?: string | null) => {
    const n = (asstName || "").toLowerCase();
    if (n.includes("微信") || n.includes("writewx")) return "✍️";
    if (n.includes("合同") || n.includes("contract")) return "📄";
    if (n.includes("prd") || n.includes("评审")) return "📋";
    return "🤖";
  };

  const handleStartRename = (s: SessionInfo, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(s.id);
    setEditTitle(s.title ?? "新会话");
  };

  const handleSaveRename = async (id: string, e: React.FormEvent) => {
    e.preventDefault();
    if (editTitle.trim()) {
      await onRename(id, editTitle.trim());
    }
    setEditingId(null);
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm("确定要删除该会话吗？历史消息将被清除。")) {
      await onDelete(id);
    }
  };

  const handleCreateWithAssistant = (pluginId: string | null) => {
    setMenuOpen(false);
    onCreate(pluginId);
  };

  if (collapsed) {
    return (
      <div className="relative flex h-full flex-col items-center border-r border-slate-200 bg-white py-3 px-2">
        <button
          type="button"
          onClick={onToggleCollapse}
          title="展开会话列表"
          className="rounded p-2 text-slate-500 hover:bg-slate-100 transition"
        >
          📂
        </button>
        <button
          type="button"
          onClick={() => setMenuOpen(!menuOpen)}
          title="新建对话"
          className="mt-3 flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white hover:bg-slate-800 transition text-sm font-bold shadow-xs"
        >
          +
        </button>

        {/* 折叠模式下的助手弹出菜单 */}
        {menuOpen && (
          <div className="absolute left-14 top-14 z-50 w-60 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl animate-in fade-in zoom-in-95 duration-100">
            <div className="px-2 py-1 text-[11px] font-semibold text-slate-400">选择助手新建对话</div>
            <button
              type="button"
              onClick={() => handleCreateWithAssistant(null)}
              className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-xs text-slate-700 hover:bg-slate-100 transition text-left"
            >
              <span>💬</span>
              <span className="font-medium">通用对话</span>
            </button>
            {assistants.length > 0 && (
              <>
                <div className="my-1 border-t border-slate-100" />
                <div className="px-2 py-1 text-[10px] text-slate-400">已安装智能体 ({assistants.length})</div>
                {assistants.map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => handleCreateWithAssistant(a.id)}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-xs text-slate-800 hover:bg-indigo-50 hover:text-indigo-700 transition text-left"
                  >
                    <span>{getAssistantIcon(a.display_name || a.name, a.id)}</span>
                    <span className="truncate font-medium">{a.display_name || a.name}</span>
                  </button>
                ))}
              </>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <aside className="relative z-30 flex h-full w-64 flex-col border-r border-slate-200 bg-white max-md:absolute max-md:inset-y-0 max-md:left-0 max-md:shadow-2xl">
      <div className="flex items-center justify-between border-b border-slate-100 p-3">
        <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
          <span>💬</span> 历史对话
        </span>
        <button
          type="button"
          onClick={onToggleCollapse}
          className="rounded p-1 text-slate-400 hover:bg-slate-100 transition text-xs"
          title="折叠侧边栏"
        >
          ◀
        </button>
      </div>

      {/* 新建对话按钮与下拉助手选择器 */}
      <div className="relative p-3">
        <button
          type="button"
          onClick={() => setMenuOpen(!menuOpen)}
          className="flex w-full items-center justify-between gap-1.5 rounded-lg border border-slate-300 bg-slate-900 px-3 py-2 text-xs font-medium text-white hover:bg-slate-800 transition shadow-xs"
        >
          <span className="flex items-center gap-1.5">
            <span>＋</span>
            <span>新建对话</span>
          </span>
          <span className={`text-[10px] transition-transform duration-150 ${menuOpen ? "rotate-180" : ""}`}>
            ▼
          </span>
        </button>

        {/* 助手选择浮层菜单 */}
        {menuOpen && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setMenuOpen(false)}
            />
            <div className="absolute left-3 right-3 top-12 z-50 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl animate-in fade-in zoom-in-95 duration-100">
              <button
                type="button"
                onClick={() => handleCreateWithAssistant(null)}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-xs text-slate-700 hover:bg-slate-100 transition text-left"
              >
                <span className="text-sm">💬</span>
                <div>
                  <div className="font-medium text-slate-900">通用对话</div>
                  <div className="text-[10px] text-slate-400">标准大模型自由问答</div>
                </div>
              </button>

              {assistants.length > 0 && (
                <>
                  <div className="my-1 border-t border-slate-100" />
                  <div className="px-2 py-1 text-[10px] font-semibold text-slate-400">
                    已安装智能体 ({assistants.length})
                  </div>
                  <div className="max-h-56 overflow-y-auto space-y-0.5">
                    {assistants.map((a) => (
                      <button
                        key={a.id}
                        type="button"
                        onClick={() => handleCreateWithAssistant(a.id)}
                        className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs text-slate-800 hover:bg-indigo-50 hover:text-indigo-700 transition text-left"
                      >
                        <span className="text-base">{getAssistantIcon(a.display_name || a.name, a.id)}</span>
                        <div className="overflow-hidden flex-1">
                          <div className="font-medium truncate">{a.display_name || a.name}</div>
                          <div className="text-[10px] text-slate-400 truncate mt-0.5 flex items-center gap-1">
                            <span className="font-mono text-[9px] text-slate-400">({a.name})</span>
                            {a.description && (
                              <>
                                <span>·</span>
                                <span className="truncate">{a.description}</span>
                              </>
                            )}
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </>
              )}

              <div className="my-1 border-t border-slate-100" />
              <a
                href="/assistants"
                className="flex items-center justify-center gap-1 rounded-md py-1.5 text-[11px] font-medium text-indigo-600 hover:bg-indigo-50 transition"
              >
                <span>🔍 浏览助手广场...</span>
              </a>
            </div>
          </>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-2 space-y-1">
        {sessions.length === 0 && (
          <div className="py-8 text-center text-xs text-slate-400">
            暂无历史会话
          </div>
        )}
        {sessions.map((s) => {
          const isSelected = s.id === currentId;
          const isEditing = editingId === s.id;
          const asstName = getAssistantName(s.plugin_id);

          return (
            <div
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={`group flex cursor-pointer flex-col rounded-lg px-2.5 py-2 text-xs transition ${
                isSelected
                  ? "bg-slate-900 text-white font-medium shadow-xs"
                  : "text-slate-700 hover:bg-slate-100"
              }`}
            >
              <div className="flex items-center justify-between">
                {isEditing ? (
                  <form
                    onSubmit={(e) => handleSaveRename(s.id, e)}
                    onClick={(e) => e.stopPropagation()}
                    className="flex-1 mr-1"
                  >
                    <input
                      type="text"
                      value={editTitle}
                      autoFocus
                      onChange={(e) => setEditTitle(e.target.value)}
                      onBlur={() => setEditingId(null)}
                      className="w-full rounded border border-slate-400 px-1.5 py-0.5 text-xs text-slate-900 focus:outline-none"
                    />
                  </form>
                ) : (
                  <div className="flex items-center gap-1.5 overflow-hidden flex-1">
                    <span className="text-xs shrink-0">
                      {s.plugin_id ? "🤖" : "💬"}
                    </span>
                    <span className="truncate">{s.title || "未命名会话"}</span>
                  </div>
                )}

                {!isEditing && (
                  <div className="hidden group-hover:flex items-center gap-1 shrink-0 ml-1">
                    <button
                      type="button"
                      onClick={(e) => handleStartRename(s, e)}
                      title="重命名"
                      className={`rounded px-1 py-0.5 text-[10px] ${
                        isSelected
                          ? "text-slate-300 hover:bg-slate-800"
                          : "text-slate-400 hover:bg-slate-200"
                      }`}
                    >
                      ✏️
                    </button>
                    {onShare && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          void onShare(s.id);
                        }}
                        title="生成只读分享链接"
                        className={`rounded px-1 py-0.5 text-[10px] ${
                          isSelected
                            ? "text-slate-300 hover:bg-slate-800"
                            : "text-slate-400 hover:bg-slate-200"
                        }`}
                      >
                        🔗
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={(e) => handleDelete(s.id, e)}
                      title="删除"
                      className={`rounded px-1 py-0.5 text-[10px] ${
                        isSelected
                          ? "text-rose-300 hover:bg-slate-800"
                          : "text-rose-400 hover:bg-slate-200"
                      }`}
                    >
                      🗑️
                    </button>
                  </div>
                )}
              </div>

              {asstName && (
                <div className="mt-1 flex items-center gap-1">
                  <span
                    className={`rounded px-1.5 py-0.2 text-[9px] font-medium truncate max-w-[190px] ${
                      isSelected
                        ? "bg-indigo-950 text-indigo-200 border border-indigo-800"
                        : "bg-indigo-50 text-indigo-600 border border-indigo-100"
                    }`}
                  >
                    {asstName}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
