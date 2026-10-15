// 消息输入框:Enter 发送,Shift+Enter 换行;防输入法回车冲突;生成中禁用

"use client";

import React, { useState } from "react";
import { uploadImage, uploadDoc } from "../../lib/api/chat";

const MAX_IMAGES = 4;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

export default function Composer({
  onSend,
  disabled,
  onStop,
}: {
  onSend: (text: string, images: string[], docs: string[]) => void;
  disabled: boolean;
  onStop?: () => void;
}) {
  const [value, setValue] = useState("");
  // 打磨④:对象存储化——选图即上传,发送用服务端 URL(消息表不再存 dataURL)
  const [images, setImages] = useState<{ preview: string; url: string | null }[]>([]);
  // 打磨⑥:单文档即问(pdf/md/txt/docx/xlsx,不入知识库)
  const [docs, setDocs] = useState<{ name: string; url: string | null }[]>([]);
  const [isComposing, setIsComposing] = useState(false);
  const fileRef = React.useRef<HTMLInputElement | null>(null);
  // 20261015:附件被忽略(超限/类型不符/上传失败)必须可见,不再静默丢弃
  const [notice, setNotice] = useState<string | null>(null);
  const noticeTimer = React.useRef<number | null>(null);
  // 20261015:文档上传真实进度(文件名 → 0-100),大 Excel 不再"没响应"
  const [docProgress, setDocProgress] = useState<Record<string, number>>({});

  const showNotice = (msg: string) => {
    setNotice(msg);
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(null), 6000);
  };

  const addImages = (files: FileList | File[]) => {
    for (const f of Array.from(files)) {
      if (!f.type.startsWith("image/")) {
        showNotice(`「${f.name || "剪贴板内容"}」不是图片,已忽略`);
        continue;
      }
      if (f.size > MAX_IMAGE_BYTES) {
        showNotice(`「${f.name}」超过 5MB 上限,已忽略`);
        continue;
      }
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
            .catch(() => showNotice(`「${f.name}」上传失败,发送时将以内嵌方式携带`));
          return [...cur, { preview, url: null }];
        });
      };
      reader.readAsDataURL(f);
    }
  };

  // 20261015:文档上传在途中禁止发送——docs.url 未就绪会被过滤丢弃,
  // 模型"看不到文件"(竞态事故实测);图片有 dataURL 兜底不受影响
  const hasPendingDoc = Object.keys(docProgress).length > 0;

  const submit = () => {
    const t = value.trim();
    if (hasPendingDoc) {
      showNotice("附件还在上传中,请等进度条完成后再发送");
      return;
    }
    if ((!t && images.length === 0 && docs.length === 0) || disabled) return;
    onSend(
      t,
      images.map((x) => x.url ?? x.preview),
      docs.map((x) => x.url).filter(Boolean) as string[],
    );
    setValue("");
    setImages([]);
    setDocs([]);
  };

  const addDoc = (file: File) => {
    if (docs.length >= 2) return;
    if (file.size > MAX_IMAGE_BYTES) {
      showNotice(`「${file.name}」超过 5MB 上限,已忽略`);
      return;
    }
    setDocProgress((p) => ({ ...p, [file.name]: 0 }));
    uploadDoc(file, (pct) => setDocProgress((prev) => ({ ...prev, [file.name]: pct })))
      .then((r) => {
        setDocProgress(({ [file.name]: _drop, ...rest }) => rest);
        setDocs((cur) => (cur.length >= 2 ? cur : [...cur, { name: file.name, url: r.url }]));
      })
      .catch(() => {
        setDocProgress(({ [file.name]: _drop, ...rest }) => rest);
        showNotice(`「${file.name}」上传失败,请重试`);
      });
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
      {docs.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {docs.map((d, i) => (
            <div key={i} className="relative rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5">
              <span className="text-[11px] text-slate-600">📄 {d.name}</span>
              <button
                type="button"
                onClick={() => setDocs((prev) => prev.filter((_, j) => j !== i))}
                className="ml-2 text-[10px] text-slate-400 hover:text-rose-500"
                title="移除"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      {Object.keys(docProgress).length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {Object.entries(docProgress).map(([name, pct]) => (
            <div key={name} className="rounded-lg border border-indigo-200 bg-indigo-50/50 px-3 py-1.5">
              <span className="text-[11px] text-slate-600">
                📄 {name} <span className="ml-1 font-mono text-[10px] text-indigo-500">{pct}%</span>
              </span>
              <div className="mt-1 h-1 w-28 rounded bg-slate-200">
                <div
                  className="h-1 rounded bg-indigo-500 transition-all duration-150"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
      {notice && (
        <div className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-[11px] text-amber-700">
          ⚠️ {notice}
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
        accept="image/*,.pdf,.md,.markdown,.txt,.docx,.xlsx"
        multiple
        className="hidden"
        onChange={(e) => {
          if (e.target.files) {
            const imgs = Array.from(e.target.files).filter((f) => f.type.startsWith("image/"));
            const files2 = Array.from(e.target.files).filter((f) => !f.type.startsWith("image/"));
            if (imgs.length) addImages(imgs);
            files2.slice(0, 2 - docs.length).forEach(addDoc);
          }
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
        className="self-stretch rounded-xl bg-slate-900 px-5 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40 shadow-xs flex items-center justify-center min-w-[72px]"
        onClick={disabled && onStop ? onStop : submit}
        disabled={disabled && !onStop}
      >
        {disabled && onStop
          ? "⏹ 停止"
          : disabled
            ? "生成中…"
            : hasPendingDoc
              ? "上传中…"
              : "发送 ↑"}
      </button>
      </div>
    </div>
  );
}
