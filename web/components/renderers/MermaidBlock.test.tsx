/**
 * MermaidBlock 渲染回归(20261015 工单 1539-e50fd0):
 * - ```mermaid 块渲染为 SVG(mermaid 模块 mock)
 * - 渲染失败降级为源码 + 异常提示
 * - 非 mermaid 代码块不受影响
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import MarkdownRenderer from "./MarkdownRenderer";

const block = (text: string) => ({ type: "markdown", data: { text } }) as any;

const mermaidSource = "sequenceDiagram\n  A->>B: 你好";

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn().mockResolvedValue({ svg: "<svg>时序图</svg>" }),
  },
}));

describe("MarkdownRenderer mermaid", () => {
  it("mermaid 块渲染为 SVG,不再显示死文本", async () => {
    const { container } = render(
      <MarkdownRenderer block={block("```mermaid\n" + mermaidSource + "\n```")} />,
    );
    await waitFor(() => expect(container.querySelector("svg")).toBeTruthy());
    expect(container.textContent).not.toContain("sequenceDiagram");
  });

  it("渲染失败降级为源码 + 异常提示", async () => {
    const mermaid = (await import("mermaid")).default;
    vi.mocked(mermaid.render).mockRejectedValueOnce(new Error("parse error"));
    const { container } = render(
      <MarkdownRenderer block={block("```mermaid\n" + mermaidSource + "\n```")} />,
    );
    await waitFor(() => expect(screen.getByText(/图表渲染异常/)).toBeTruthy());
    expect(container.textContent).toContain("sequenceDiagram");
  });

  it("非 mermaid 代码块仍按 <pre> 渲染", () => {
    const { container } = render(
      <MarkdownRenderer block={block("```python\nprint(1)\n```")} />,
    );
    expect(container.querySelector("pre")).toBeTruthy();
    expect(container.querySelector("svg")).toBeNull();
  });
});
