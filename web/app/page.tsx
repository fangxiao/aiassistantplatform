// 对话页(T8.1):会话选择/创建 + 消息流 + SSE 流式渲染 + 工具调用徽标

"use client";

import { useCallback, useEffect, useState } from "react";
import Composer from "../components/chat/Composer";
import MessageList from "../components/chat/MessageList";
import {
  createSession,
  getHistory,
  listSessions,
  sendMessage,
} from "../lib/api/chat";
import type { ChatMessage, SessionInfo, ToolCallInfo } from "../lib/types";

let tempSeq = 0;
const nid = (prefix: string) => `${prefix}-${Date.now()}-${tempSeq++}`;

export default function Home() {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [current, setCurrent] = useState<SessionInfo | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);

  const selectSession = useCallback(async (s: SessionInfo) => {
    setCurrent(s);
    setMessages(await getHistory(s.id));
  }, []);

  useEffect(() => {
    (async () => {
      let list = await listSessions();
      if (list.length === 0) {
        const s = await createSession();
        list = [s];
      }
      setSessions(list);
      await selectSession(list[0]);
    })();
  }, [selectSession]);

  const refreshSessions = useCallback(async () => {
    setSessions(await listSessions());
  }, []);

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
        toolCalls: [],
      };
      setMessages((ms) => [...ms, userMsg, asstMsg]);

      const patch = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((ms) => ms.map((m) => (m.id === asstId ? fn(m) : m)));

      try {
        for await (const ev of sendMessage(current.id, content)) {
          if (ev.event === "delta") {
            const d = ev.data as { text?: string };
            patch((m) => ({ ...m, text: m.text + (d.text ?? "") }));
          } else if (ev.event === "tool_call") {
            const d = ev.data as ToolCallInfo;
            patch((m) => ({ ...m, toolCalls: [...(m.toolCalls ?? []), d] }));
          } else if (ev.event === "done") {
            const d = ev.data as { message_id?: string };
            patch((m) => ({ ...m, id: d.message_id ?? m.id }));
          } else if (ev.event === "error") {
            const d = ev.data as { message?: string };
            patch((m) => ({ ...m, text: m.text + `\n\n[错误] ${d.message ?? "未知"}` }));
          }
        }
      } catch (e) {
        patch((m) => ({ ...m, text: m.text + `\n\n[错误] ${String(e)}` }));
      } finally {
        setStreaming(false);
        refreshSessions();
      }
    },
    [current, streaming, refreshSessions],
  );

  return (
    <main className="flex h-screen flex-col">
      <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-2">
        <h1 className="text-lg font-bold">agentplatform</h1>
        <select
          className="rounded border border-slate-300 px-2 py-1 text-sm"
          value={current?.id ?? ""}
          onChange={(e) => {
            const s = sessions.find((x) => x.id === e.target.value);
            if (s) selectSession(s);
          }}
        >
          {sessions.map((s) => (
            <option key={s.id} value={s.id}>
              会话 {s.id.slice(0, 8)}
            </option>
          ))}
        </select>
        <button
          className="ml-auto rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-50"
          onClick={async () => {
            const s = await createSession();
            setSessions((ss) => [...ss, s]);
            await selectSession(s);
          }}
        >
          新会话
        </button>
      </header>
      <MessageList messages={messages} />
      <Composer onSend={handleSend} disabled={streaming} />
    </main>
  );
}
