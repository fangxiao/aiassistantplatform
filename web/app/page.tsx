"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Composer from "../components/chat/Composer";
import MessageList from "../components/chat/MessageList";
import { Navbar } from "../components/layout/Navbar";
import { WorkbenchView } from "../components/workbench/WorkbenchView";
import { NewSessionModal } from "../components/workbench/NewSessionModal";
import { SessionDrawer } from "../components/chat/SessionDrawer";
import { KbMountModal } from "../components/chat/KbMountModal";
import { SaveToKbModal } from "../components/chat/SaveToKbModal";
import {
  createSession,
  deleteSession,
  getHistory,
  interactBlock,
  listSessions,
  renameSession,
  sendFeedbackEvent,
  regenerateLast,
  sendMessage,
  updateSessionKbs,
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
  // 移动端(<768px)默认折叠抽屉,桌面默认展开
  const [drawerCollapsed, setDrawerCollapsed] = useState(
    () => typeof window !== "undefined" && window.innerWidth < 768
  );
  const [showAsstModal, setShowAsstModal] = useState(false);
  // M14:"新会话"是选择意图而非制造记录——无明确助手时弹选择器,取消不留垃圾会话
  const [showNewSessionModal, setShowNewSessionModal] = useState(false);
  // M14 双视图:工作台 | 对话;两视图常驻挂载(hidden 切换),对话流式不因切换中断
  const [view, setView] = useState<"workbench" | "chat">(() => {
    if (typeof window === "undefined") return "workbench";
    return (localStorage.getItem("workbench_view") as "workbench" | "chat") || "workbench";
  });
  const switchView = (v: "workbench" | "chat") => {
    setView(v);
    localStorage.setItem("workbench_view", v);
  };
  const [showKbModal, setShowKbModal] = useState(false);
  // 会话产出收藏(设计 008 §11):记录待收藏正文与来源
  const [kbSaveTarget, setKbSaveTarget] = useState<{ content: string; source: { app: string; session_id?: string; message_id?: string } } | null>(null);

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

  // 打磨②:流式中断
  const abortRef = React.useRef<AbortController | null>(null);
  const handleStop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  // 打磨②:重新生成最后一条助手回复
  const handleRegenerate = useCallback(
    async (asstId: string) => {
      if (!current || streaming) return;
      setStreaming(true);
      const patch = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((ms) => ms.map((m) => (m.id === asstId ? fn(m) : m)));
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        for await (const ev of regenerateLast(current.id, controller.signal)) {
          if (ev.event === "delta") {
            const d = ev.data as { text?: string };
            patch((m) => ({ ...m, text: m.text + (d.text ?? "") }));
          } else if (ev.event === "block_meta") {
            const block = ev.data as ContentBlock;
            patch((m) => ({ ...m, blocks: [...(m.blocks ?? []), block] }));
          } else if (ev.event === "tool_call") {
            const d = ev.data as ToolCallInfo;
            patch((m) => ({ ...m, toolCalls: [...(m.toolCalls ?? []), d] }));
          }
        }
      } catch {
        patch((m) => ({ ...m, text: m.text || "[已中断]" }));
      } finally {
        setStreaming(false);
        abortRef.current = null;
        void refreshSessions();
      }
    },
    [current, streaming, refreshSessions]
  );

  // 发送普通对话消息
  const handleSend = useCallback(
    async (content: string, images: string[] = [], docUrls: string[] = []) => {
      if (!current || streaming) return;
      setStreaming(true);
      const userMsg: ChatMessage = {
        id: nid("u"),
        role: "user",
        text: content,
        blocks: [
          ...(content ? [{ type: "markdown" as const, data: { text: content } }] : []),
          ...images.map((url) => ({ type: "image" as const, data: { url } })),
          ...docUrls.map((url) => ({
            type: "file" as const,
            data: { name: decodeURIComponent(url.split("/").pop() || "document"), url },
          })),
        ],
      };
      const asstId = nid("a");
      const asstMsg: ChatMessage = {
        id: asstId,
        role: "assistant",
        text: "",
        blocks: [],
        toolCalls: [],
      };
      const controller = new AbortController();
      abortRef.current = controller;
      setMessages((ms) => [...ms, userMsg, asstMsg]);

      const patch = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((ms) => ms.map((m) => (m.id === asstId ? fn(m) : m)));

      try {
        for await (const ev of sendMessage(current.id, content, images, controller.signal, docUrls)) {
          if (ev.event === "reasoning") {
            // 模型深度思考中：在助手消息上实时展示思考进度，不计入正文
            const d = ev.data as { text?: string };
            patch((m) => ({
              ...m,
              reasoning: (m.reasoning ?? "") + (d.text ?? ""),
            }));
          } else if (ev.event === "delta") {
            const d = ev.data as { text?: string };
            patch((m) => ({
              ...m,
              reasoning: undefined,   // 正文开始后清空思考内容
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
            patch((m) => {
              const currentList = m.toolCalls ?? [];
              const matchIndex = currentList.findLastIndex(
                (tc) => tc.id === d.id || (tc.name && tc.name === d.name)
              );
              if (matchIndex >= 0) {
                const copy = [...currentList];
                copy[matchIndex] = d;
                return { ...m, toolCalls: copy };
              }
              return { ...m, toolCalls: [...currentList, d] };
            });
          } else if (ev.event === "done") {
            const d = ev.data as { message_id?: string };
            patch((m) => ({ ...m, id: d.message_id ?? m.id, reasoning: undefined }));
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

  // 保存会话挂载知识库 (M12, T12.13)
  const handleSaveKbs = async (kbIds: string[]) => {
    if (!current) return;
    try {
      await updateSessionKbs(current.id, kbIds);
      setCurrent((prev) => (prev ? { ...prev, mounted_kb_ids: kbIds } : null));
      setShowKbModal(false);
      void refreshSessions();
    } catch (err) {
      alert(`保存挂载失败: ${err instanceof Error ? err.message : err}`);
    }
  };

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

      {/* M14 视图切换条 */}
      <div className="flex h-10 shrink-0 items-center gap-1 border-b border-slate-200 bg-white px-4">
        {(
          [
            { key: "workbench", label: "🏠 工作台" },
            { key: "chat", label: "💬 对话" },
          ] as const
        ).map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => switchView(t.key)}
            className={`rounded-lg px-3 py-1 text-xs font-semibold transition ${
              view === t.key ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-slate-100"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 工作台视图(常驻挂载,hidden 切换) */}
      <div className={view === "workbench" ? "flex-1 overflow-hidden" : "hidden"}>
        <WorkbenchView
          assistants={assistants}
          sessions={sessions}
          onNewSession={(assistantId) => {
            if (assistantId) {
              // 助手卡直达:语境已明确,无需再选
              void handleCreateSession(assistantId);
              switchView("chat");
              return;
            }
            if (assistants.length <= 1) {
              // 助手少时不弹层,别为一个选择多一次点击
              void handleCreateSession(assistants[0]?.id ?? null);
              switchView("chat");
              return;
            }
            setShowNewSessionModal(true);
          }}
          onContinue={(sessionId) => {
            const s = sessions.find((x) => x.id === sessionId);
            if (s) void selectSession(s);
            switchView("chat");
          }}
          onOpenKb={() => router.push("/kb")}
          onSaveToKb={(content) =>
            setKbSaveTarget({ content, source: { app: "workbench", session_id: undefined } })
          }
        />
      </div>

      {/* 对话视图(常驻挂载,hidden 切换) */}
      <div className={view === "chat" ? "flex flex-1 overflow-hidden" : "hidden"}>
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
                        {currentAssistant.display_name || currentAssistant.name}
                      </span>
                      {currentAssistant.display_name && (
                        <span className="font-mono text-[10px] text-slate-400">
                          ({currentAssistant.name})
                        </span>
                      )}
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
              <button
                type="button"
                onClick={() => setShowKbModal(true)}
                title="管理当前会话挂载的知识库"
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-medium transition ${
                  (current?.mounted_kb_ids?.length ?? 0) > 0
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-100"
                }`}
              >
                <span>📚</span>
                <span>
                  知识库 {(current?.mounted_kb_ids?.length ?? 0) > 0 ? `(${current?.mounted_kb_ids?.length})` : "未挂载"}
                </span>
              </button>
              {streaming ? (
                <span className="inline-flex items-center gap-1.5 text-indigo-600 font-medium animate-pulse">
                  <span className="h-2 w-2 rounded-full bg-indigo-600 animate-ping" />
                  生成中
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-slate-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  就绪
                </span>
              )}
            </div>
          </div>

          <MessageList
            messages={messages}
            streaming={streaming}
            onInteract={handleInteract}
            onRegenerate={() => void handleRegenerate(messages[messages.length - 1]?.id ?? "")}
            onSaveToKb={(content) =>
              setKbSaveTarget({ content, source: { app: "platform", session_id: current?.id } })
            }
          />
          <Composer onSend={handleSend} disabled={streaming} onStop={handleStop} />
        </main>
      </div>

      {/* 新会话助手选择器(M14) */}
      {showNewSessionModal && (
        <NewSessionModal
          assistants={assistants}
          onPick={(assistantId) => {
            setShowNewSessionModal(false);
            void handleCreateSession(assistantId);
            switchView("chat");
          }}
          onClose={() => setShowNewSessionModal(false)}
        />
      )}

      {/* Session KB Mount Modal (M12) */}
      {showKbModal && current && (
        <KbMountModal
          sessionId={current.id}
          currentKbIds={current.mounted_kb_ids ?? []}
          onClose={() => setShowKbModal(false)}
          onSave={handleSaveKbs}
        />
      )}

      {/* Save Assistant Message to KB (M12 增补, 设计 008 §11) */}
      {kbSaveTarget && (
        <SaveToKbModal content={kbSaveTarget.content} source={kbSaveTarget.source} onClose={() => setKbSaveTarget(null)} />
      )}

      {/* Assistant Details Modal */}
      {showAsstModal && currentAssistant && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-xl">🤖</span>
                <div>
                  <h3 className="font-bold text-sm text-slate-900">
                    {currentAssistant.display_name || currentAssistant.name}
                  </h3>
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono">
                    <span>{currentAssistant.name}</span>
                    <span>•</span>
                    <span>v{currentAssistant.version}</span>
                  </div>
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
