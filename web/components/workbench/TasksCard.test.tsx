/**
 * TasksCard 表格重构回归(20261010 四列:名称/类型/状态/交付物):
 * - 表头与行渲染(常规/定时类型列、运行中/已完成状态列)
 * - 交付物单元格点击 → 单件直接 md 预览
 * - 手动任务行内完成操作 → 状态变已完成
 * - 已完成折叠区
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TasksCard } from "./TasksCard";
import * as client from "../../lib/api/client";

const PANEL = {
  tasks: [
    { id: "t1", title: "季度评审", status: "active" as const, kind: "manual" as const, session_id: "s1", artifact_count: 2, created_at: "2026-10-10T10:00:00Z", completed_at: null },
    { id: "t2", title: "每天记单词", status: "active" as const, kind: "scheduled" as const, session_id: null, scheduled_task_id: "sch1", latest_session_id: "s2", artifact_count: 1, created_at: "2026-10-09T09:00:00Z", completed_at: null },
  ],
  done_tasks: [
    { id: "t3", title: "旧任务", status: "done" as const, kind: "manual" as const, session_id: "s3", artifact_count: 0, created_at: "2026-10-01T10:00:00Z", completed_at: "2026-10-05T10:00:00Z" },
  ],
  running: [
    { kind: "run" as const, id: "r1", title: "每天记单词", detail: "定时任务执行中", session_id: "s2", started_at: "2026-10-10T09:00:00Z", updated_at: null },
  ],
  scheduled: [
    { id: "sch1", name: "每天记单词", kind: "custom", next_run_at: "2026-10-11T09:00:00Z", last_status: "running" },
  ],
  artifacts: [
    { id: "a1", kind: "report" as const, title: "评审报告", created_at: "2026-10-10T10:00:00Z", session_id: "s1", signed_url: null, content: "评审结论:通过" },
    { id: "a2", kind: "image" as const, title: "配图", created_at: "2026-10-10T10:05:00Z", session_id: "s1", signed_url: "http://x/img.png", content: null },
    { id: "a3", kind: "report" as const, title: "单词速记报告", created_at: "2026-10-10T09:30:00Z", session_id: "s2", signed_url: null, content: "今日 3 词已推送" },
  ],
};

describe("TasksCard(四列表格)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("表头四列 + 类型/状态列正确渲染", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue(PANEL);
    render(<TasksCard onContinue={vi.fn()} onSaveToKb={vi.fn()} />);
    expect(await screen.findByText("季度评审")).toBeTruthy();
    expect(screen.getByText("任务名称")).toBeTruthy();
    expect(screen.getByText("类型")).toBeTruthy();
    expect(screen.getByText("状态")).toBeTruthy();
    expect(screen.getByText("交付物")).toBeTruthy();
    expect(screen.getByText("常规")).toBeTruthy();
    expect(screen.getByText("定时")).toBeTruthy();
    expect(screen.getByText("进行中")).toBeTruthy(); // manual active
    expect(screen.getByText("运行中")).toBeTruthy(); // scheduled running
  });

  it("单件交付物点击 → 直接 md 预览", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue(PANEL);
    render(<TasksCard onContinue={vi.fn()} onSaveToKb={vi.fn()} />);
    // 记单词只有 1 个 report → 点 📦 1 直接预览
    fireEvent.click(await screen.findByText("📦 1"));
    expect(await screen.findByText(/单词速记报告/)).toBeTruthy();
    expect(screen.getByText("今日 3 词已推送")).toBeTruthy();
  });

  it("多件交付物点击 → 列表弹层再选择", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue(PANEL);
    render(<TasksCard onContinue={vi.fn()} onSaveToKb={vi.fn()} />);
    fireEvent.click(await screen.findByText("📦 2")); // 季度评审 2 件
    expect(await screen.findByText(/季度评审 · 交付物/)).toBeTruthy();
    expect(screen.getByText(/评审报告/)).toBeTruthy();
    expect(screen.getByText(/配图/)).toBeTruthy();
    fireEvent.click(screen.getByText(/评审报告/));
    expect(await screen.findByText("评审结论:通过")).toBeTruthy();
  });

  it("手动任务行内完成 → PATCH + 刷新", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue(PANEL);
    const patch = vi.spyOn(client, "apiPatch").mockResolvedValue({ ok: true });
    render(<TasksCard onContinue={vi.fn()} onSaveToKb={vi.fn()} />);
    await screen.findByText("季度评审");
    fireEvent.click(screen.getByTitle("标记完成"));
    expect(patch).toHaveBeenCalledWith("/tasks/t1", { status: "done" });
  });

  it("已完成折叠区展开可见", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue(PANEL);
    render(<TasksCard onContinue={vi.fn()} onSaveToKb={vi.fn()} />);
    await screen.findByText("季度评审");
    expect(screen.queryByText("旧任务")).toBeNull(); // 默认收起
    fireEvent.click(screen.getByRole("button", { name: /已完成\(1\)/ }));
    expect(screen.getByText(/旧任务/)).toBeTruthy();
    expect(screen.getByText("已完成")).toBeTruthy(); // 状态列
  });

  it("空态提示", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue({ tasks: [], done_tasks: [], running: [], scheduled: [], artifacts: [] });
    render(<TasksCard onContinue={vi.fn()} onSaveToKb={vi.fn()} />);
    expect(await screen.findByText(/暂无任务/)).toBeTruthy();
  });
});
