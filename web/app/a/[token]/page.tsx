"use client";

/**
 * 助手独立访问页(T18.20):/a/{access_token} —— 开发者运营自有用户的白牌入口。
 * 纯聊天体验:无导航/抽屉/工作台,用户不感知平台;轻注册(昵称即用)。
 */
import { use, useCallback, useEffect, useRef, useState } from "react";
import Composer from "../../../components/chat/Composer";
import MessageList from "../../../components/chat/MessageList";
import { API_BASE, getAuthHeader } from "../../../lib/api/client";
import type { AssistantInfo, ChatMessage, ContentBlock, ToolCallInfo } from "../../../lib/types";

interface AccessInfo {
  plugin_id: string;
  name: string;
  display_name: string;
  description: string;
}

interface Entry {
  token: string;
  sessionId: string;
}

const ENTRY_KEY = "agentplatform_assist_entry";

export default function AssistantAccessPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [info, setInfo] = useState<AccessInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needJoin, setNeedJoin] = useState(false);
  const [nickname, setNickname] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // 1. 解析令牌 → 助手信息
  useEffect(() => {
    fetch(`${API_BASE}/assistant-access/${token}`)
      .then(async (r) => (r.ok ? setInfo(await r.json()) : setError("链接无效或助手未发布")))
      .catch(() => setError("无法连接服务"));
  }, [token]);

  // 2. 本地凭据 → 恢复/创建会话
  const openSession = useCallback(
    async (pluginId: string) => {
      let entry: Entry | null = null;
      try {
        entry = JSON.parse(localStorage.getItem(ENTRY_KEY) || "null");
      } catch { entry = null; }
      if (entry?.token === token && entry.sessionId) {
        const hist = await fetch(`${API_BASE}/chat/sessions/${entry.sessionId}/messages`, {
          headers: getAuthHeader(),
        });
        if (hist.ok) {
          setMessages(await hist.json());
          return;
        }
      }
      const created = await fetch(`${API_BASE}/chat/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeader() },
        body: JSON.stringify({ plugin_id: pluginId }),
      });
      if (!created.ok) throw new Error("会话创建失败");
      const s = await created.json();
      localStorage.setItem(ENTRY_KEY, JSON.stringify({ token, sessionId: s.id }));
    },
    [token],
  );

  useEffect(() => {
    if (!info) return;
    const platformToken = localStorage.getItem("agentplatform_token");
    if (platformToken) {
      openSession(info.plugin_id).catch(() => setNeedJoin(true));
    } else {
      setNeedJoin(true);
    }
  }, [info, openSession]);

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
    openSession(info.plugin_id).catch(() => setError("会话创建失败"));
  };

  // 4. 发送(SSE 流式;逻辑与主站一致但独立轻量实现)
  const send = async (text: string) => {
    let entry: Entry | null = null;
    try { entry = JSON.parse(localStorage.getItem(ENTRY_KEY) || "null"); } catch { entry = null; }
    if (!entry?.sessionId || streaming) return;
    setStreaming(true);
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", text, blocks: [{ type: "markdown", data: { text } }] };
    const asstId = `a-${Date.now()}`;
    setMessages((ms) => [...ms, userMsg, { id: asstId, role: "assistant", text: "", blocks: [], toolCalls: [] }]);
    const patch = (fn: (m: ChatMessage) => ChatMessage) =>
      setMessages((ms) => ms.map((m) => (m.id === asstId ? fn(m) : m)));
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const resp = await fetch(`${API_BASE}/chat/sessions/${entry.sessionId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeader() },
        body: JSON.stringify({ content: text }),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
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
          try { d = JSON.parse(data); } catch { /* 保留原文 */ }
          if (ev === "delta") {
            const t = (d as { text?: string }).text ?? "";
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
    } catch {
      patch((m) => ({ ...m, text: m.text || "[已中断]" }));
    } finally {
      setStreaming(false);
      abortRef.current = null;
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
      <header className="flex items-center gap-2.5 border-b border-slate-200 bg-white px-5 py-3.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 text-base">🤖</span>
        <div>
          <div className="text-sm font-bold text-slate-800">{info.display_name}</div>
          <div className="text-[11px] text-slate-400">{streaming ? "正在回复…" : "随时为你服务"}</div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 overflow-y-auto px-4 py-6">
        <MessageList
          messages={messages}
          streaming={streaming}
          onInteract={undefined}
        />
      </main>
      <div className="border-t border-slate-200 bg-white px-4 py-3">
        <div className="mx-auto max-w-3xl">
          <Composer onSend={(t) => void send(t)} disabled={streaming} onStop={() => abortRef.current?.abort()} />
        </div>
      </div>
    </div>
  );
}
