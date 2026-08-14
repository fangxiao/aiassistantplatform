// 单条消息:用户气泡 / 助手 markdown + 工具调用徽标

"use client";

import type { ChatMessage } from "../../lib/types";
import Renderer from "../renderers/Renderer";

export default function MessageItem({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-blue-600 px-4 py-2 text-white">
          {message.text}
        </div>
      </div>
    );
  }

  const block = { type: "markdown", data: { text: message.text } };
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl border border-slate-200 bg-white px-4 py-2">
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {message.toolCalls.map((tc, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-700"
                title={`${tc.name}(${JSON.stringify(tc.args)}) -> ${tc.result}`}
              >
                ⚙ {tc.name}
              </span>
            ))}
          </div>
        )}
        <Renderer block={block} />
      </div>
    </div>
  );
}
