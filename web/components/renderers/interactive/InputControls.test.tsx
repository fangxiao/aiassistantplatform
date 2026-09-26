/**
 * InputFormRenderer 金样本回归(2026-09-26 表单三连崩教训):
 * - 模型真实 output_block 输出的字段形状(name/type/options 字符串数组)
 * - select 下拉必须有选项(字符串 options 曾渲染成 undefined → 空下拉)
 * - 嵌套字段不得自带提交按钮(此前每字段一个"提交")
 * - 容器提交组装 {fields:[{id,label,value}]}(此前总提交收到 {})
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { InputFormRenderer } from "./InputControls";
import { parsePseudoForm } from "../MarkdownRenderer";

// 与 input.form 同款字段形状(取自 2026-09-26 生产会话真实输出)
const REAL_FORM_BLOCK = {
  type: "input.form",
  data: {
    title: "文章写作需求",
    fields: [
      { name: "topic", type: "input.textarea", label: "文章主题 *", required: true, placeholder: "如:中秋" },
      { name: "tone", type: "input.select", label: "语气风格", options: ["专业", "轻松", "幽默"], required: false },
      { name: "length", type: "input.number", label: "目标字数", required: false },
    ],
    submit_label: "🚀 开始撰写",
  },
} as any;

describe("InputFormRenderer", () => {
  it("select 字段把字符串 options 渲染成可见选项(空下拉回归)", () => {
    render(<InputFormRenderer block={REAL_FORM_BLOCK} onInteract={vi.fn()} />);
    fireEvent.click(screen.getAllByText(/语气风格|目标字数/)[0] ?? screen.getAllByRole("combobox")[0]);
    const combo = screen.getAllByRole("combobox")[0];
    fireEvent.change(combo, { target: { value: "" } });
    const options = screen.getAllByRole("option").map((o) => o.textContent);
    for (const v of ["专业", "轻松", "幽默"]) expect(options).toContain(v);
  });

  it("只有一个提交按钮(每字段自带按钮的回归)", () => {
    render(<InputFormRenderer block={REAL_FORM_BLOCK} onInteract={vi.fn()} />);
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByText("🚀 开始撰写")).toBeTruthy();
  });

  it("填写后提交,组装结构化 fields 并回调", () => {
    const onInteract = vi.fn();
    render(<InputFormRenderer block={REAL_FORM_BLOCK} onInteract={onInteract} />);
    fireEvent.change(screen.getByLabelText("文章主题 *"), { target: { value: "中秋" } });
    fireEvent.click(screen.getByText("🚀 开始撰写"));
    expect(onInteract).toHaveBeenCalledTimes(1);
    const [, value] = onInteract.mock.calls[0];
    expect(value.fields).toEqual([
      { id: "topic", label: "文章主题 *", value: "中秋" },
      { id: "tone", label: "语气风格", value: "" },
      { id: "length", label: "目标字数", value: "" },
    ]);
  });
});

describe("parsePseudoForm(伪调用确定性兜底)", () => {
  it("解析模型裸写的 input.form 伪调用(2026-09-26 用户实录)", () => {
    const src = 'input.form({\n  "主题": input.text(),\n  "受众": input.text(),\n  "字数": input.number()\n})';
    const block = parsePseudoForm(src)!;
    expect(block).not.toBeNull();
    expect(block.data.fields.map((f: any) => f.label)).toEqual(["主题", "受众", "字数"]);
    expect(block.data.fields.map((f: any) => f.widget)).toEqual(["text", "text", "number"]);
  });

  it("select 伪调用携带 options", () => {
    const block = parsePseudoForm('input.form({ "风格": input.select({options: ["专业", "幽默"]}) })')!;
    expect(block!.data.fields[0].options).toEqual(["专业", "幽默"]);
  });

  it("非表单文本返回 null", () => {
    expect(parsePseudoForm("普通文字")).toBeNull();
  });
});
