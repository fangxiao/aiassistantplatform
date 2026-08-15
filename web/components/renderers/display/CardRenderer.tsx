"use client";

import React from "react";
import { ContentBlock } from "../../../lib/types";
import { BlockRenderer } from "../BlockRenderer";

interface CardProps {
  block: ContentBlock;
  onInteract?: (action: string, value: any, args?: Record<string, any>) => void;
}

export function CardRenderer({ block, onInteract }: CardProps) {
  const title = block.data?.title ? String(block.data.title) : null;
  const subtitle = block.data?.subtitle ? String(block.data.subtitle) : null;
  const bodyBlocks: ContentBlock[] = block.data?.body_blocks ?? [];
  const actions: ContentBlock[] = block.data?.actions ?? [];

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition hover:shadow">
      {(title || subtitle) && (
        <div className="border-b border-slate-100 bg-slate-50/60 px-4 py-3">
          {title && <h3 className="text-sm font-bold text-slate-800">{title}</h3>}
          {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
        </div>
      )}

      {bodyBlocks.length > 0 && (
        <div className="space-y-2 p-4">
          {bodyBlocks.map((b, i) => (
            <BlockRenderer key={i} block={b} onInteract={onInteract} />
          ))}
        </div>
      )}

      {actions.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 bg-slate-50/40 px-4 py-2.5">
          {actions.map((act, i) => (
            <BlockRenderer key={i} block={act} onInteract={onInteract} />
          ))}
        </div>
      )}
    </div>
  );
}
