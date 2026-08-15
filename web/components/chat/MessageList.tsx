// 消息流列表:自动滚动到底部 + onInteract 转发

"use client";

import React, { useEffect, useRef } from "react";
import type { ChatMessage } from "../../lib/types";
import MessageItem from "./MessageItem";

interface MessageListProps {
  messages: ChatMessage[];
  onInteract?: (action: string, value: any, args?: Record<string, any>) => void;
}

export default function MessageList({ messages, onInteract }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50 p-4">
      {messages.length === 0 && (
        <div className="mt-16 text-center text-slate-400 text-sm">
          <p className="text-2xl mb-2">💬</p>
          <p className="font-medium text-slate-600">开始与助手对话</p>
          <p className="text-xs text-slate-400 mt-1">支持显式调用 skill/tool 与富交互组件渲染</p>
        </div>
      )}
      {messages.map((m) => (
        <MessageItem key={m.id} message={m} onInteract={onInteract} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
