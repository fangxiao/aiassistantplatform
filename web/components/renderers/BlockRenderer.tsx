"use client";

import React, { createContext, useContext } from "react";
import { ContentBlock } from "../../lib/types";
import { registry } from "../../lib/registry/RendererRegistry";
import { FallbackRenderer } from "./FallbackRenderer";

// 深度上下文 (003 v2.0 §7.2 最大嵌套深度 = 3)
export const NestingContext = createContext<number>(0);

interface BlockRendererProps {
  block: ContentBlock;
  onInteract?: (action: string, value: any, args?: Record<string, any>) => void;
}

const CONTAINER_TYPES = new Set(["card", "collapsible", "input.form"]);

export function BlockRenderer({ block, onInteract }: BlockRendererProps) {
  const depth = useContext(NestingContext);

  if (depth > 3) {
    return <FallbackRenderer block={block} reason="嵌套层级超过上限(>3)" />;
  }

  const Component = registry.resolve(block.type);
  if (!Component) {
    return <FallbackRenderer block={block} reason="未知组件类型" />;
  }

  const childDepth = CONTAINER_TYPES.has(block.type) ? depth + 1 : depth;

  try {
    return (
      <NestingContext.Provider value={childDepth}>
        <Component block={block} onInteract={onInteract} />
      </NestingContext.Provider>
    );
  } catch (err) {
    return <FallbackRenderer block={block} reason={`渲染异常: ${err}`} />;
  }
}
