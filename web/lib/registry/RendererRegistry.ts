// 前端 Renderer 注册表(对齐 003 v2.0 §4.1 / ADR 0001)

import React from "react";
import { ContentBlock } from "../types";

// 展示类
import MarkdownRenderer from "../../components/renderers/MarkdownRenderer";
import { CodeRenderer } from "../../components/renderers/display/CodeRenderer";
import { TableRenderer } from "../../components/renderers/display/TableRenderer";
import { CardRenderer } from "../../components/renderers/display/CardRenderer";
import { CollapsibleRenderer } from "../../components/renderers/display/CollapsibleRenderer";
import { ImageRenderer } from "../../components/renderers/display/ImageRenderer";
import { FileRenderer } from "../../components/renderers/display/FileRenderer";
import { MermaidRenderer } from "../../components/renderers/display/MermaidRenderer";

// 交互输入类
import {
  InputTextRenderer,
  InputTextareaRenderer,
  InputNumberRenderer,
  InputSelectRenderer,
  InputRadioRenderer,
  InputCheckboxRenderer,
  InputToggleRenderer,
  InputDateRenderer,
  InputFileRenderer,
  InputConfirmRenderer,
  InputFormRenderer,
} from "../../components/renderers/interactive/InputControls";

// 动作反馈类
import {
  ActionCopyRenderer,
  ActionThumbsRenderer,
  ActionRegenerateRenderer,
} from "../../components/renderers/actions/ActionControls";

import { FallbackRenderer } from "../../components/renderers/FallbackRenderer";

export type RendererComponent = React.ComponentType<{
  block: ContentBlock;
  onInteract?: (action: string, value: any, args?: Record<string, any>) => void;
}>;

class RendererRegistry {
  private map = new Map<string, RendererComponent>();

  constructor() {
    this.registerDefaults();
  }

  private registerDefaults(): void {
    // 降级兜底
    this.map.set("__fallback__", FallbackRenderer);

    // 8 种展示类
    this.map.set("markdown", MarkdownRenderer);
    this.map.set("code", CodeRenderer);
    this.map.set("table", TableRenderer);
    this.map.set("card", CardRenderer);
    this.map.set("collapsible", CollapsibleRenderer);
    this.map.set("image", ImageRenderer);
    this.map.set("file", FileRenderer);
    this.map.set("mermaid", MermaidRenderer);

    // 11 种交互输入类
    this.map.set("input.text", InputTextRenderer);
    this.map.set("input.textarea", InputTextareaRenderer);
    this.map.set("input.number", InputNumberRenderer);
    this.map.set("input.select", InputSelectRenderer);
    this.map.set("input.radio", InputRadioRenderer);
    this.map.set("input.checkbox", InputCheckboxRenderer);
    this.map.set("input.toggle", InputToggleRenderer);
    this.map.set("input.date", InputDateRenderer);
    this.map.set("input.file", InputFileRenderer);
    this.map.set("input.confirm", InputConfirmRenderer);
    this.map.set("input.form", InputFormRenderer);

    // 3 种动作反馈类
    this.map.set("action.copy", ActionCopyRenderer);
    this.map.set("action.thumbs", ActionThumbsRenderer);
    this.map.set("action.regenerate", ActionRegenerateRenderer);
  }

  register(name: string, component: RendererComponent): void {
    if (this.map.has(name) && !name.startsWith("plugin.")) {
      // 平台内置名保护,不可被覆盖
      return;
    }
    this.map.set(name, component);
  }

  resolve(name: string): RendererComponent | undefined {
    return this.map.get(name) ?? this.map.get("__fallback__");
  }

  list(): string[] {
    return Array.from(this.map.keys());
  }
}

export const registry = new RendererRegistry();
