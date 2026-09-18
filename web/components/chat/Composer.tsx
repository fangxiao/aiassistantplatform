// 消息输入框:Enter 发送,Shift+Enter 换行;防输入法回车冲突;生成中禁用

"use client";

import React, { useState } from "react";

const MAX_IMAGES = 4;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

export default function Composer({
  onSend,
  disabled,
}: {
  onSend: (text: string, images: string[]) => void;
  disabled: boolean;
}) {
  const [value, setValue] = useState("");
  const [images, setImages] = useState<string[]>([]);
  const [isComposing, setIsComposing] = useState(false);
  const fileRef = React.useRef<HTMLInputElement | null>(null);

  const addImages = (files: FileList | File[]) => {
    setImages((prev) => {
      const next = [...prev];
      for (const f of Array.from(files)) {
        if (next.length >= MAX_IMAGES) break;
        if (!f.type.startsWith("image/")) continue;
        if (f.size > MAX_IMAGE_BYTES) continue;
        const reader = new FileReader();
        reader.onload = () => {
          if (typeof reader.result === "string") {
            setImages((cur) => (cur.length >= MAX_IMAGES ? cur : [...cur, reader.result as string]));
          }
        };
        reader.readAsDataURL(f);
      }
      return next;
    });
  };

  const submit = () => {
    const t = value.trim();
    if ((!t && images.length === 0) || disabled) return;
    onSend(t, images);
    setValue("");
    setImages([]);
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
    <div className="border-t border-slate-200 bg-white p-3 shadow-xs">
      {images.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {images.map((img, i) => (
            <div key={i} className="relative">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={img}
                alt={`附件${i + 1}`}
                className="h-16 w-16 rounded-lg border border-slate-200 object-cover"
              />
              <button
                type="button"
                onClick={() => setImages((prev) => prev.filter((_, j) => j !== i))}
                className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-slate-900 text-[10px] text-white"
                title="移除"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-2 items-end">
      <button
        type="button"
        disabled={disabled || images.length >= MAX_IMAGES}
        onClick={() => fileRef.current?.click()}
        className="shrink-0 rounded-xl border border-slate-300 px-3 py-2.5 text-base text-slate-500 transition hover:border-indigo-400 hover:text-indigo-600 disabled:opacity-40"
        title="添加图片(最多 4 张,可粘贴)"
      >
        📎
      </button>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={(e) => {
          if (e.target.files) addImages(e.target.files);
          e.target.value = "";
        }}
      />
      <textarea
        className="flex-1 resize-none rounded-xl border border-slate-300 px-3.5 py-2.5 text-xs text-slate-800 outline-none transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 placeholder-slate-400"
        rows={2}
        placeholder="输入消息，Enter 发送；可粘贴或点击 📎 附带图片..."
        value={value}
        disabled={disabled}
        onChange={(e) => setValue(e.target.value)}
        onPaste={(e) => {
          const files = Array.from(e.clipboardData.files || []);
          if (files.some((f) => f.type.startsWith("image/"))) {
            e.preventDefault();
            addImages(files);
          }
        }}
        onCompositionStart={() => setIsComposing(true)}
        onCompositionEnd={() => setIsComposing(false)}
        onKeyDown={handleKeyDown}
      />
      <button
        type="button"
        className="rounded-xl bg-slate-900 px-5 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40 shadow-xs flex items-center justify-center min-w-[72px]"
        onClick={submit}
        disabled={disabled || (!value.trim() && images.length === 0)}
      >
        {disabled ? "生成中…" : "发送 ↑"}
      </button>
      </div>
    </div>
  );
}
