// 单条消息:用户气泡 / 助手 ContentBlock 列表 + 工具调用徽标 + 内联流式等待状态

"use client";

import React, { useState } from "react";
import type { ChatMessage, ContentBlock, ToolCallInfo } from "../../lib/types";
import { BlockRenderer } from "../renderers/BlockRenderer";

/** 将技术名称映射为对用户友好的中文描述。
 *  20261015 工单 20261015-0956-0059e1:output_block 此前一律显示"给出了填写表单",
 *  表格/卡片被误标为表单致用户困惑——按 args.type 细化语义化标签。 */
function friendlyLabel(rawName: string, args?: unknown): { icon: string; name: string } {
  const n = (rawName || "").toLowerCase();
  if (n.includes("output_block")) {
    let blockType = "";
    if (typeof args === "string") {
      try {
        blockType = String((JSON.parse(args) as Record<string, unknown>)?.type ?? "");
      } catch {
        /* 非 JSON,保持空走缺省 */
      }
    } else if (args && typeof args === "object") {
      blockType = String((args as Record<string, unknown>).type ?? "");
    }
    const t = blockType.toLowerCase();
    if (t.startsWith("input.")) return { icon: "📝", name: "输入表单" };
    if (t === "table") return { icon: "📊", name: "数据表格" };
    if (t === "card") return { icon: "📋", name: "方案卡片" };
    if (t === "metric_stat") return { icon: "📈", name: "指标看板" };
    if (t === "waterfall") return { icon: "⏱️", name: "时序流" };
    return { icon: "🧩", name: "组件渲染" };
  }
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

/**
 * 拆分模型误写进正文的中英文决策思考前导(如 "The user wants... I should call..." 或 "用户选择了... 让我先调用..."):
 * 启发式——开头连续思考句子段(且后文存在标题/结构化内容)视为思考前导,
 * 返回 [preamble, body]。无匹配返回 ["", text]。
 */
function splitEnglishPreamble(text: string): [string, string] {
  if (!text) return ["", ""];
  // <think> 标签块(部分网关模型把推理内联在 content 里)→ 整体归入思考
  const thinkTag = /<think>([\s\S]*?)<\/think>\s*/i.exec(text);
  if (thinkTag) return [thinkTag[1].trim(), text.slice(thinkTag[0].length).trimStart()];
  // 锚点:首个内容结构(标题/表格/代码块/【/加粗/控件伪调用),而非首个中文字符——
  // 混排 meta 推理(如 "audience: 技术小白… let's call the tool.")含中文字段值,
  // 以中文字符锚点会过早截断导致漏判(2026-09-26 泄露事故)
  const m = text.search(/\n#{1,3} |\n\||```|【|\*\*|input\.form/);
  if (m <= 0) return ["", text];
  const head = text.slice(0, m).trim();
  if (!head) return ["", text];
  // 前导需"足够像思考":含决策动词/元规划特征(字段枚举、调用意图)
  const thinky =
    /(should|let me|i'll|i will|let's|need to|the user|my role|first|alternatively|given that|call the tool|the form|collect\b|audience\s*:|length\s*:|tone\s*:|topic\s*:)/i.test(head);
  const chineseThinky =
    /(用户选择了|想要了解|作为.*专家|我应该|让我先|确保回答|检索一下|分析一下|调用.*技能|根据.*定位|根据我的角色)/.test(head);
  const ascii = (head.match(/[\x00-\x7f]/g) || []).length / head.length;
  const fieldEnum = /^[a-z_]+\s*:/im.test(head);
  if (chineseThinky || (head.length > 40 && thinky && (ascii > 0.6 || fieldEnum))) {
    return [head, text.slice(m).replace(/^\s+/, "")];
  }
  return ["", text];
}

interface MessageItemProps {
  message: ChatMessage;
  isStreaming?: boolean;
  isLast?: boolean;
  onRegenerate?: () => void;
  onResume?: () => void;
  onInteract?: (action: string, value: any, args?: Record<string, any>) => void;
  onSaveToKb?: (content: string) => void;
}

export default function MessageItem({
  message,
  isStreaming = false,
  isLast = false,
  onRegenerate,
  onResume,
  onInteract,
  onSaveToKb,
}: MessageItemProps) {
  if (message.role === "user") {
    // 20261015:用户消息回显附件(图缩略图/文档芯片)——此前只渲染文本,
    // 用户发了附件却"看不到消息带着文件",历史回看同样缺失
    const userBlocks = (message.blocks ?? []) as ContentBlock[];
    const userImages = userBlocks.filter((b) => b.type === "image");
    const userFiles = userBlocks.filter((b) => b.type === "file");
    return (
      <div className="flex flex-col items-end gap-1.5">
        {userImages.length > 0 && (
          <div className="flex max-w-[80%] flex-wrap justify-end gap-1.5">
            {userImages.map((b, i) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={i}
                src={String(b.data?.url ?? "")}
                alt={`附件图片${i + 1}`}
                className="max-h-48 rounded-xl border border-slate-200 object-cover shadow-xs"
              />
            ))}
          </div>
        )}
        {userFiles.length > 0 && (
          <div className="flex max-w-[80%] flex-wrap justify-end gap-1.5">
            {userFiles.map((b, i) => (
              <span
                key={i}
                className="inline-flex max-w-[280px] items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[11px] text-slate-600 shadow-xs"
                title={String(b.data?.url ?? "")}
              >
                📄 <span className="truncate">{String(b.data?.name ?? "文档")}</span>
              </span>
            ))}
          </div>
        )}
        {message.text && (
          <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-slate-900 px-4 py-2.5 text-sm text-white shadow-xs">
            {message.text}
          </div>
        )}
      </div>
    );
  }

  const hasBlocks = message.blocks && message.blocks.length > 0;
  const [engPreamble, cleanText] = splitEnglishPreamble(message.text || "");
  const effectiveReasoning = [message.reasoning, engPreamble].filter(Boolean).join("\n\n");
  const hasText = Boolean(cleanText && cleanText.trim().length > 0);
  const hasToolCalls = Boolean(message.toolCalls && message.toolCalls.length > 0);
  const isThinking = isStreaming && isLast && Boolean(effectiveReasoning) && !hasText && !hasBlocks;
  const isActivelyWaiting = isStreaming && isLast && !hasText && !hasBlocks && !effectiveReasoning;
  // M34:工具轮过渡语("我来调用X精讲…")淡色呈现——它是过程说明,不是回答正文
  const hasTransition = Boolean(message.transition && message.transition.trim());

  const blocks: ContentBlock[] = hasBlocks
    ? (message.blocks as ContentBlock[])
    : [{ type: "markdown", data: { text: cleanText || "" } }];

  const runningTool = message.toolCalls?.find((tc) => !tc.result);
  const hasRunningTool = Boolean(runningTool);
  const runningToolName = runningTool?.name || runningTool?.id || "公共技能";
  // 收藏到知识库入口(设计 008 §11.4):有正文且非流式中
  const canSaveToKb = Boolean(onSaveToKb && message.text && message.text.trim() && !(isStreaming && isLast));


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
        {/* 工具执行进度条（用户友好视图，隐藏技术实现细节）。
            20261015 工单 20261015-1538-1e28fe:连续同类工具(>2 次)折叠聚合,
            消除"12 行信息搜索完成"式刷屏;点击展开明细 */}
        {hasToolCalls && (
          <div className="mb-3 flex flex-col gap-1.5 border-b border-slate-100 pb-3">
            {groupConsecutiveTools(message.toolCalls ?? []).map((group, gi) =>
              group.items.length > 2 ? (
                <ToolGroupRow
                  key={`g${gi}`}
                  label={group.label}
                  items={group.items}
                  isStreaming={isStreaming}
                  isLast={isLast}
                  totalLen={message.toolCalls?.length ?? 0}
                />
              ) : (
                group.items.map(([tc, i]) => (
                  <ToolRow key={i} tc={tc} index={i} isStreaming={isStreaming} isLast={isLast} totalLen={message.toolCalls?.length ?? 0} />
                ))
              ),
            )}
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
            {/* 思考过程(完成后折叠,可展开;打磨:区分思考与回答) */}
            {!isStreaming && effectiveReasoning && hasText && (
              <details className="mb-2 rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-1.5">
                <summary className="cursor-pointer select-none text-[11px] font-medium text-slate-400">
                  🧠 思考过程(模型内部推理,点击展开)
                </summary>
                <div className="mt-1.5 max-h-48 overflow-y-auto whitespace-pre-wrap font-mono text-[10px] leading-5 text-violet-500/80">
                  {effectiveReasoning}
                </div>
              </details>
            )}
            {/* M34:工具轮过渡语淡色呈现(过程说明,非回答正文) */}
            {hasTransition && (
              <div className="whitespace-pre-wrap text-[11px] leading-5 text-slate-400">
                {message.transition}
              </div>
            )}
            {blocks.map((block, i) => (
              <BlockRenderer key={i} block={block} onInteract={onInteract} />
            ))}
            {/* 断点续跑(ADR 0009):中断草稿可从断点继续 */}
            {!isStreaming && message.role === "assistant" && message.resumable && onResume && (
              <button
                type="button"
                onClick={onResume}
                className="mt-2 inline-flex items-center gap-1 rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] text-amber-700 transition hover:border-amber-400 hover:text-amber-800"
                title="该回复因连接中断未完成,点击从断点继续(已完成内容不重复生成)"
              >
                ⚡ 从断点续跑
              </button>
            )}
            {/* 打磨②:最后一条助手回复可重新生成 */}
            {!isStreaming && isLast && message.role === "assistant" && hasText && onRegenerate && (
              <button
                type="button"
                onClick={onRegenerate}
                className="mt-2 inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[10px] text-slate-500 transition hover:border-indigo-300 hover:text-indigo-600"
                title="按最后一条消息重新生成"
              >
                ↻ 重新生成
              </button>
            )}
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
                      const { icon, name } = friendlyLabel(runningToolName, runningTool?.args);
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

// ---- 工具徽标:连续同类折叠聚合(20261015 工单 20261015-1538-1e28fe) ----

function isRowDone(tc: ToolCallInfo, index: number, isStreaming: boolean, isLast: boolean, totalLen: number): boolean {
  // 非流式状态(就绪态)或已有明确结果时,均视为执行完毕;流式末位且无结果的保持 pending
  return !isStreaming || (Boolean(tc.result) && !(isLast && index === totalLen - 1 && !tc.result));
}

function rowFailed(tc: ToolCallInfo, isDone: boolean): boolean {
  // 执行状态真实显示:失败结果不渲染成"✅完成"(2026-09-26 编造成功教训)
  if (!isDone || !tc.result) return false;
  try {
    const d = JSON.parse(tc.result);
    return d?.ok === false || d?.status === "error" || d?.status === "failed";
  } catch {
    return false; // 非 JSON 结果(纯文本/HTML)按成功显示
  }
}

/** 连续同类工具归组(按语义化标签;非连续同类不合并,保持时序真实) */
function groupConsecutiveTools(
  toolCalls: ToolCallInfo[],
): { label: { icon: string; name: string }; items: [ToolCallInfo, number][] }[] {
  const groups: { label: { icon: string; name: string }; items: [ToolCallInfo, number][] }[] = [];
  for (let i = 0; i < toolCalls.length; i++) {
    const tc = toolCalls[i];
    const label = friendlyLabel(tc.name || tc.id || "", tc.args);
    const last = groups[groups.length - 1];
    if (last && last.label.icon === label.icon && last.label.name === label.name) {
      last.items.push([tc, i]);
    } else {
      groups.push({ label, items: [[tc, i]] });
    }
  }
  return groups;
}

function toolArgsSummary(tc: ToolCallInfo): string {
  // 20261015 工单 1706-27e1c1:展开态展示入参摘要——检索类显示关键词,
  // 其余截取 JSON 前 80 字,便于判断是否在盲目重复调用
  const args = tc.args;
  if (!args || typeof args !== "object") return "";
  const a = args as Record<string, unknown>;
  if (typeof a.query === "string" && a.query.trim()) return `关键词: ${a.query}`;
  if (typeof a.question === "string" && a.question.trim()) return `问题: ${a.question}`;
  if (typeof a.text === "string" && a.text.trim()) return `输入: ${a.text}`;
  const json = JSON.stringify(args);
  return json === "{}" ? "" : json.slice(0, 80);
}

function ToolRow({
  tc,
  index,
  isStreaming,
  isLast,
  totalLen,
  showArgs = false,
}: {
  tc: ToolCallInfo;
  index: number;
  isStreaming: boolean;
  isLast: boolean;
  totalLen: number;
  showArgs?: boolean; // 折叠组展开态传入:展示入参摘要
}) {
  const isDone = isRowDone(tc, index, isStreaming, isLast, totalLen);
  const hasFailed = rowFailed(tc, isDone);
  const { icon, name } = friendlyLabel(tc.name || tc.id || "", tc.args);
  const stepResult = tc.result?.startsWith("⚡")
    ? tc.result.replace(/^⚡\s*\[/, "").replace(/\]$/, "")
    : null;
  return (
    <div
      className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-all ${
        !isDone
          ? "bg-amber-50 text-amber-900 animate-pulse"
          : hasFailed
            ? "bg-rose-50 text-rose-800"
            : "bg-emerald-50 text-emerald-800"
      }`}
      title={`[开发者信息] ${tc.name ?? tc.id}`}
    >
      <span className={`text-base ${isDone ? "" : "animate-spin"}`}>
        {isDone ? (hasFailed ? "❌" : "✅") : icon}
      </span>
      <div className="flex min-w-0 flex-col">
        <span className="font-medium">{!isDone ? `正在${name}...` : hasFailed ? `${name}失败` : `${name}完成`}</span>
        {stepResult && <span className="mt-0.5 text-[11px] opacity-75">{stepResult}</span>}
        {showArgs && (() => {
          const summary = toolArgsSummary(tc);
          return summary ? (
            <span className="mt-0.5 truncate font-mono text-[10px] text-slate-500" title={summary}>
              ⌗ {summary}
            </span>
          ) : null;
        })()}
      </div>
    </div>
  );
}

function ToolGroupRow({
  label,
  items,
  isStreaming,
  isLast,
  totalLen,
}: {
  label: { icon: string; name: string };
  items: [ToolCallInfo, number][];
  isStreaming: boolean;
  isLast: boolean;
  totalLen: number;
}) {
  const [open, setOpen] = useState(false);
  const n = items.length;
  const dones = items.map(([tc, i]) => isRowDone(tc, i, isStreaming, isLast, totalLen));
  const failedCount = items.filter(([tc], k) => rowFailed(tc, dones[k])).length;
  const pendingIdx = dones.findIndex((d) => !d);
  const state = pendingIdx >= 0 ? "pending" : failedCount > 0 ? "failed" : "done";
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-all ${
          state === "pending"
            ? "bg-amber-50 text-amber-900"
            : state === "failed"
              ? "bg-rose-50 text-rose-800"
              : "bg-emerald-50 text-emerald-800"
        }`}
        title="点击展开/收起每次调用的明细"
      >
        <span className={`text-base ${state === "pending" ? "animate-spin" : ""}`}>
          {state === "pending" ? label.icon : state === "failed" ? "❌" : "✅"}
        </span>
        <span className="font-medium">
          {state === "pending"
            ? `正在${label.name}... 第 ${pendingIdx + 1}/${n} 次处理中`
            : state === "failed"
              ? `${label.name}(${n} 次,${failedCount} 次失败)`
              : `${label.name}(${n} 次已完成)`}
        </span>
        <span className="ml-auto text-[10px] opacity-60">{open ? "▴ 收起" : "▾ 展开"}</span>
      </button>
      {open && (
        <div className="mt-1.5 flex flex-col gap-1.5">
          {items.map(([tc, i]) => (
            <ToolRow key={i} tc={tc} index={i} isStreaming={isStreaming} isLast={isLast} totalLen={totalLen} showArgs />
          ))}
        </div>
      )}
    </div>
  );
}
