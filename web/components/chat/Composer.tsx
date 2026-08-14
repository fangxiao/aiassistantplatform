// 消息输入框:Enter 发送,Shift+Enter 换行;生成中禁用

"use client";

import { useState } from "react";

export default function Composer({
  onSend,
  disabled,
}: {
  onSend: (text: string) => void;
  disabled: boolean;
}) {
  const [value, setValue] = useState("");

  const submit = () => {
    const t = value.trim();
    if (!t || disabled) return;
    onSend(t);
    setValue("");
  };

  return (
    <div className="flex gap-2 border-t border-slate-200 bg-white p-3">
      <textarea
        className="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
        rows={2}
        placeholder="输入消息,Enter 发送,Shift+Enter 换行"
        value={value}
        disabled={disabled}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <button
        className="rounded-lg bg-blue-600 px-4 text-sm text-white disabled:opacity-50"
        onClick={submit}
        disabled={disabled || !value.trim()}
      >
        {disabled ? "生成中…" : "发送"}
      </button>
    </div>
  );
}
