// 消息输入框:Enter 发送,Shift+Enter 换行;防输入法回车冲突;生成中禁用

"use client";

import React, { useState } from "react";
import { uploadImage } from "../../lib/api/chat";

const MAX_IMAGES = 4;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

export default function Composer({
  onSend,
  disabled,
  onStop,
}: {
  onSend: (text: string, images: string[]) => void;
  disabled: boolean;
  onStop?: () => void;
}) {
  const [value, setValue] = useState("");
  // 打磨④:对象存储化——选图即上传,发送用服务端 URL(消息表不再存 dataURL)
  const [images, setImages] = useState<{ preview: string; url: string | null }[]>([]);
  const [isComposing, setIsComposing] = useState(false);
  const fileRef = React.useRef<HTMLInputElement | null>(null);

  const addImages = (files: FileList | File[]) => {
    for (const f of Array.from(files)) {
      if (!f.type.startsWith("image/") || f.size > MAX_IMAGE_BYTES) continue;
      const reader = new FileReader();
      reader.onload = () => {
        const preview = typeof reader.result === "string" ? reader.result : "";
        if (!preview) return;
        setImages((cur) => {
          if (cur.length >= MAX_IMAGES || cur.some((x) => x.preview === preview)) return cur;
          // 上传异步进行:成功用服务端 URL,失败发送时降级 dataURL
          uploadImage(f)
            .then((r) =>
              setImages((cur2) =>
                cur2.map((x) => (x.preview === preview ? { ...x, url: r.url } : x))
              )
            )
            .catch(() => undefined);
          return [...cur, { preview, url: null }];
        });
      };
      reader.readAsDataURL(f);
    }
  };

  const submit = () => {
    const t = value.trim();
    if ((!t && images.length === 0) || disabled) return;
    onSend(t, images.map((x) => x.url ?? x.preview)); // 上传未完成的用 dataURL 兜底
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
                src={img.preview || img.url || ""}
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
        onClick={disabled && onStop ? onStop : submit}
        disabled={disabled && !onStop}
      >
        {disabled && onStop ? "⏹ 停止" : disabled ? "生成中…" : "发送 ↑"}
      </button>
      </div>
    </div>
  );
}
