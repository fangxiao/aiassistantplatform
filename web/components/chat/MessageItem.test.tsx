/**
 * friendlyLabel output_block 语义化标签回归(20261015 工单 20261015-0956-0059e1):
 * 此前所有 output_block 一律显示"给出了填写表单",表格/卡片被误标为表单。
 * 通过渲染组件断言工具进度条文案(MessageItem 私有函数经 UI 行为验证)。
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import MessageItem from "./MessageItem";
import type { ChatMessage } from "../../lib/types";

const msg = (toolCalls: ChatMessage["toolCalls"]): { message: ChatMessage } => ({
  message: {
    id: "m1",
    role: "assistant",
    text: "完成",
    toolCalls,
  } as ChatMessage,
});

describe("MessageItem 工具徽标(output_block 按 type 语义化)", () => {
  it("table 类型显示「数据表格」,不再冒充表单", () => {
    render(
      <MessageItem
        {...msg([{ id: "c1", name: "output_block", args: { type: "table" }, result: "ok" }])}
        onSaveToKb={vi.fn()}
      />,
    );
    expect(screen.getByText(/数据表格/)).toBeTruthy();
    expect(screen.queryByText(/填写表单/)).toBeNull();
  });

  it("card/metric_stat/waterfall 各自语义化", () => {
    for (const [type, label] of [
      ["card", "方案卡片"],
      ["metric_stat", "指标看板"],
      ["waterfall", "时序流"],
    ] as const) {
      const { unmount } = render(
        <MessageItem
          {...msg([{ id: "c1", name: "output_block", args: { type }, result: "ok" }])}
          onSaveToKb={vi.fn()}
        />,
      );
      expect(screen.getByText(new RegExp(label))).toBeTruthy();
      unmount();
    }
  });

  it("input.form 下发仍显示「输入表单」", () => {
    render(
      <MessageItem
        {...msg([{ id: "c1", name: "output_block", args: { type: "input.form" }, result: "ok" }])}
        onSaveToKb={vi.fn()}
      />,
    );
    expect(screen.getByText(/输入表单/)).toBeTruthy();
  });

  it("args 为 JSON 字符串形态(旧客户端)同样解析", () => {
    render(
      <MessageItem
        {...msg([{ id: "c1", name: "output_block", args: '{"type":"table"}', result: "ok" }])}
        onSaveToKb={vi.fn()}
      />,
    );
    expect(screen.getByText(/数据表格/)).toBeTruthy();
  });

  it("type 缺省回落「组件渲染」,不出现表单文案", () => {
    render(
      <MessageItem
        {...msg([{ id: "c1", name: "output_block", args: {}, result: "ok" }])}
        onSaveToKb={vi.fn()}
      />,
    );
    expect(screen.getByText(/组件渲染/)).toBeTruthy();
  });
});


describe("MessageItem 用户消息附件回显(20261015)", () => {
  it("image 块渲染缩略图,file 块渲染文档芯片", () => {
    render(
      <MessageItem
        message={
          {
            id: "u1",
            role: "user",
            text: "帮我看看这道题",
            blocks: [
              { type: "markdown", data: { text: "帮我看看这道题" } },
              { type: "image", data: { url: "https://x/api/files/raw?path=/a.png&sig=s" } },
              { type: "file", data: { name: "测算.xlsx", url: "https://x/api/files/raw?path=/b.xlsx&sig=s" } },
            ],
          } as any
        }
        onSaveToKb={vi.fn()}
      />,
    );
    const img = document.querySelector("img[alt='附件图片1']") as HTMLImageElement;
    expect(img).toBeTruthy();
    expect(img.src).toContain("/api/files/raw");
    expect(screen.getByText("测算.xlsx")).toBeTruthy();
    expect(screen.getByText("帮我看看这道题")).toBeTruthy();
  });

  it("纯文本用户消息渲染不受影响", () => {
    render(
      <MessageItem
        message={{ id: "u2", role: "user", text: "你好" } as any}
        onSaveToKb={vi.fn()}
      />,
    );
    expect(screen.getByText("你好")).toBeTruthy();
    expect(document.querySelector("img")).toBeNull();
  });
});


describe("MessageItem 连续同类工具折叠聚合(20261015 工单 1538-1e28fe)", () => {
  const searchCalls = (n: number) =>
    Array.from({ length: n }, (_, i) => ({
      id: `c${i}`,
      name: "tool:kb_search",
      args: {},
      result: '{"ok": true}',
    }));

  it("连续 >2 次同类工具折叠为单行「n 次已完成」,默认不刷屏", () => {
    render(
      <MessageItem
        message={{ id: "a1", role: "assistant", text: "结论", toolCalls: searchCalls(12) } as any}
        onSaveToKb={vi.fn()}
      />,
    );
    expect(screen.getByText(/信息搜索.{0,3}12 次已完成/)).toBeTruthy();
    // 明细默认收起:不渲染 12 行"完成"
    expect(screen.queryAllByText(/信息搜索完成/).length).toBe(0);
  });

  it("点击展开可见全部明细行,且带检索关键词入参摘要", () => {
    const calls = Array.from({ length: 3 }, (_, i) => ({
      id: `c${i}`,
      name: "tool:kb_search",
      args: { query: `消金场景规范 第${i + 1}篇` },
      result: '{"ok": true}',
    }));
    render(
      <MessageItem
        message={{ id: "a2", role: "assistant", text: "结论", toolCalls: calls } as any}
        onSaveToKb={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText(/信息搜索.{0,3}3 次已完成/));
    expect(screen.queryAllByText(/信息搜索完成/).length).toBe(3);
    // 20261015 工单 1706-27e1c1:展开后可见每次调用的入参摘要
    expect(screen.getByText(/关键词: 消金场景规范 第1篇/)).toBeTruthy();
    expect(screen.getByText(/关键词: 消金场景规范 第3篇/)).toBeTruthy();
  });

  it("≤2 次同类调用保持平铺(不折叠)", () => {
    render(
      <MessageItem
        message={{ id: "a3", role: "assistant", text: "ok", toolCalls: searchCalls(2) } as any}
        onSaveToKb={vi.fn()}
      />,
    );
    expect(screen.queryAllByText(/信息搜索完成/).length).toBe(2);
    expect(screen.queryByText(/次已完成/)).toBeNull();
  });

  it("非连续同类调用不合并(时序真实)", () => {
    render(
      <MessageItem
        message={
          {
            id: "a4",
            role: "assistant",
            text: "ok",
            toolCalls: [
              { id: "c0", name: "tool:kb_search", args: {}, result: '{"ok": true}' },
              { id: "c1", name: "tool:echo", args: {}, result: '{"ok": true}' },
              { id: "c2", name: "tool:kb_search", args: {}, result: '{"ok": true}' },
            ],
          } as any
        }
        onSaveToKb={vi.fn()}
      />,
    );
    expect(screen.queryByText(/次已完成/)).toBeNull();
  });
});
