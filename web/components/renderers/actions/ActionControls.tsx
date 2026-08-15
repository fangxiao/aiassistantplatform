"use client";

import React, { useState } from "react";
import { ContentBlock } from "../../../lib/types";

interface ActionProps {
  block: ContentBlock;
  onInteract?: (action: string, value: any, args?: Record<string, any>) => void;
}

// 1. action.copy
export function ActionCopyRenderer({ block }: ActionProps) {
  const [copied, setCopied] = useState(false);
  const text = String(block.data?.text ?? "");
  const label = String(block.data?.label ?? "复制文本");

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="my-1 inline-flex items-center gap-1.5 rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 transition shadow-xs"
    >
      <span>{copied ? "✓" : "📋"}</span>
      <span>{copied ? "已复制" : label}</span>
    </button>
  );
}

// 2. action.thumbs
export function ActionThumbsRenderer({ block, onInteract }: ActionProps) {
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const action = String(block.data?.action ?? "action.thumbs");

  const handleThumbs = (type: "up" | "down") => {
    setFeedback(type);
    onInteract?.(action, { rating: type === "up" ? 1 : -1 }, block.data?.args);
  };

  return (
    <div className="my-1 inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white p-1 text-xs shadow-xs">
      <button
        type="button"
        onClick={() => handleThumbs("up")}
        className={`rounded px-2 py-0.5 transition ${
          feedback === "up" ? "bg-emerald-100 text-emerald-700 font-bold" : "text-slate-600 hover:bg-slate-100"
        }`}
        title="点赞"
      >
        👍 {feedback === "up" && "已赞"}
      </button>
      <div className="h-3 w-px bg-slate-200" />
      <button
        type="button"
        onClick={() => handleThumbs("down")}
        className={`rounded px-2 py-0.5 transition ${
          feedback === "down" ? "bg-rose-100 text-rose-700 font-bold" : "text-slate-600 hover:bg-slate-100"
        }`}
        title="点踩"
      >
        👎 {feedback === "down" && "已踩"}
      </button>
    </div>
  );
}

// 3. action.regenerate
export function ActionRegenerateRenderer({ block, onInteract }: ActionProps) {
  const action = String(block.data?.action ?? "action.regenerate");
  const label = String(block.data?.label ?? "重新生成回答");

  return (
    <button
      type="button"
      onClick={() => onInteract?.(action, { regenerate: true }, block.data?.args)}
      className="my-1 inline-flex items-center gap-1.5 rounded border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100 transition shadow-xs"
    >
      <span>🔄</span>
      <span>{label}</span>
    </button>
  );
}
