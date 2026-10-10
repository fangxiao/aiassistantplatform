import { expect, test } from "@playwright/test";
import {
  clickStable,
  createWeeklyTask,
  createScheduledTask,
  loginViaToken,
  registerAndLogin,
  runLatestTask,
  taskRow,
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

  // 等完成:表格第四列交付物出现(真实 LLM,最长 150s)
  await expect(page.getByRole("button", { name: /📦/ }).first()).toBeVisible({ timeout: 150_000 });

  // 交付物(表格第四列):点 📦 → 单件 report 直接 md 预览产出全文(20261010 表格重构)
  await page.getByRole("button", { name: /📦/ }).first().click();
  await expect(page.getByText(/执行完成/).first()).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: "✕" }).last().click();

  // 任务名称列点开执行现场
  await page.getByRole("button", { name: "E2E执行", exact: true }).click();
  await expect(page.getByText(/执行完成/).first()).toBeVisible({ timeout: 20_000 });
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
  const doneBtn = page.getByTitle("标记完成").first();
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

// ── 定时任务面板全覆盖(M31:用户随手测踩坑区,20261009 补)──

test("旅程 6:模板任务(晨报)快速创建 → 列表出现", async ({ page }) => {
  await loginViaToken(page);
  await clickStable(page, "＋ 新建任务");
  await page.getByPlaceholder("例如: 每日晨报").fill("E2E晨报");
  await clickStable(page, "创建任务");
  await expect(page.getByText("E2E晨报").first()).toBeVisible({ timeout: 10_000 });
});

test("旅程 7:编辑任务改名 → 列表即时更新", async ({ page }) => {
  await loginViaToken(page);
  const row = page.locator("div").filter({ hasText: "E2E晨报" }).locator("button", { hasText: "编辑" }).first();
  await row.click();
  await page.getByPlaceholder("例如: 每日晨报").fill("E2E晨报改名");
  await clickStable(page, "保存修改");
  await expect(page.getByText("E2E晨报改名").first()).toBeVisible({ timeout: 10_000 });
});

test("旅程 8:启停切换 → 删除 → 任务中心转已完成折叠区", async ({ page }) => {
  await loginViaToken(page);
  // 启停:每行一个开关按钮(标题为 启用/停用 之一)——先展开确认按钮名
  const target = taskRow(page, "E2E晨报改名");
  await target.getByRole("button", { name: "停用" }).click();
  await expect(target.getByText("已停用")).toBeVisible({ timeout: 10_000 });

  // 删除(confirm 自动接受)
  page.once("dialog", (d) => d.accept());
  await target.getByRole("button", { name: "删除" }).click();
  await expect(page.getByText("E2E晨报改名").first()).toBeHidden({ timeout: 10_000 });

  // 任务中心:折叠区出现该任务(定时删除 → 实体转已完成)
  await page.getByRole("button", { name: /已完成\(/ }).click();
  await expect(page.getByText("E2E晨报改名").first()).toBeVisible({ timeout: 10_000 });
});

test("旅程 9:运行记录展开 → 看到产出 → 进入会话(真实运行后)", async ({ page }) => {
  test.setTimeout(300_000); // 含真实 LLM 执行 + 轮询刷新,上游慢时需要更长时间
  await loginViaToken(page);
  await createScheduledTask(page, "E2E记录", "只回复:记录验证");
  await runLatestTask(page);
  // 等运行完成(记录里出现产出)
  const recBtn = taskRow(page, "E2E记录").getByRole("button", { name: "记录" });
  await expect(recBtn).toBeVisible({ timeout: 15_000 });
  // 展开后 runs 是点击瞬间的快照(组件不自动刷新)——轮询:显式收起→重展开(重拉)
  await recBtn.click();
  for (let i = 0; i < 25; i++) {
    const visible = await page.getByText("记录验证").first().isVisible().catch(() => false);
    if (visible) break;
    const collapseBtn = page.getByRole("button", { name: "收起", exact: true }).first();
    if (await collapseBtn.isVisible().catch(() => false)) {
      await collapseBtn.click(); // 收起
      await page.waitForTimeout(400);
    }
    await recBtn.click(); // 展开(重拉 runs)
    await page.waitForTimeout(8_000);
  }
  // 从记录「继续追问」进入会话
  await page.getByRole("button", { name: "继续追问 →" }).first().click();
  await expect(page.getByText("记录验证").first()).toBeVisible({ timeout: 20_000 });
});

test("旅程 10:推送区渲染(目标下拉 + 测试按钮,不真推)", async ({ page }) => {
  await loginViaToken(page);
  await clickStable(page, "＋ 新建任务");
  await page.getByPlaceholder("例如: 每日晨报").fill("E2E推送UI");
  // 飞书推送下拉存在且含「不推送」默认项
  const pushSelect = page.locator("select").filter({ hasText: "不推送" }).first();
  await expect(pushSelect).toBeVisible({ timeout: 5_000 });
  // 测试按钮存在(未选目标时禁用)
  await expect(page.getByRole("button", { name: "测试" }).first()).toBeDisabled();
  await page.getByRole("button", { name: "取消" }).click();
});

test("旅程 11:每周任务(周报)创建 → 显示每周周一(20261010 对标补齐)", async ({ page }) => {
  await loginViaToken(page);
  await createWeeklyTask(page, "E2E周报任务");
  await expect(page.locator('[data-task-name="E2E周报任务"]').getByText(/每周一/)).toBeVisible({
    timeout: 10_000,
  });
  const target = taskRow(page, "E2E周报任务");
  page.once("dialog", (d) => d.accept());
  await target.getByRole("button", { name: "删除" }).click();
  await expect(page.locator('[data-task-name="E2E周报任务"]')).toBeHidden({ timeout: 10_000 });
});
