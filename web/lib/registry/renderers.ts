// Renderer Registry(001 §web/lib/registry / 003 v2.0 §3.2)
// type -> 渲染组件;T8.1 MVP 仅 markdown,M7 扩展富交互类型

import type { ComponentType } from "react";
import type { ContentBlock } from "../types";
import MarkdownRenderer from "../../components/renderers/MarkdownRenderer";

export const RENDERERS: Record<string, ComponentType<{ block: ContentBlock }>> = {
  markdown: MarkdownRenderer,
};

export function getRenderer(type: string) {
  return RENDERERS[type] ?? null;
}
