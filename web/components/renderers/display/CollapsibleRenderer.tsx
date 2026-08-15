"use client";

import React, { useState } from "react";
import { ContentBlock } from "../../../lib/types";
import { BlockRenderer } from "../BlockRenderer";

interface CollapsibleProps {
  block: ContentBlock;
  onInteract?: (action: string, value: any, args?: Record<string, any>) => void;
}

export function CollapsibleRenderer({ block, onInteract }: CollapsibleProps) {
  const summary = String(block.data?.summary ?? "点击展开详情");
  const contentBlocks: ContentBlock[] = block.data?.content_blocks ?? [];
  const defaultOpen = Boolean(block.data?.default_open ?? false);
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="my-2 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xs">
      <div
        className="flex cursor-pointer items-center justify-between bg-slate-50/80 px-3.5 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition select-none"
        onClick={() => setOpen(!open)}
      >
        <span>{summary}</span>
        <span className="text-slate-400 transform transition-transform duration-200">
          {open ? "▲" : "▼"}
        </span>
      </div>
      {open && (
        <div className="space-y-2 border-t border-slate-100 p-3.5 bg-white">
          {contentBlocks.map((cb, i) => (
            <BlockRenderer key={i} block={cb} onInteract={onInteract} />
          ))}
        </div>
      )}
    </div>
  );
}
