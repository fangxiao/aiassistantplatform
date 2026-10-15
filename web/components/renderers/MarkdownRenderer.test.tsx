/**
 * MarkdownRenderer 数学公式渲染回归(20261014 错题场景:LaTeX 原样展示源码):
 * - $$...$$ 块级(跨行/同行闭合)→ KaTeX display 节点
 * - $...$ 与 \(...\) 行内 → KaTeX inline 节点
 * - 代码围栏内的 $ 不渲染(避免误伤示例代码)
 * - 未闭合 $$ 不吞内容(原样展示)
 */
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import MarkdownRenderer from "./MarkdownRenderer";

const block = (text: string) =>
  ({ type: "markdown", data: { text } }) as any;

const katexNodes = (container: HTMLElement) =>
  container.querySelectorAll(".katex");

describe("MarkdownRenderer 数学公式", () => {
  it("块级 $$ 跨行公式渲染为 KaTeX display", () => {
    const { container } = render(
      <MarkdownRenderer block={block("面积:\n$$\nS = \\frac{1}{2}ab\\sin C\n$$\n完")} />,
    );
    expect(katexNodes(container).length).toBeGreaterThan(0);
    expect(container.textContent).toContain("面积:");
    expect(container.textContent).not.toContain("$$");
  });

  it("块级 $$ 同行闭合渲染", () => {
    const { container } = render(
      <MarkdownRenderer block={block("$$BC^2 - 5\\sqrt{3}BC + 16 = 0$$")} />,
    );
    expect(katexNodes(container).length).toBeGreaterThan(0);
    expect(container.textContent).not.toContain("$$");
  });

  it("行内 $ 与 \\( \\) 公式渲染", () => {
    const { container } = render(
      <MarkdownRenderer block={block("由 $AC^2 = 9$ 且 \\(AB = 5\\) 得结论")} />,
    );
    expect(katexNodes(container).length).toBe(2);
  });

  it("代码围栏内的 $ 不被渲染(误伤回归)", () => {
    const { container } = render(
      <MarkdownRenderer block={block("```\nprice = a + $b$\n```")} />,
    );
    expect(katexNodes(container).length).toBe(0);
    expect(container.textContent).toContain("$b$");
  });

  it("未闭合 $$ 原样输出不吞内容", () => {
    const { container } = render(
      <MarkdownRenderer block={block("开头 $$abc 后面没有闭合")} />,
    );
    expect(container.textContent).toContain("$$abc 后面没有闭合");
  });
});
