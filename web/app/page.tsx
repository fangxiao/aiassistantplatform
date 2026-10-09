"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Composer from "../components/chat/Composer";
import { ProviderModal } from "../components/chat/ProviderModal";
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
  createShare,
  continueChat,
  resumeChat,
  regenerateLast,
  sendMessage,
  updateSessionKbs,
  fetchAutoPool,
  setSessionModel,
} from "../lib/api/chat";
import { apiGet, apiPost } from "../lib/api/client";
import { getUser, isAuthed } from "../lib/api/auth";
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
  // 上下文摘要(设计 016 §4 P3.3 尾项):会话级滚动摘要查看入口
  const [summary, setSummary] = useState<{ text: string | null } | null>(null);
  // 任务实体(M28/需求 017):会话提升状态与轻提示
  const [promotedTaskIds, setPromotedTaskIds] = useState<Set<string>>(new Set());
  const [taskToast, setTaskToast] = useState<string | null>(null);
  // 会话产出收藏(设计 008 §11):记录待收藏正文与来源
  const [kbSaveTarget, setKbSaveTarget] = useState<{ content: string; source: { app: string; session_id?: string; message_id?: string } } | null>(null);

  // 门禁
  useEffect(() => {
    if (!isAuthed()) {
      router.replace("/auth");
    }
  }, [router]);

  // 角色检测(admin 才显示飞书通道会话入口)
  useEffect(() => {
    const u = getUser();
    setIsAdmin(u?.role === "admin");
  }, []);

  const selectSession = useCallback(async (s: SessionInfo) => {
    setCurrent(s);
    try {
      const history = await getHistory(s.id);
      setMessages(history);
    } catch {
      setMessages([]);
    }
  }, []);

  // 飞书通道会话视图(admin;需求 012 A5)
  const [showChannelView, setShowChannelView] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);

  const refreshSessions = useCallback(async () => {
    try {
      const list = await listSessions(showChannelView ? "channel" : undefined);
      setSessions(list);
      return list;
    } catch {
      return [];
    }
  }, [showChannelView]);

  const toggleChannelView = useCallback(() => {
    setShowChannelView((v) => {
      const next = !v;
      // 切回我的会话时清掉当前选中,避免停留在打不开的通道会话上下文
      if (!next) setCurrent(null);
      return next;
    });
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

  // 产品成熟度③:会话分享(生成只读链接并复制)
  const handleShareSession = useCallback(async (id: string) => {
    try {
      const r = await createShare(id, 7);
      const base = typeof window !== "undefined" ? window.location.origin : "";
      const url = `${base}/share/${r.share_token}`;
      await navigator.clipboard.writeText(url);
      alert(`分享链接已复制(${new Date(r.expires_at).toLocaleDateString("zh-CN")} 前有效):\n${url}`);
    } catch (err) {
      alert(`分享失败: ${err instanceof Error ? err.message : err}`);
    }
  }, []);

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
      let terminated = false;
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
          } else if (ev.event === "done") {
            terminated = true;
          }
        }
        if (!terminated) {
          patch((m) => ({
            ...m,
            text: m.text + "\n\n[连接中断] 流式响应意外结束(未收到完成事件),请重试;反复出现请反馈平台。",
          }));
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
            const d = ev.data as { message?: string; resumable?: boolean; message_id?: string };
            if (d.resumable && d.message_id) {
              // 断点续跑(ADR 0009):检查点已落库,标记该消息可从断点继续
              patch((m) => ({
                ...m,
                resumable: d.message_id ?? null,
                text: m.text + "\n\n[连接中断,已保留以上内容]",
              }));
            } else {
              patch((m) => ({
                ...m,
                text: m.text + `\n\n[错误] ${d.message ?? "未知"}`,
              }));
            }
          }
        }
      } catch (e) {
        // 用户主动停止(AbortError):服务端已把 partial 转正式,不标可续跑;
        // 其他异常(网络断开等):服务端留有检查点草稿,标记可从断点续跑
        const aborted = e instanceof DOMException && e.name === "AbortError";
        patch((m) => ({
          ...m,
          resumable: !aborted ? (m.resumable ?? "latest") : m.resumable,
          text: aborted ? m.text || "[已中断]" : m.text + `\n\n[错误] ${String(e)}`,
        }));
      } finally {
        setStreaming(false);
        refreshSessions();
      }
    },
    [current, streaming, refreshSessions]
  );
  // 断点续跑(设计 016 §2 / ADR 0009):从中断草稿处继续,产物原地并入该气泡
  const handleResumeDraft = useCallback(
    async (bubbleId: string, draftId: string) => {
      if (!current || streaming) return;
      setStreaming(true);
      let target = bubbleId;
      const patch = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((ms) => ms.map((m) => (m.id === target ? fn(m) : m)));
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        for await (const ev of resumeChat(current.id, controller.signal)) {
          if (ev.event === "resume_started") {
            // 气泡 id 原地切换为服务端草稿行 id,后续事件继续命中
            const d = ev.data as { message_id?: string };
            const newId = d.message_id ?? target;
            setMessages((ms) => ms.map((m) => (m.id === target ? { ...m, id: newId } : m)));
            target = newId;
          } else if (ev.event === "delta") {
            const d = ev.data as { text?: string };
            patch((m) => ({ ...m, text: m.text + (d.text ?? "") }));
          } else if (ev.event === "block_meta") {
            const block = ev.data as ContentBlock;
            patch((m) => ({ ...m, blocks: [...(m.blocks ?? []), block] }));
          } else if (ev.event === "tool_call") {
            const d = ev.data as ToolCallInfo;
            patch((m) => ({ ...m, toolCalls: [...(m.toolCalls ?? []), d] }));
          } else if (ev.event === "done") {
            patch((m) => ({ ...m, resumable: null }));
          } else if (ev.event === "error") {
            const d = ev.data as { message?: string };
            patch((m) => ({ ...m, text: m.text + `\n\n[错误] ${d.message ?? "未知"}` }));
          }
        }
      } catch (e) {
        patch((m) => ({ ...m, text: m.text + `\n\n[错误] ${String(e)}` }));
      } finally {
        setStreaming(false);
      }
    },
    [current, streaming]
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
      // 交互回填后自动续跑(表单提交/确认类动作):agent 以回填消息为当前轮直接继续,
      // 用户无需再手动输入"继续"
      // 表单判定与后端同构:除约定命名外,value 含 fields 数组即视为表单提交
      // (input.form 允许自定义 action 名,不能只靠命名匹配,否则表现为"提交后无响应")
      const isFormSubmit =
        action === "input.form" ||
        action.endsWith("form_submit") ||
        Boolean(value && typeof value === "object" && Array.isArray((value as { fields?: unknown }).fields));
      const isConfirm = action === "input.confirm" || action.endsWith("confirm");
      if (isFormSubmit || isConfirm) {
        setStreaming(true);
        const asstId = nid("a");
        setMessages((prev) => [
          ...prev,
          { id: asstId, role: "assistant", text: "", blocks: [], toolCalls: [] },
        ]);
        const patch = (fn: (m: ChatMessage) => ChatMessage) =>
          setMessages((ms) => ms.map((m) => (m.id === asstId ? fn(m) : m)));
        const controller = new AbortController();
        abortRef.current = controller;
        try {
          for await (const ev of continueChat(current.id, controller.signal)) {
            if (ev.event === "reasoning") {
              const d = ev.data as { text?: string };
              patch((m) => ({ ...m, reasoning: (m.reasoning ?? "") + (d.text ?? "") }));
            } else if (ev.event === "delta") {
              const d = ev.data as { text?: string };
              patch((m) => ({ ...m, reasoning: undefined, text: m.text + (d.text ?? "") }));
            } else if (ev.event === "block_meta") {
              const block = ev.data as ContentBlock;
              patch((m) => ({ ...m, blocks: [...(m.blocks ?? []), block] }));
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
              const d = ev.data as { message?: string; resumable?: boolean };
              if (d.resumable) {
                patch((m) => ({
                  ...m,
                  resumable: m.resumable ?? "latest",
                  text: m.text + "\n\n[连接中断,已保留以上内容]",
                }));
              } else {
                patch((m) => ({ ...m, text: m.text + `\n\n[错误] ${d.message ?? "未知"}` }));
              }
            }
          }
        } catch {
          patch((m) => ({ ...m, text: m.text || "[已中断]" }));
        } finally {
          setStreaming(false);
          abortRef.current = null;
          void refreshSessions();
        }
      }
    } catch (err) {
      alert(`交互处理失败: ${err instanceof Error ? err.message : err}`);
    }
  };

  const currentAssistant = assistants.find((a) => a.id === current?.plugin_id);

  // 会话级模型动态切换(T18.19):auto 池下拉,override 即时生效;
  // M29:目录升级三组(平台网关/我的供应商/平台共享),自定义模型可选
  const [autoPool, setAutoPool] = useState<string[]>([]);
  const [poolLoading, setPoolLoading] = useState(false);
  const [catalog, setCatalog] = useState<
    { model: string; source: string; provider: string | null }[]
  >([]);
  const [showProviderModal, setShowProviderModal] = useState(false);
  const loadCatalog = useCallback(() => {
    apiGet<{ models: { model: string; source: string; provider: string | null }[] }>("/llm/models")
      .then((d) => setCatalog(d.models || []))
      .catch(() => setCatalog([]));
  }, []);
  useEffect(() => {
    loadCatalog();
  }, [loadCatalog]);
  useEffect(() => {
    if (!current || autoPool.length > 0 || poolLoading) return;
    setPoolLoading(true);
    fetchAutoPool()
      .then(setAutoPool)
      .catch(() => setAutoPool([]))
      .finally(() => setPoolLoading(false));
  }, [current, autoPool.length, poolLoading]);
  const changeSessionModel = useCallback(
    async (model: string) => {
      if (!current) return;
      try {
        await setSessionModel(current.id, model === "auto" ? null : model);
        setCurrent({ ...current, model_override: model === "auto" ? null : model });
        void refreshSessions();
      } catch (err) {
        alert(`模型切换失败: ${err instanceof Error ? err.message : err}`);
      }
    },
    [current, refreshSessions],
  );

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
          onContinue={async (sessionId) => {
            // 定时任务新建的执行会话可能不在前端快照里(20261009 E2E 发现):
            // 找不到时先拉最新列表再选,避免静默落回当前会话
            let s = sessions.find((x) => x.id === sessionId);
            if (!s) {
              const list = await refreshSessions();
              s = list.find((x) => x.id === sessionId);
            }
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
          showChannelView={showChannelView}
          onToggleChannelView={toggleChannelView}
          canViewChannel={isAdmin}
          onSelect={(id) => {
            const s = sessions.find((x) => x.id === id);
            if (s) selectSession(s);
          }}
          onCreate={handleCreateSession}
          onRename={handleRenameSession}
          onDelete={handleDeleteSession}
          onShare={handleShareSession}
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
                    <div className="flex items-center gap-2">
                      <div className="text-[11px] text-slate-400 truncate max-w-sm">
                        {current?.title || "专属助手会话"}
                      </div>
                      {current && (
                        <>
                          <select
                            value={current.model_override || "auto"}
                            onChange={(e) => void changeSessionModel(e.target.value)}
                            className="rounded-md border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] text-slate-600 hover:border-indigo-300"
                            title="会话模型:切换后下一条消息生效(auto=平台智能路由)"
                          >
                            <optgroup label="平台网关(默认)">
                              <option value="auto">⚡ auto(智能路由)</option>
                              {autoPool.filter((m) => m !== "auto").map((m) => (
                                <option key={`gw-${m}`} value={m}>{m}</option>
                              ))}
                            </optgroup>
                            {catalog
                              .filter((m) => m.source === "personal")
                              .reduce<{ name: string; models: string[] }[]>((groups, m) => {
                                const g = groups.find((x) => x.name === (m.provider || "导入的端点"));
                                if (g) g.models.push(m.model);
                                else groups.push({ name: m.provider || "导入的端点", models: [m.model] });
                                return groups;
                              }, [])
                              .map((g) => (
                                <optgroup key={g.name} label={`我的供应商 · ${g.name}`}>
                                  {g.models.map((m) => (
                                    <option key={`p-${m}`} value={m}>{m}</option>
                                  ))}
                                </optgroup>
                              ))}
                            {catalog.filter((m) => m.source === "platform").length > 0 && (
                              <optgroup label="平台共享">
                                {catalog
                                  .filter((m) => m.source === "platform")
                                  .map((m) => (
                                    <option key={`s-${m.model}`} value={m.model}>{m.model}</option>
                                  ))}
                              </optgroup>
                            )}
                          </select>
                          <button
                            type="button"
                            onClick={() => setShowProviderModal(true)}
                            className="rounded-md border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-slate-600 hover:border-indigo-300 hover:text-indigo-600"
                            title="添加自定义模型供应商(自带 API Key)"
                          >
                            +
                          </button>
                        </>
                      )}
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
              {current && (
                <button
                  type="button"
                  onClick={() => {
                    void apiGet<{ text: string | null }>(`/chat/sessions/${current.id}/summary`)
                      .then((r) => setSummary({ text: r.text }))
                      .catch(() => setSummary({ text: null }));
                  }}
                  title="查看本会话的上下文滚动摘要(长对话自动压缩)"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 font-medium text-slate-600 transition hover:bg-slate-100"
                >
                  <span>📝</span>
                  <span>摘要</span>
                </button>
              )}
              {current && !promotedTaskIds.has(current.id) && (
                <button
                  type="button"
                  onClick={() => {
                    const title = window.prompt("任务名称:", current.title || "未命名任务");
                    if (!title) return;
                    void apiPost<{ id: string }>(`/tasks/from-session/${current.id}`, { title })
                      .then(() => {
                        setPromotedTaskIds((s) => new Set(s).add(current.id));
                        setTaskToast("⭐ 已保存为任务(工作台任务中心可管理)");
                        window.dispatchEvent(new Event("ap:tasks-changed"));
                      })
                      .catch((err: unknown) => {
                        setTaskToast(
                          String(err).includes("409") ? "该会话已是任务" : "保存任务失败",
                        );
                      });
                    setTimeout(() => setTaskToast(null), 2500);
                  }}
                  title="把本会话保存为任务:命名、归集交付物、可完成/归档"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 font-medium text-amber-700 transition hover:bg-amber-100"
                >
                  <span>⭐</span>
                  <span>保存为任务</span>
                </button>
              )}
              {taskToast && <span className="text-[10px] text-emerald-600">{taskToast}</span>}
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
            onResume={(m) => {
              if (m.resumable) void handleResumeDraft(m.id, m.resumable);
            }}
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

      {/* 上下文摘要弹窗(设计 016 §4;无摘要时说明触发条件) */}
      {/* M29:添加自定义模型供应商(会话选择器直达) */}
      {showProviderModal && (
        <ProviderModal
          onClose={() => setShowProviderModal(false)}
          onCreated={loadCatalog}
        />
      )}

      {summary && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-sm font-bold text-slate-900">📝 上下文摘要</h3>
              <button
                type="button"
                onClick={() => setSummary(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                ✕
              </button>
            </div>
            <div className="mt-3 max-h-80 overflow-y-auto text-xs leading-relaxed text-slate-700">
              {summary.text ? (
                <pre className="whitespace-pre-wrap font-sans">{summary.text}</pre>
              ) : (
                <p className="text-slate-400">
                  本会话暂无摘要——历史超阈值后自动生成滚动压缩(上下文管理,ADR 0011),无需手动触发。
                </p>
              )}
            </div>
          </div>
        </div>
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
