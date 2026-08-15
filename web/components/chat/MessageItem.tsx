// 单条消息:用户气泡 / 助手 ContentBlock 列表 + 工具调用徽标

"use client";

import React from "react";
import type { ChatMessage, ContentBlock } from "../../lib/types";
import { BlockRenderer } from "../renderers/BlockRenderer";

interface MessageItemProps {
  message: ChatMessage;
  onInteract?: (action: string, value: any, args?: Record<string, any>) => void;
}

export default function MessageItem({ message, onInteract }: MessageItemProps) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-slate-900 px-4 py-2.5 text-sm text-white shadow-xs">
          {message.text}
        </div>
      </div>
    );
  }

  const blocks: ContentBlock[] =
    message.blocks && message.blocks.length > 0
      ? message.blocks
      : [{ type: "markdown", data: { text: message.text } }];

  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-1.5 border-b border-slate-100 pb-2">
            {message.toolCalls.map((tc, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 rounded bg-amber-50 px-2 py-0.5 text-xs font-mono text-amber-800 border border-amber-200"
                title={`${tc.name}(${JSON.stringify(tc.args)}) -> ${tc.result}`}
              >
                <span>⚙</span>
                <span>{tc.name}</span>
              </span>
            ))}
          </div>
        )}

        <div className="space-y-2">
          {blocks.map((block, i) => (
            <BlockRenderer key={i} block={block} onInteract={onInteract} />
          ))}
        </div>
      </div>
    </div>
  );
}
