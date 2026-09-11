// 单条消息:用户气泡 / 助手 ContentBlock 列表 + 工具调用徽标 + 内联流式等待状态

"use client";

import React from "react";
import type { ChatMessage, ContentBlock } from "../../lib/types";
import { BlockRenderer } from "../renderers/BlockRenderer";

interface MessageItemProps {
  message: ChatMessage;
  isStreaming?: boolean;
  isLast?: boolean;
  onInteract?: (action: string, value: any, args?: Record<string, any>) => void;
  onSaveToKb?: (content: string) => void;
}

export default function MessageItem({
  message,
  isStreaming = false,
  isLast = false,
  onInteract,
  onSaveToKb,
}: MessageItemProps) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-slate-900 px-4 py-2.5 text-sm text-white shadow-xs">
          {message.text}
        </div>
      </div>
    );
  }

  const hasBlocks = message.blocks && message.blocks.length > 0;
  const hasText = Boolean(message.text && message.text.trim().length > 0);
  const hasToolCalls = Boolean(message.toolCalls && message.toolCalls.length > 0);
  const isThinking = isStreaming && isLast && Boolean(message.reasoning) && !hasText && !hasBlocks;
  const isActivelyWaiting = isStreaming && isLast && !hasText && !hasBlocks && !message.reasoning;

  const blocks: ContentBlock[] = hasBlocks
    ? (message.blocks as ContentBlock[])
    : [{ type: "markdown", data: { text: message.text || "" } }];

  const runningTool = message.toolCalls?.find((tc) => !tc.result);
  const hasRunningTool = Boolean(runningTool);
  const runningToolName = runningTool?.name || runningTool?.id || "公共技能";
  // 收藏到知识库入口(设计 008 §11.4):有正文且非流式中
  const canSaveToKb = Boolean(onSaveToKb && message.text && message.text.trim() && !(isStreaming && isLast));

  /** 将技术名称映射为对用户友好的中文描述 */
  function friendlyLabel(rawName: string): { icon: string; name: string } {
    const n = (rawName || "").toLowerCase();
    if (n.includes("writewx_write") || n.includes("wechat_write")) return { icon: "✍️", name: "文章撰写" };
    if (n.includes("wechat_official") || n.includes("layout") || n.includes("排版")) return { icon: "🎨", name: "排版规范获取" };
    if (n.includes("writewx_preview") || n.includes("preview")) return { icon: "👁️", name: "文章预览生成" };
    if (n.includes("browser_wechat") || n.includes("wechat_draft") || n.includes("inject")) return { icon: "📤", name: "注入公众号草稿箱" };
    if (n.includes("search") || n.includes("搜索")) return { icon: "🔍", name: "信息搜索" };
    if (n.includes("summarize") || n.includes("总结")) return { icon: "📋", name: "内容整理" };
    if (n.includes("structured") || n.includes("output")) return { icon: "📦", name: "结构化输出" };
    if (n.includes("pdf") || n.includes("parse")) return { icon: "📄", name: "文档解析" };
    if (n.includes("browser") || n.includes("tab")) return { icon: "🌐", name: "浏览器操作" };
    return { icon: "⚙️", name: "任务处理" };
  }

  return (
    <div className="group flex justify-start">
      <div className="relative max-w-[90%] rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
        {canSaveToKb && (
          <button
            type="button"
            title="收藏到知识库"
            onClick={() => onSaveToKb?.(message.text ?? "")}
            className="absolute -top-2.5 right-3 hidden rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] text-slate-500 shadow-xs transition hover:border-indigo-300 hover:text-indigo-600 group-hover:block"
          >
            📚 收藏
          </button>
        )}
        {/* 工具执行进度条（用户友好视图，隐藏技术实现细节） */}
        {hasToolCalls && (
          <div className="mb-3 flex flex-col gap-1.5 border-b border-slate-100 pb-3">
            {message.toolCalls?.map((tc, i) => {
              // 非流式状态（就绪态）或已有明确结果时，均视为执行完毕
              const isDone = !isStreaming || (Boolean(tc.result) && !(isLast && i === (message.toolCalls?.length ?? 1) - 1 && !tc.result));
              const { icon, name } = friendlyLabel(tc.name || tc.id || "");
              const stepResult = tc.result?.startsWith("⚡") ? tc.result.replace(/^⚡\s*\[/, "").replace(/\]$/, "") : null;
              return (
                <div
                  key={i}
                  className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-all ${
                    isDone
                      ? "bg-emerald-50 text-emerald-800"
                      : "bg-amber-50 text-amber-900 animate-pulse"
                  }`}
                  title={`[开发者信息] ${tc.name ?? tc.id}`}  /* 技术名称仅 tooltip 可见 */
                >
                  <span className={`text-base ${isDone ? "" : "animate-spin"}`}>
                    {isDone ? "✅" : icon}
                  </span>
                  <div className="flex flex-col">
                    <span className="font-medium">{isDone ? `${name}完成` : `正在${name}...`}</span>
                    {stepResult && (
                      <span className="text-[11px] opacity-75 mt-0.5">{stepResult}</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* 深度思考中：实时展示推理内容 */}
        {isThinking ? (
          <div className="rounded-xl border border-violet-200 bg-violet-50 px-4 py-3 text-xs text-violet-800">
            <div className="mb-2 flex items-center gap-2 font-semibold text-violet-700">
              <span className="flex h-4 w-4 items-center justify-center rounded-full bg-violet-200 text-violet-700">
                🧠
              </span>
              <span>AI 深度思考中...</span>
              <span className="ml-auto flex space-x-1">
                <span className="h-1.5 w-1.5 rounded-full bg-violet-500 animate-bounce [animation-delay:-0.3s]"></span>
                <span className="h-1.5 w-1.5 rounded-full bg-violet-500 animate-bounce [animation-delay:-0.15s]"></span>
                <span className="h-1.5 w-1.5 rounded-full bg-violet-500 animate-bounce"></span>
              </span>
            </div>
            <div className="max-h-32 overflow-hidden font-mono text-[10px] leading-5 text-violet-600 opacity-70 [mask-image:linear-gradient(to_bottom,black_60%,transparent_100%)]">
              {message.reasoning}
            </div>
          </div>
        ) : isActivelyWaiting ? (
          <div className="flex items-center gap-3 py-2 px-1 text-slate-500">
            <div className="flex space-x-1.5 items-center">
              <span className="w-2.5 h-2.5 bg-indigo-500 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
              <span className="w-2.5 h-2.5 bg-indigo-500 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
              <span className="w-2.5 h-2.5 bg-indigo-500 rounded-full animate-bounce"></span>
            </div>
            <span className="text-xs text-indigo-600 font-medium tracking-wide">
              正在思考并生成回答与富交互组件...
            </span>
          </div>
        ) : (
          <div className="space-y-2">
            {blocks.map((block, i) => (
              <BlockRenderer key={i} block={block} onInteract={onInteract} />
            ))}
            {/* 流式文本打字光标 */}
            {isStreaming && isLast && hasText && (
              <span className="inline-block h-4 w-1.5 translate-y-0.5 bg-indigo-600 animate-pulse ml-0.5" />
            )}

            {/* 当正在执行步骤或等待后续内容时，底部展示动态进度条 */}
            {isStreaming && isLast && (
              <div className="mt-3 flex items-center gap-2.5 rounded-xl bg-slate-50 border border-slate-200/80 px-3.5 py-2.5 text-xs text-slate-600 shadow-2xs">
                {hasRunningTool ? (
                  <>
                    {(() => {
                      const { icon, name } = friendlyLabel(runningToolName);
                      const stepText = runningTool?.result?.startsWith("⚡")
                        ? runningTool.result.replace(/^⚡\s*\[/, "").replace(/\]$/, "")
                        : null;
                      return (
                        <>
                          <span className="text-base animate-spin">{icon}</span>
                          <div className="flex flex-col gap-0.5">
                            <span className="font-medium text-slate-800">正在{name}...</span>
                            {stepText && (
                              <span className="text-[11px] text-indigo-600 font-medium animate-pulse">
                                {stepText}
                              </span>
                            )}
                          </div>
                        </>
                      );
                    })()}
                  </>
                ) : (
                  <>
                    <div className="flex space-x-1 items-center">
                      <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
                      <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
                      <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce"></span>
                    </div>
                    <span className="font-medium text-slate-600">
                      AI 正在生成内容...
                    </span>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
