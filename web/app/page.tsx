"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Composer from "../components/chat/Composer";
import MessageList from "../components/chat/MessageList";
import { Navbar } from "../components/layout/Navbar";
import { SessionDrawer } from "../components/chat/SessionDrawer";
import {
  createSession,
  deleteSession,
  getHistory,
  interactBlock,
  listSessions,
  renameSession,
  sendFeedbackEvent,
  sendMessage,
} from "../lib/api/chat";
import { apiGet } from "../lib/api/client";
import { isAuthed } from "../lib/api/auth";
import type {
  AssistantInfo,
  ChatMessage,
  ContentBlock,
  SessionInfo,
  ToolCallInfo,
} from "../lib/types";

let tempSeq = 0;
const nid = (prefix: string) => `${prefix}-${Date.now()}-${tempSeq++}`;

function ChatHome() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const querySessionId = searchParams.get("sessionId");

  const [assistants, setAssistants] = useState<AssistantInfo[]>([]);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [current, setCurrent] = useState<SessionInfo | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [drawerCollapsed, setDrawerCollapsed] = useState(false);
  const [showAsstModal, setShowAsstModal] = useState(false);

  // 门禁
  useEffect(() => {
    if (!isAuthed()) {
      router.replace("/auth");
    }
  }, [router]);

  const selectSession = useCallback(async (s: SessionInfo) => {
    setCurrent(s);
    try {
      const history = await getHistory(s.id);
      setMessages(history);
    } catch {
      setMessages([]);
    }
  }, []);

  const refreshSessions = useCallback(async () => {
    try {
      const list = await listSessions();
      setSessions(list);
      return list;
    } catch {
      return [];
    }
  }, []);

  // 初始加载
  useEffect(() => {
    if (!isAuthed()) return;
    (async () => {
      // 加载助手市场列表，用于名称映射与详情呈现
      try {
        const asstList = await apiGet<AssistantInfo[]>("/assistants");
        setAssistants(asstList);
      } catch {
        // ignore
      }

      let list = await refreshSessions();
      if (querySessionId) {
        const found = list.find((s) => s.id === querySessionId);
        if (found) {
          await selectSession(found);
          return;
        }
      }

      if (list.length === 0) {
        const s = await createSession();
        list = [s];
        setSessions(list);
      }
      await selectSession(list[0]);
    })();
  }, [querySessionId, refreshSessions, selectSession]);

  const handleCreateSession = async (pluginId?: string | null) => {
    try {
      const s = await createSession(pluginId ?? null);
      const list = await refreshSessions();
      const target = list.find((x) => x.id === s.id) ?? s;
      await selectSession(target);
    } catch (err) {
      alert(`创建会话失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const handleRenameSession = async (id: string, title: string) => {
    try {
      await renameSession(id, title);
      await refreshSessions();
      if (current?.id === id) {
        setCurrent((prev) => (prev ? { ...prev, title } : null));
      }
    } catch (err) {
      alert(`重命名失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const handleDeleteSession = async (id: string) => {
    try {
      await deleteSession(id);
      const list = await refreshSessions();
      if (current?.id === id) {
        if (list.length > 0) {
          await selectSession(list[0]);
        } else {
          const s = await createSession();
          setSessions([s]);
          await selectSession(s);
        }
      }
    } catch (err) {
      alert(`删除会话失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  // 发送普通对话消息
  const handleSend = useCallback(
    async (content: string) => {
      if (!current || streaming) return;
      setStreaming(true);
      const userMsg: ChatMessage = { id: nid("u"), role: "user", text: content };
      const asstId = nid("a");
      const asstMsg: ChatMessage = {
        id: asstId,
        role: "assistant",
        text: "",
        blocks: [],
        toolCalls: [],
      };
      setMessages((ms) => [...ms, userMsg, asstMsg]);

      const patch = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((ms) => ms.map((m) => (m.id === asstId ? fn(m) : m)));

      try {
        for await (const ev of sendMessage(current.id, content)) {
          if (ev.event === "delta") {
            const d = ev.data as { text?: string };
            patch((m) => ({
              ...m,
              text: m.text + (d.text ?? ""),
            }));
          } else if (ev.event === "block_meta") {
            const block = ev.data as ContentBlock;
            patch((m) => ({
              ...m,
              blocks: [...(m.blocks ?? []), block],
            }));
          } else if (ev.event === "tool_call") {
            const d = ev.data as ToolCallInfo;
            patch((m) => ({ ...m, toolCalls: [...(m.toolCalls ?? []), d] }));
          } else if (ev.event === "done") {
            const d = ev.data as { message_id?: string };
            patch((m) => ({ ...m, id: d.message_id ?? m.id }));
          } else if (ev.event === "error") {
            const d = ev.data as { message?: string };
            patch((m) => ({
              ...m,
              text: m.text + `\n\n[错误] ${d.message ?? "未知"}`,
            }));
          }
        }
      } catch (e) {
        patch((m) => ({ ...m, text: m.text + `\n\n[错误] ${String(e)}` }));
      } finally {
        setStreaming(false);
        refreshSessions();
      }
    },
    [current, streaming, refreshSessions]
  );

  // 交互回传处理器 (003 v2.0 §9)
  const handleInteract = async (
    action: string,
    value: any,
    args?: Record<string, any>
  ) => {
    if (!current) return;

    if (action === "action.thumbs") {
      await sendFeedbackEvent(current.id, "thumbs", undefined, value);
      return;
    }

    try {
      const resp = await interactBlock(current.id, nid("block"), action, value, args);
      if (resp.blocks && resp.blocks.length > 0) {
        const asstMsg: ChatMessage = {
          id: nid("act"),
          role: "assistant",
          text: "",
          blocks: resp.blocks,
        };
        setMessages((prev) => [...prev, asstMsg]);
      }
    } catch (err) {
      alert(`交互处理失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const currentAssistant = assistants.find((a) => a.id === current?.plugin_id);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-white">
      <Navbar />

      <div className="flex flex-1 overflow-hidden">
        {/* 左侧会话抽屉 */}
        <SessionDrawer
          sessions={sessions}
          assistants={assistants}
          currentId={current?.id ?? null}
          onSelect={(id) => {
            const s = sessions.find((x) => x.id === id);
            if (s) selectSession(s);
          }}
          onCreate={handleCreateSession}
          onRename={handleRenameSession}
          onDelete={handleDeleteSession}
          collapsed={drawerCollapsed}
          onToggleCollapse={() => setDrawerCollapsed(!drawerCollapsed)}
        />

        {/* 右侧主聊天区域 */}
        <main className="flex flex-1 flex-col overflow-hidden bg-slate-50">
          {/* Header Bar 明确展示当前助手信息 */}
          <div className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-4 shadow-2xs">
            <div className="flex items-center gap-3">
              {currentAssistant ? (
                <div className="flex items-center gap-2.5">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700 text-base font-bold shadow-2xs">
                    🤖
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-900">
                        {currentAssistant.name}
                      </span>
                      <span className="rounded bg-slate-100 px-1.5 py-0.2 font-mono text-[10px] text-slate-600">
                        v{currentAssistant.version}
                      </span>
                      {currentAssistant.model && (
                        <span className="rounded-full bg-emerald-50 border border-emerald-200 px-2 py-0.2 font-mono text-[10px] text-emerald-700">
                          {currentAssistant.model}
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => setShowAsstModal(true)}
                        title="查看助手详情与依赖"
                        className="text-slate-400 hover:text-slate-600 text-xs transition"
                      >
                        ℹ️
                      </button>
                    </div>
                    <div className="text-[11px] text-slate-400 truncate max-w-sm">
                      {current?.title || "专属助手会话"}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-xs">
                    💬
                  </span>
                  <div>
                    <span className="text-xs font-bold text-slate-800">
                      {current?.title || "通用对话"}
                    </span>
                    <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.2 text-[10px] text-slate-500">
                      默认助手
                    </span>
                  </div>
                </div>
              )}
            </div>

            <div className="text-[11px] text-slate-400 flex items-center gap-2">
              {streaming ? (
                <span className="inline-flex items-center gap-1.5 text-indigo-600 font-medium animate-pulse">
                  <span className="h-2 w-2 rounded-full bg-indigo-600" />
                  正在生成回答与富交互组件...
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-slate-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  就绪
                </span>
              )}
            </div>
          </div>

          <MessageList messages={messages} onInteract={handleInteract} />
          <Composer onSend={handleSend} disabled={streaming} />
        </main>
      </div>

      {/* Assistant Details Modal */}
      {showAsstModal && currentAssistant && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-xl">🤖</span>
                <div>
                  <h3 className="font-bold text-sm text-slate-900">{currentAssistant.name}</h3>
                  <span className="font-mono text-xs text-slate-400">v{currentAssistant.version}</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowAsstModal(false)}
                className="text-slate-400 hover:text-slate-600 text-sm"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <span className="font-semibold text-slate-700">助手描述：</span>
                <p className="mt-1 text-slate-600 leading-relaxed bg-slate-50 p-3 rounded-lg border border-slate-100">
                  {currentAssistant.description || "暂无描述"}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
                  <span className="text-slate-500">作者 / 发布者:</span>
                  <div className="font-semibold text-slate-800 mt-0.5">{currentAssistant.author || "官方平台"}</div>
                </div>
                <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-100">
                  <span className="text-slate-500">运行模型:</span>
                  <div className="font-mono font-semibold text-slate-800 mt-0.5">{currentAssistant.model || "默认模型"}</div>
                </div>
              </div>

              {currentAssistant.depends_on && currentAssistant.depends_on.length > 0 && (
                <div>
                  <span className="font-semibold text-slate-700">复用的平台共享能力 (depends_on)：</span>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {currentAssistant.depends_on.map((dep, idx) => (
                      <span
                        key={idx}
                        className="rounded bg-indigo-50 border border-indigo-100 px-2 py-0.5 font-mono text-[10px] text-indigo-700"
                      >
                        {dep}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setShowAsstModal(false)}
                className="rounded-lg bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Home() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center bg-slate-50 text-xs text-slate-400">
          加载工作台...
        </div>
      }
    >
      <ChatHome />
    </Suspense>
  );
}
