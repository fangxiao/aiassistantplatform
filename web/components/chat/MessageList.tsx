// 消息流列表:自动滚动到底部

"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "../../lib/types";
import MessageItem from "./MessageItem";

export default function MessageList({ messages }: { messages: ChatMessage[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50 p-4">
      {messages.length === 0 && (
        <div className="mt-10 text-center text-slate-400">
          开始对话吧 —— 支持显式调用 skill/tool
        </div>
      )}
      {messages.map((m) => (
        <MessageItem key={m.id} message={m} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
