/**
 * TasksCard 渲染回归(M25/需求 014):
 * - 三栏结构(进行中/定时任务/交付物)与空态
 * - 交付物:跳会话回调、report 存 KB 回调、文件类点击打开
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TasksCard } from "./TasksCard";
import * as client from "../../lib/api/client";

const PANEL = {
  tasks: [
    { id: "e1", title: "季度评审", status: "active" as const, kind: "manual" as const, session_id: "s1", artifact_count: 2, created_at: "2026-10-06T10:00:00Z", completed_at: null },
  ],
  running: [
    { kind: "session" as const, id: "s1", title: "评审会话", detail: "评审完成", session_id: "s1", started_at: null, updated_at: "2026-10-06T10:00:00Z" },
    { kind: "run" as const, id: "r1", title: "每日简报", detail: "定时任务执行中", session_id: "s2", started_at: "2026-10-06T09:00:00Z", updated_at: null },
  ],
  scheduled: [
    { id: "t1", name: "每日简报", kind: "briefing", next_run_at: "2026-10-07T08:00:00Z", last_status: "success" },
  ],
  artifacts: [
    { id: "a1", kind: "image" as const, title: "柴犬水彩", created_at: "2026-10-06T10:00:00Z", session_id: "s1", signed_url: "http://x/api/files/raw?path=%2Fa.png&exp=1&sig=s", content: null },
    { id: "a2", kind: "report" as const, title: "每日简报 · 10-06", created_at: "2026-10-06T09:00:00Z", session_id: "s2", signed_url: null, content: "今日 3 条动态" },
  ],
};

describe("TasksCard", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("三栏渲染:进行中/定时任务/交付物", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue(PANEL);
    render(<TasksCard onContinue={vi.fn()} onSaveToKb={vi.fn()} />);
    expect(await screen.findByText("评审会话")).toBeTruthy();
    expect(screen.getByText("季度评审")).toBeTruthy(); // M28 实体区
    expect(screen.getByText(/2 个交付物/)).toBeTruthy();
    expect(screen.getAllByText("每日简报").length).toBeGreaterThanOrEqual(2); // run + scheduled(+report 标题)
    expect(screen.getByText("柴犬水彩")).toBeTruthy();
    expect(screen.getByText("成功")).toBeTruthy();
  });

  it("交付物「继续」触发跳会话回调", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue(PANEL);
    const onContinue = vi.fn();
    render(<TasksCard onContinue={onContinue} onSaveToKb={vi.fn()} />);
    await screen.findByText("柴犬水彩");
    fireEvent.click(screen.getAllByText("继续")[0]); // 首个交付物(image,session s1)
    expect(onContinue).toHaveBeenCalledWith("s1");
  });

  it("report「存 KB」带产出内容回调", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue(PANEL);
    const onSaveToKb = vi.fn();
    render(<TasksCard onContinue={vi.fn()} onSaveToKb={onSaveToKb} />);
    fireEvent.click(await screen.findByText("存 KB"));
    expect(onSaveToKb).toHaveBeenCalledWith("今日 3 条动态");
  });

  it("空态:三区各自占位文案", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue({ tasks: [], running: [], scheduled: [], artifacts: [] });
    render(<TasksCard onContinue={vi.fn()} onSaveToKb={vi.fn()} />);
    expect(await screen.findByText(/暂无任务/)).toBeTruthy();
    expect(screen.getByText("暂无进行中的任务")).toBeTruthy();
    expect(screen.getByText("暂无定时任务")).toBeTruthy();
    expect(screen.getByText(/暂无产出/)).toBeTruthy();
  });
});
