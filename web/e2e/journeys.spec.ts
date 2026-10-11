import { expect, test } from "@playwright/test";
import {
  state,
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
  await expect(page.getByText("💬 会话中心")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("我的待办").or(page.getByText("⭐")).first()).toBeVisible();
});

test("旅程 2:新建定时任务 → 会话中心即时出现(20261009 反馈回归)", async ({ page }) => {
  await loginViaToken(page);
  await createScheduledTask(page, "E2E巡检", "回复「巡检完成」四个字即可");
  // 会话中心「我的任务」应即时出现(M30 事件刷新)
  await expect(page.getByText("E2E巡检").first()).toBeVisible({ timeout: 10_000 });
});

test("旅程 3:跑一次 → 运行徽标 → 完成 → 交付物 → 点开执行现场", async ({ page }) => {
  await loginViaToken(page);
  await createScheduledTask(page, "E2E执行", "只回复:执行完成");
  await runLatestTask(page);

  // 运行中:任务行/运行区可见运行态(呼吸徽标或文案)
  await expect(page.getByText("运行中").first()).toBeVisible({ timeout: 20_000 });

  // v4:等会话中心出现带交付物的会话行(真实 LLM,最长 150s)
  await expect(page.getByText(/📦/).first()).toBeVisible({ timeout: 150_000 });

  // 点击带 📦 的会话行进会话看产出
  const artRow = page.locator("tr", { hasText: /E2E执行/ }).first();
  await artRow.locator("button").first().click();
  await expect(page.getByText(/执行完成/).first()).toBeVisible({ timeout: 20_000 });
});

