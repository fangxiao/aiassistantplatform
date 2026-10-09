import { expect, test } from "@playwright/test";
import {
  clickStable,
  createScheduledTask,
  loginViaToken,
  registerAndLogin,
  runLatestTask,
} from "./helpers";

/**
 * 用户旅程 E2E(C2):覆盖本周真实用户踩过的路径。
 * 跑在本地 docker 平台;含一次真实 LLM 定时任务(慢,180s 上限)。
 */

test.describe.configure({ mode: "serial" });

test("旅程 1:邀请码注册 → 登录 → 工作台", async ({ page }) => {
  await registerAndLogin(page);
  await expect(page.getByText("📋 任务中心")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("我的待办").or(page.getByText("⭐")).first()).toBeVisible();
});

test("旅程 2:新建定时任务 → 任务中心即时出现(20261009 反馈回归)", async ({ page }) => {
  await loginViaToken(page);
  await createScheduledTask(page, "E2E巡检", "回复「巡检完成」四个字即可");
  // 任务中心「我的任务」应即时出现(M30 事件刷新)
  await expect(page.getByText("E2E巡检").first()).toBeVisible({ timeout: 10_000 });
});

test("旅程 3:跑一次 → 运行徽标 → 完成 → 交付物 → 点开执行现场", async ({ page }) => {
  await loginViaToken(page);
  await createScheduledTask(page, "E2E执行", "只回复:执行完成");
  await runLatestTask(page);

  // 运行中:任务行/运行区可见运行态(呼吸徽标或文案)
  await expect(page.getByText("运行中").first()).toBeVisible({ timeout: 20_000 });

  // 等完成:交付物出现 report(真实 LLM,最长 150s)
  await expect(
    page.locator("section", { hasText: "交付物" }).getByText(/E2E执行 · /).first(),
  ).toBeVisible({ timeout: 150_000 });

  // 任务行(li)点开执行现场——交付物条目与任务同名,必须按行元素定位
  const row = page.locator("li").filter({ hasText: "E2E执行" }).first();
  await row.locator("button").first().click();
  await expect(page.getByText("执行完成").first()).toBeVisible({ timeout: 20_000 });
});

test("旅程 4:会话保存为任务 → 完成 → 已完成折叠区", async ({ page }) => {
  await loginViaToken(page);
  // 切到对话视图(等首屏路由/预取安静后再点,避开导航竞争)
  await page.waitForTimeout(1_500);
  await page.getByRole("button", { name: "💬 对话", exact: true }).click();
  await page.getByPlaceholder(/输入消息/).fill("你好");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(3_000);

  // 保存为任务:window.prompt 命名 → 轻提示 → 任务中心出现手动任务
  page.once("dialog", (d) => d.accept("E2E手动任务"));
  await page.getByRole("button", { name: "⭐ 保存为任务" }).click();
  await expect(page.getByText("已保存为任务").first()).toBeVisible({ timeout: 10_000 });

  // 切回工作台视图(任务中心此前在隐藏容器中)
  await page.getByRole("button", { name: "🏠 工作台", exact: true }).click();
  const doneBtn = page.getByRole("button", { name: "✓ 完成" }).first();
  await expect(doneBtn).toBeVisible({ timeout: 15_000 });
  await doneBtn.click();
  await page.getByRole("button", { name: /已完成\(/ }).click();
  await expect(page.getByText("E2E手动任务").first()).toBeVisible({ timeout: 10_000 });
});

test("旅程 5:登出 → 回登录页", async ({ page }) => {
  await loginViaToken(page);
  await page.getByRole("button", { name: "退出" }).click();
  await expect(page).toHaveURL(/\/auth/);
  await expect(page.getByText("agentplatform").first()).toBeVisible();
});
