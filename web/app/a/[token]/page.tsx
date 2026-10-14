"use client";

/**
 * 助手独立访问页(T18.20):/a/{access_token} —— 开发者运营自有用户的白牌入口。
 * 纯聊天体验:无导航/工作台,轻注册(昵称即用);支持多会话(新建/切换)。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import Composer from "../../../components/chat/Composer";
import MessageList from "../../../components/chat/MessageList";
import { API_BASE, getAuthHeader } from "../../../lib/api/client";
import type { ChatMessage, ContentBlock, ToolCallInfo } from "../../../lib/types";

interface AccessInfo {
  plugin_id: string;
  name: string;
  display_name: string;
  description: string;
  guidance?: string[]; // M39:插件方提供的引导语
}

interface SessionMeta {
  id: string;
  title: string;
  updatedAt: number;
}

interface Entry {
  token: string;
  sessionId: string;
  sessions: SessionMeta[];
}

const ENTRY_KEY = "agentplatform_assist_entry";

export default function AssistantAccessPage({ params }: { params: { token: string } }) {
  const { token } = params;
  const [info, setInfo] = useState<AccessInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needJoin, setNeedJoin] = useState(false);
  const [nickname, setNickname] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [showSessions, setShowSessions] = useState(false);
  const [sessionList, setSessionList] = useState<SessionMeta[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const readEntry = (): Entry | null => {
    try {
      return JSON.parse(localStorage.getItem(ENTRY_KEY) || "null");
    } catch {
      return null;
    }
  };

  const writeEntry = (e: Entry) => localStorage.setItem(ENTRY_KEY, JSON.stringify(e));

  const loadSessionHistory = useCallback(async (sid: string) => {
    const hist = await fetch(`${API_BASE}/chat/sessions/${sid}/messages`, {
      headers: getAuthHeader(),
    });
    if (!hist.ok) return false;
    setMessages(await hist.json());
    setCurrentSessionId(sid);
    return true;
  }, []);

  const createNewSession = useCallback(
    async (pluginId: string) => {
      const created = await fetch(`${API_BASE}/chat/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeader() },
        body: JSON.stringify({ plugin_id: pluginId }),
      });
      if (!created.ok) throw new Error("会话创建失败");
      const s = await created.json();
      const entry = readEntry();
      const meta: SessionMeta = { id: s.id, title: "新对话", updatedAt: Date.now() };
      const newEntry: Entry = {
        token,
        sessionId: s.id,
        sessions: [meta, ...(entry?.sessions ?? []).filter((x) => x.id !== s.id)].slice(0, 20),
      };
      writeEntry(newEntry);
      setSessionList(newEntry.sessions);
      setMessages([]);
      setCurrentSessionId(s.id);
    },
    [token],
  );

  // 1. 解析令牌 → 助手信息
  useEffect(() => {
    fetch(`${API_BASE}/assistant-access/${token}`)
      .then(async (r) => (r.ok ? setInfo(await r.json()) : setError("链接无效或助手未发布")))
      .catch(() => setError("无法连接服务"));
  }, [token]);

  // 2. 本地凭据 → 恢复最近会话或创建新会话
  const initSession = useCallback(
    async (pluginId: string) => {
      const entry = readEntry();
      if (entry?.token === token && entry.sessionId) {
        if (await loadSessionHistory(entry.sessionId)) {
          setSessionList(entry.sessions ?? []);
          return;
        }
      }
      await createNewSession(pluginId);
    },
    [token, loadSessionHistory, createNewSession],
  );

  useEffect(() => {
    if (!info) return;
    const platformToken = localStorage.getItem("agentplatform_token");
    if (platformToken) {
      initSession(info.plugin_id).catch(() => setNeedJoin(true));
    } else {
      setNeedJoin(true);
    }
  }, [info, initSession]);

  // 3. 轻注册
  const join = async () => {
    if (!info || !nickname.trim()) return;
    const r = await fetch(`${API_BASE}/assistant-access/${token}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nickname: nickname.trim() }),
    });
    if (!r.ok) {
      setError("加入失败,请稍后再试");
      return;
    }
    const d = await r.json();
    localStorage.setItem("agentplatform_token", d.token);
    localStorage.setItem("agentplatform_user", JSON.stringify(d.user));
    setNeedJoin(false);
    createNewSession(info.plugin_id).catch(() => setError("会话创建失败"));
  };

  // 4. 发送(SSE 流式)
  const send = async (text: string) => {
    const sid = currentSessionId;
    if (!sid || streaming) return;
    setStreaming(true);
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", text, blocks: [{ type: "markdown", data: { text } }] };
    const asstId = `a-${Date.now()}`;
    setMessages((ms) => [...ms, userMsg, { id: asstId, role: "assistant", text: "", blocks: [], toolCalls: [] }]);
    const patch = (fn: (m: ChatMessage) => ChatMessage) =>
      setMessages((ms) => ms.map((m) => (m.id === asstId ? fn(m) : m)));
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const resp = await fetch(`${API_BASE}/chat/sessions/${sid}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeader() },
        body: JSON.stringify({ content: text }),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let lastDelta = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx: number;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          let ev = "message";
          let data = "";
          for (const line of frame.split("\n")) {
            if (line.startsWith("event: ")) ev = line.slice(7);
            else if (line.startsWith("data: ")) data += line.slice(6);
          }
          if (!data) continue;
          let d: unknown = data;
          try {
            d = JSON.parse(data);
          } catch {
            /* 保留原文 */
          }
          if (ev === "delta") {
            const t = (d as { text?: string }).text ?? "";
            lastDelta += t;
            patch((m) => ({ ...m, reasoning: undefined, text: m.text + t }));
          } else if (ev === "reasoning") {
            const t = (d as { text?: string }).text ?? "";
            patch((m) => ({ ...m, reasoning: (m.reasoning ?? "") + t }));
          } else if (ev === "block_meta") {
            patch((m) => ({ ...m, blocks: [...(m.blocks ?? []), d as ContentBlock] }));
          } else if (ev === "tool_call") {
            patch((m) => ({ ...m, toolCalls: [...(m.toolCalls ?? []), d as ToolCallInfo] }));
          } else if (ev === "error") {
            patch((m) => ({ ...m, text: m.text + `\n\n[错误] ${(d as { message?: string }).message ?? "未知"}` }));
          }
        }
      }
      // 流结束:更新会话标题(首条消息摘要)并持久化
      if (lastDelta.trim()) {
        const entry = readEntry();
        if (entry) {
          const title = text.slice(0, 20) || "新对话";
          const updated = {
            ...entry,
            sessions: (entry.sessions ?? []).map((s) =>
              s.id === sid ? { ...s, title, updatedAt: Date.now() } : s,
            ),
          };
          writeEntry(updated);
          setSessionList(updated.sessions);
        }
      }
    } catch {
      patch((m) => ({ ...m, text: m.text || "[已中断]" }));
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const switchSession = async (sid: string) => {
    setShowSessions(false);
    if (sid === currentSessionId) return;
    if (await loadSessionHistory(sid)) {
      const entry = readEntry();
      if (entry) {
        writeEntry({ ...entry, sessionId: sid });
      }
    }
  };

  // M39:交互组件回调(input.select/confirm/form 等)——白牌页此前未接线导致组件"死"
  const handleInteract = async (action: string, value: unknown, args?: Record<string, unknown>) => {
    const sid = currentSessionId;
    if (!sid) return;
    try {
      const resp = await fetch(`${API_BASE}/chat/sessions/${sid}/blocks/${action}/interact`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeader() },
        body: JSON.stringify({ action, value, args }),
      });
      if (!resp.ok) return;
      const result = await resp.json();
      // 将返回的 blocks 追加为新消息
      if (result?.blocks?.length) {
        const newMsg: ChatMessage = {
          id: `i-${Date.now()}`,
          role: "assistant",
          text: "",
          blocks: result.blocks,
          toolCalls: [],
        };
        setMessages((ms) => [...ms, newMsg]);
      }
    } catch {
      // 交互失败静默(组件本地状态不受影响)
    }
  };

  const newSession = async () => {
    if (!info || streaming) return;
    setShowSessions(false);
    try {
      await createNewSession(info.plugin_id);
    } catch {
      setError("新建失败,请重试");
    }
  };

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50">
        <div className="text-center text-sm text-slate-500">😕 {error}</div>
      </div>
    );
  }
  if (!info) {
    return <div className="flex h-screen items-center justify-center bg-slate-50 text-sm text-slate-400">加载中…</div>;
  }
  if (needJoin) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 px-6">
        <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="mb-1 text-center text-xl font-bold text-slate-800">{info.display_name}</div>
          {info.description && <div className="mb-6 text-center text-xs text-slate-400">{info.description.slice(0, 60)}</div>}
          <input
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void join()}
            placeholder="怎么称呼你?"
            className="mb-4 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-indigo-500"
            autoFocus
          />
          <button
            type="button"
            onClick={() => void join()}
            disabled={!nickname.trim()}
            className="w-full rounded-xl bg-slate-900 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40"
          >
            开始对话
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-slate-50">
      <header className="relative flex items-center gap-2.5 border-b border-slate-200 bg-white px-5 py-3.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 text-base">🤖</span>
        <div className="flex-1">
          <div className="text-sm font-bold text-slate-800">{info.display_name}</div>
          <div className="text-[11px] text-slate-400">{streaming ? "正在回复…" : "随时为你服务"}</div>
        </div>
        <button
          type="button"
          onClick={() => void newSession()}
          disabled={streaming}
          className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-600 transition hover:bg-indigo-100 disabled:opacity-40"
        >
          ＋ 新对话
        </button>
        {sessionList.length > 1 && (
          <button
            type="button"
            onClick={() => setShowSessions((v) => !v)}
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-500 transition hover:bg-slate-50"
            title="历史会话"
          >
            📜 {sessionList.length}
          </button>
        )}
        {showSessions && (
          <div className="absolute right-4 top-full z-20 mt-1 w-64 rounded-xl border border-slate-200 bg-white shadow-lg">
            {sessionList.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => void switchSession(s.id)}
                className={`block w-full truncate px-4 py-2.5 text-left text-xs transition hover:bg-slate-50 ${
                  s.id === currentSessionId ? "font-semibold text-indigo-600" : "text-slate-600"
                }`}
              >
                {s.id === currentSessionId ? "▸ " : ""}
                {s.title}
              </button>
            ))}
          </div>
        )}
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 overflow-y-auto px-4 py-6">
        {messages.length === 0 && !streaming && (
          <div className="flex flex-col items-center justify-center py-16">
            <span className="mb-4 text-4xl">🤖</span>
            <h2 className="mb-2 text-lg font-bold text-slate-800">{info.display_name}</h2>
            {info.description && (
              <p className="mb-6 max-w-md text-center text-xs leading-relaxed text-slate-500">
                {info.description}
              </p>
            )}
            <div className="w-full max-w-md space-y-2">
              {(info.guidance?.length ? info.guidance : ["有什么可以帮你的？直接开始提问吧"]).map((g, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => void send(g)}
                  className="block w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-xs text-slate-600 transition hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700"
                >
                  💬 {g}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.length > 0 && (
          <MessageList
            messages={messages}
            streaming={streaming}
            onInteract={handleInteract}
          />
        )}
      </main>
      <div className="border-t border-slate-200 bg-white px-4 py-3">
        <div className="mx-auto max-w-3xl">
          <Composer onSend={(t) => void send(t)} disabled={streaming} onStop={() => abortRef.current?.abort()} />
        </div>
      </div>
    </div>
  );
}
