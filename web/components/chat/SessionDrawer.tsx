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
  collapsed,
  onToggleCollapse,
}: SessionDrawerProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const getAssistantName = (pluginId?: string | null) => {
    if (!pluginId) return null;
    const found = assistants.find((a) => a.id === pluginId);
    return found ? found.name : "插件助手";
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

  if (collapsed) {
    return (
      <div className="flex h-full flex-col items-center border-r border-slate-200 bg-white py-3 px-2">
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
          onClick={() => onCreate(null)}
          title="新建通用对话"
          className="mt-3 flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white hover:bg-slate-800 transition text-sm font-bold shadow-xs"
        >
          +
        </button>
      </div>
    );
  }

  return (
    <aside className="flex h-full w-64 flex-col border-r border-slate-200 bg-white">
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

      <div className="p-3">
        <button
          type="button"
          onClick={() => onCreate(null)}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-slate-300 py-2 text-xs font-medium text-slate-700 hover:border-slate-400 hover:bg-slate-50 transition shadow-2xs"
        >
          <span>＋</span>
          <span>新建对话</span>
        </button>
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
