// 消息输入框:Enter 发送,Shift+Enter 换行;防输入法回车冲突;生成中禁用

"use client";

import React, { useState } from "react";

export default function Composer({
  onSend,
  disabled,
}: {
  onSend: (text: string) => void;
  disabled: boolean;
}) {
  const [value, setValue] = useState("");
  const [isComposing, setIsComposing] = useState(false);

  const submit = () => {
    const t = value.trim();
    if (!t || disabled) return;
    onSend(t);
    setValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // 处理输入法合成状态（中文拼音输入按回车时不触发提交）
    if (e.key === "Enter" && !e.shiftKey) {
      if (isComposing || e.nativeEvent.isComposing) {
        return;
      }
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex gap-2 border-t border-slate-200 bg-white p-3 shadow-xs">
      <textarea
        className="flex-1 resize-none rounded-xl border border-slate-300 px-3.5 py-2.5 text-xs text-slate-800 outline-none transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 placeholder-slate-400"
        rows={2}
        placeholder="输入消息，Enter 发送，Shift + Enter 换行..."
        value={value}
        disabled={disabled}
        onChange={(e) => setValue(e.target.value)}
        onCompositionStart={() => setIsComposing(true)}
        onCompositionEnd={() => setIsComposing(false)}
        onKeyDown={handleKeyDown}
      />
      <button
        type="button"
        className="rounded-xl bg-slate-900 px-5 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40 shadow-xs flex items-center justify-center min-w-[72px]"
        onClick={submit}
        disabled={disabled || !value.trim()}
      >
        {disabled ? "生成中…" : "发送 ↑"}
      </button>
    </div>
  );
}
