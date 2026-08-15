"use client";

import React, { useState } from "react";
import { ContentBlock } from "../../../lib/types";

export function ImageRenderer({ block }: { block: ContentBlock }) {
  const url = String(block.data?.url ?? "");
  const alt = String(block.data?.alt ?? "图片");
  const caption = block.data?.caption ? String(block.data.caption) : null;
  const [zoomed, setZoomed] = useState(false);

  if (!url.startsWith("http://") && !url.startsWith("https://") && !url.startsWith("/")) {
    return (
      <div className="my-2 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-600">
        ⚠️ 图片 URL 格式不安全: {url}
      </div>
    );
  }

  return (
    <div className="my-3 max-w-lg">
      <div
        className="cursor-zoom-in overflow-hidden rounded-lg border border-slate-200 bg-slate-100 shadow-sm"
        onClick={() => setZoomed(true)}
      >
        <img
          src={url}
          alt={alt}
          loading="lazy"
          className="max-h-80 w-full object-contain"
        />
      </div>
      {caption && (
        <p className="mt-1 text-center text-xs text-slate-500">{caption}</p>
      )}

      {zoomed && (
        <div
          className="fixed inset-0 z-50 flex cursor-zoom-out items-center justify-center bg-black/80 p-4"
          onClick={() => setZoomed(false)}
        >
          <img
            src={url}
            alt={alt}
            className="max-h-[90vh] max-w-[90vw] rounded object-contain shadow-2xl"
          />
        </div>
      )}
    </div>
  );
}
