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
import { isAuthed } from "../lib/api/auth";
import type { ChatMessage, ContentBlock, SessionInfo, ToolCallInfo } from "../lib/types";

let tempSeq = 0;
const nid = (prefix: string) => `${prefix}-${Date.now()}-${tempSeq++}`;

function ChatHome() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const querySessionId = searchParams.get("sessionId");


  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [current, setCurrent] = useState<SessionInfo | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [drawerCollapsed, setDrawerCollapsed] = useState(false);

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

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-white">
      <Navbar />

      <div className="flex flex-1 overflow-hidden">
        {/* 左侧会话抽屉 */}
        <SessionDrawer
          sessions={sessions}
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
          <div className="flex h-11 items-center justify-between border-b border-slate-200 bg-white px-4">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-800">
                {current?.title || (current ? `会话 ${current.id.slice(0, 8)}` : "新建对话")}
              </span>
              {current?.plugin_id && (
                <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-medium text-indigo-700 border border-indigo-100">
                  插件助手
                </span>
              )}
            </div>
            <div className="text-[11px] text-slate-400">
              {streaming ? (
                <span className="text-indigo-600 font-medium animate-pulse">● 正在生成回答与组件...</span>
              ) : (
                "就绪"
              )}
            </div>
          </div>

          <MessageList messages={messages} onInteract={handleInteract} />
          <Composer onSend={handleSend} disabled={streaming} />
        </main>
      </div>
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

