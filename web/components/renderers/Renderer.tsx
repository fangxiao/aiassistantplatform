// 块渲染分发器(003 v2.0 §3):按 type 选择渲染器,未知类型给降级占位

"use client";

import type { ContentBlock } from "../../lib/types";
import { getRenderer } from "../../lib/registry/renderers";

export default function Renderer({ block }: { block: ContentBlock }) {
  const Component = getRenderer(block.type);
  if (!Component) {
    return (
      <div className="rounded border border-dashed border-slate-300 p-2 text-xs text-slate-400">
        暂不支持的内容块: {block.type}(M7 富交互组件支持)
      </div>
    );
  }
  return <Component block={block} />;
}