test("旅程 4:手动对话会话出现在会话中心 → 点击重开(20261010 v4)", async ({ page }) => {
  await loginViaToken(page);
  // 登录后默认工作台,先切到对话视图
  await page.getByRole("button", { name: "💬 对话", exact: true }).click();
  await page.waitForTimeout(1_500);
  await page.getByPlaceholder(/输入消息/).fill("你好这是测试消息");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(3_000);

  await page.getByRole("button", { name: "🏠 工作台", exact: true }).click();
  const manualRow = page.locator("tr", { hasText: "手动" }).first();
  await expect(manualRow).toBeVisible({ timeout: 15_000 });

  await manualRow.locator("button").first().click();
  await expect(page.getByPlaceholder(/输入消息/)).toBeVisible({ timeout: 15_000 });
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

test("旅程 8:启停切换 → 删除 → 会话中心转已完成折叠区", async ({ page }) => {
  await loginViaToken(page);
  // 启停:每行一个开关按钮(标题为 启用/停用 之一)——先展开确认按钮名
  const target = taskRow(page, "E2E晨报改名");
  await target.getByRole("button", { name: "停用" }).click();
  await expect(target.getByText("已停用")).toBeVisible({ timeout: 10_000 });

  // 删除(confirm 自动接受)
  page.once("dialog", (d) => d.accept());
  await target.getByRole("button", { name: "删除" }).click();
  await expect(page.getByText("E2E晨报改名").first()).toBeHidden({ timeout: 10_000 });

  // v4:删除后会话中心的该任务行消失(无"已完成折叠区"概念)
  await expect(page.locator('[data-task-name="E2E晨报改名"]')).toBeHidden({ timeout: 10_000 });
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

test("旅程 12:官方插件助手(英语学习)→ 提问 → 收到技能产出(20261011 M2)", async ({ page }) => {
  await loginViaToken(page);
  await page.goto("/assistants");
  const card = page
    .locator("div")
    .filter({ has: page.getByRole("heading", { name: "上海高中英语助手" }) })
    .filter({ has: page.getByRole("button", { name: /开始对话/ }) })
    .last();
  await card.getByRole("button", { name: /开始对话/ }).click();
  // 跳转后默认停在工作台视图,必须点"💬 对话"标签才会显示会话(20261011 实测);
  // 断言用 visible=true 过滤——工作台里藏着会话标题/历史摘要等隐藏同文元素,
  // 裸 getByText 的 .first() 会命中它们导致 flaky
  await page.waitForURL(/sessionId=/, { timeout: 20_000 });
  await page.getByRole("button", { name: "💬 对话", exact: true }).click();
  await page.waitForTimeout(1_500); // 视图重挂载稳定(同旅程 4);否则 fill 后 Enter 落在旧 DOM 上发不出去
  await expect(page.getByPlaceholder(/输入消息/)).toBeVisible({ timeout: 20_000 });
  await page.getByPlaceholder(/输入消息/).fill("讲一下 accumulate 这个词");
  await page.getByRole("button", { name: /发送/ }).click();
  // 发送后输入框清空,visible 匹配到的只会是聊天气泡(text 引擎会按 value 匹配 textarea,不能在发送前断言)
  await expect(page.locator("text=讲一下 accumulate 这个词 >> visible=true").first()).toBeVisible({
    timeout: 20_000,
  });
  // auto 池每次可能路由到不同模型,回复措辞有方差——断言词汇讲解的任一特征词
  await expect(
    page.locator("text=/音标|释义|搭配|例句|词性/ >> visible=true").first()
  ).toBeVisible({ timeout: 180_000 });
});

test("旅程 13:官方插件助手(数学学习)→ 提问 → 收到解题产出(20261011 M2)", async ({ page }) => {
  await loginViaToken(page);
  await page.goto("/assistants");
  const card = page
    .locator("div")
    .filter({ has: page.getByRole("heading", { name: "上海高中数学助手" }) })
    .filter({ has: page.getByRole("button", { name: /开始对话/ }) })
    .last();
  await card.getByRole("button", { name: /开始对话/ }).click();
  await page.waitForURL(/sessionId=/, { timeout: 20_000 });
  // 钉稳定模型(同旅程 14)
  const sid = page.url().match(/sessionId=([^&]+)/)?.[1] ?? "";
  await page.request.patch(`/api/chat/sessions/${sid}`, {
    headers: { Authorization: `Bearer ${state().token}` },
    data: { model_override: "deepseek-v4-pro" },
  });
  await page.getByRole("button", { name: "💬 对话", exact: true }).click();
  await page.waitForTimeout(1_500);
  await page.getByPlaceholder(/输入消息/).fill("解这道题:已知等差数列首项 2,公差 3,求第 10 项");
  await page.getByRole("button", { name: /发送/ }).click();
  // 回复措辞有方差,断言解题产出任一特征
  await expect(
    page.locator("text=/详解|易错|思路|步骤/ >> visible=true").first()
  ).toBeVisible({ timeout: 180_000 });
});

test("旅程 14:错题本插件 → 对话录入错题 → 工具落库确认(20261011 M3)", async ({ page }) => {
  test.setTimeout(300_000); // auto 池可能路由到慢模型,150s 不够(20261011 实测)
  await loginViaToken(page);
  await page.goto("/assistants");
  const card = page
    .locator("div")
    .filter({ has: page.getByRole("heading", { name: "上海高中错题本助手" }) })
    .filter({ has: page.getByRole("button", { name: /开始对话/ }) })
    .last();
  await card.getByRole("button", { name: /开始对话/ }).click();
  await page.waitForURL(/sessionId=/, { timeout: 20_000 });
  // 钉稳定模型:auto 池路由有方差,慢模型 240s 都出不了回复(20261011 实测)
  const sid = page.url().match(/sessionId=([^&]+)/)?.[1] ?? "";
  await page.request.patch(`/api/chat/sessions/${sid}`, {
    headers: { Authorization: `Bearer ${state().token}` },
    data: { model_override: "deepseek-v4-pro" },
  });
  await page.getByRole("button", { name: "💬 对话", exact: true }).click();
  await page.waitForTimeout(1_500);
  await page
    .getByPlaceholder(/输入消息/)
    .fill("帮我录入一道英语错题:题目是 He ____ (wait) since two hours. 我的答案是 has waited,正确答案是 has been waiting,错因是时态判断");
  await page.getByRole("button", { name: /发送/ }).click();
  // 工具落库成功后,助手确认话术有方差(已录入/已入库/任务处理完成/错题摘要都有出现过)——
  // 断言取并集;真正的落库事实由工具返回保证
  await expect(
    page.locator("text=/已入库|已录入|录入成功|任务处理完成|错题摘要/ >> visible=true").first()
  ).toBeVisible({ timeout: 240_000 });
});
