/**
 * 会话中心 v4 回归(20261010):统一会话列表(定时+手动)。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TasksCard } from "./TasksCard";
import * as client from "../../lib/api/client";

const PANEL = {
  sessions: [
    { session_id: "s1", title: "季度评审讨论", source: "manual" as const, last_active: "2026-10-10T10:00:00Z", artifact_count: 2, running: false, next_run_at: null },
    { session_id: "s2", title: "每天记单词 · 10-10", source: "scheduled" as const, last_active: "2026-10-10T09:00:00Z", artifact_count: 1, running: true, next_run_at: "2026-10-11T09:00:00Z" },
    { session_id: "s3", title: "每天一篇文言文 · 10-09", source: "scheduled" as const, last_active: "2026-10-09T20:00:00Z", artifact_count: 0, running: false, next_run_at: "2026-10-10T20:00:00Z" },
  ],
};

describe("TasksCard(会话中心 v4)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("表头四列 + 来源徽标 + 交付物计数", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue(PANEL);
    render(<TasksCard onContinue={vi.fn()} onSaveToKb={vi.fn()} />);
    expect(await screen.findByText("💬 会话中心")).toBeTruthy();
    expect(screen.getByText("会话")).toBeTruthy();
    expect(screen.getByText("来源")).toBeTruthy();
    expect(screen.getByText("最后活跃")).toBeTruthy();
    expect(screen.getByText("交付物")).toBeTruthy();
    expect(screen.getAllByText("⏰ 定时").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("💬 手动").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("📦 2")).toBeTruthy();
    expect(screen.getByText("📦 1")).toBeTruthy();
  });

  it("点击会话行跳转", async () => {
    const onContinue = vi.fn();
    vi.spyOn(client, "apiGet").mockResolvedValue(PANEL);
    render(<TasksCard onContinue={onContinue} onSaveToKb={vi.fn()} />);
    fireEvent.click(await screen.findByText("季度评审讨论"));
    expect(onContinue).toHaveBeenCalledWith("s1");
  });

  it("运行中的定时会话有 spinner", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue(PANEL);
    render(<TasksCard onContinue={vi.fn()} onSaveToKb={vi.fn()} />);
    await screen.findByText("每天记单词 · 10-10");
    expect(document.querySelector(".animate-spin")).toBeTruthy();
  });

  it("空态提示", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue({ sessions: [] });
    render(<TasksCard onContinue={vi.fn()} onSaveToKb={vi.fn()} />);
    expect(await screen.findByText(/暂无会话/)).toBeTruthy();
  });
});
