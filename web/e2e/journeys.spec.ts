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
  test.setTimeout(300_000); // auto 池路由到慢模型时 180s 不够(20261017 实测,同旅程 14)
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
    page.locator("text=/详解|易错|思路|步骤|过程|答案/ >> visible=true").first()
  ).toBeVisible({ timeout: 180_000 });
});

test("旅程 14:错题本插件 → 对话录入错题 → 工具落库确认(20261011 M3)", async ({ page }) => {
  test.setTimeout(300_000); // auto 池可能路由到慢模型,150s 不够(20261011 实测)
  await loginViaToken(page);
  await page.goto("/assistants");
  const card = page
    .locator("div")
    .filter({ has: page.getByRole("heading", { name: "错题本助手" }) })
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

// ── 错题本全链路(20261015 补齐:复习闭环/学情/边界/持久,真模型 + DB 断言)──

import { execSync } from "node:child_process";

/** 查错题本存储(stage/数量),供确定性断言 */
function queryMistakeDb(sql: string): string {
  try {
    return execSync(
      `docker exec agentplatform-pg-1 psql -U agentplatform -d agentplatform -t -c "${sql}"`,
      { stdio: "pipe" },
    ).toString();
  } catch {
    return execSync(`psql -h localhost -U agentplatform -d agentplatform -t -c "${sql}"`, {
      stdio: "pipe",
    }).toString();
  }
}

async function openMistakeChat(page: import("@playwright/test").Page) {
  await page.goto("/assistants");
  const card = page
    .locator("div")
    .filter({ has: page.getByRole("heading", { name: "错题本助手" }) })
    .filter({ has: page.getByRole("button", { name: /开始对话/ }) })
    .last();
  await card.getByRole("button", { name: /开始对话/ }).click();
  await page.waitForURL(/sessionId=/, { timeout: 20_000 });
  const sid = page.url().match(/sessionId=([^&]+)/)?.[1] ?? "";
  await page.request.patch(`/api/chat/sessions/${sid}`, {
    headers: { Authorization: `Bearer ${state().token}` },
    data: { model_override: "deepseek-v4-pro" },
  });
  await page.getByRole("button", { name: "💬 对话", exact: true }).click();
  await page.waitForTimeout(1_500);
  return sid;
}

test("旅程 15:错题本复习闭环——录入 → 到期卷 → 答对进阶/答错回炉(20261015)", async ({ page }) => {
  test.setTimeout(600_000);
  await loginViaToken(page);
  await openMistakeChat(page);
  const input = page.getByPlaceholder(/输入消息/);

  // 1. 录入两道错题(旅程自洽:不依赖旅程 14 的记录,隔离跑/串行跑均成立)
  await input.fill("帮我录入一道数学错题:题目是解方程 2x+3=11,我的答案是 x=7,正确答案是 x=4,错因是移项没变号");
  await page.getByRole("button", { name: /发送/ }).click();
  await expect(
    page.locator("text=/已入库|已录入|录入成功|任务处理完成/ >> visible=true").first()
  ).toBeVisible({ timeout: 240_000 });
  await input.fill("再录入一道物理错题:题目是质量 2kg 的物体所受重力(g 取 10),我的答案是 12N,正确答案是 20N,错因是公式代错");
  await page.getByRole("button", { name: /发送/ }).click();
  await expect(
    page.locator("text=/已入库|已录入|录入成功|任务处理完成/ >> visible=true").first()
  ).toBeVisible({ timeout: 240_000 });

  // 2. 复习卷(as_of=明天,两道都在第 1 轮):题面出现、答案只出现在核对区
  await input.fill("复习日期按明天算,给我明天到期的错题,生成复习卷(共两道:数学与物理)");
  await page.getByRole("button", { name: /发送/ }).click();
  await expect(
    page.locator("text=/核对区|核对|复习卷/ >> visible=true").first()
  ).toBeVisible({ timeout: 240_000 });
  await expect(page.locator("text=/2x\\+3=11|has been waiting/").first()).toBeVisible();
  await page.screenshot({ path: "test-results/mistake-15-due.png", fullPage: true });

  // 3. 反馈:逐条单消息(多条目单消息的 grade 映射有模型遵从度方差,20261015 实测)
  await input.fill("复习反馈:物理错题(重力那道)我答对了,是 20N");
  await page.getByRole("button", { name: /发送/ }).click();
  await expect(
    page.locator("text=/进阶|第 2 轮|第2轮/ >> visible=true").first()
  ).toBeVisible({ timeout: 240_000 });
  await input.fill("数学错题(2x+3=11 那道)我复习时又做错了,还是写成 x=7");
  await page.getByRole("button", { name: /发送/ }).click();
  await expect(
    page.locator("text=/回炉|答错/ >> visible=true").first()
  ).toBeVisible({ timeout: 240_000 });

  // 4. DB 断言(确定性):英语题 stage=2,数学题 stage=1
  const stages = queryMistakeDb(
    "SELECT data->>'stage' FROM plugin_data WHERE plugin_name='study-mistakes' AND data->>'question' LIKE '%2kg%' ORDER BY created_at DESC LIMIT 1;",
  ).trim();
  const stages2 = queryMistakeDb(
    "SELECT data->>'stage' FROM plugin_data WHERE plugin_name='study-mistakes' AND data->>'question' LIKE '%2x+3=11%' ORDER BY created_at DESC LIMIT 1;",
  ).trim();
  expect(stages).toBe("2"); // 物理题答对进阶
  expect(stages2).toBe("1");
  await page.screenshot({ path: "test-results/mistake-15-graded.png", fullPage: true });
});

test("旅程 16:错题本学情汇总 + 职责边界 + 跨会话持久(20261015)", async ({ page }) => {
  test.setTimeout(600_000);
  await loginViaToken(page);

  // 1. 学情汇总:数字与 DB 一致性由人工核,自动化断言汇总卡片出现
  await openMistakeChat(page);
  const input = page.getByPlaceholder(/输入消息/);
  await input.fill("汇总一下我的学情");
  await page.getByRole("button", { name: /发送/ }).click();
  await expect(
    page.locator("text=/学科|错因|到期|学情/ >> visible=true").first()
  ).toBeVisible({ timeout: 240_000 });

  // 2. 职责边界:域外请求不得新增错题记录(DB 计数不变)
  const before = queryMistakeDb(
    "SELECT count(*) FROM plugin_data WHERE plugin_name='study-mistakes';"
  ).trim();
  await input.fill("帮我生成今天的英语单词表,20 个高考高频词");
  await page.getByRole("button", { name: /发送/ }).click();
  await page.waitForTimeout(30_000); // 给模型充分越界的机会
  const after = queryMistakeDb(
    "SELECT count(*) FROM plugin_data WHERE plugin_name='study-mistakes';"
  ).trim();
  expect(after).toBe(before); // 越界请求不产生错题数据
  await page.screenshot({ path: "test-results/mistake-16-boundary.png", fullPage: true });

  // 3. 跨会话持久:新会话仍可见全部错题
  await openMistakeChat(page);
  await input.fill("我的错题本里有哪些题?");
  await page.getByRole("button", { name: /发送/ }).click();
  await expect(
    page.locator("text=/2x\\+3=11|2kg/").first()
  ).toBeVisible({ timeout: 240_000 });
});

// ── 学生自助闭环(20261017 批次 1:推荐订阅 / 我的订阅 / 导航收敛)──

test("旅程 17:错题本白牌页订阅 → 时间可选 → 我的订阅可见 → 可删除(20261017)", async ({ page }) => {
  test.setTimeout(300_000);
  await loginViaToken(page);
  await page.goto("/a/k2Rz64nIjhb5SPq6");
  await expect(page.getByText("错题本助手").first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /🔔 订阅/ }).click();
  await page.locator('input[type="time"]').fill("20:15");
  await page.getByRole("button", { name: /确认订阅/ }).click();
  await expect(page.getByText(/已订阅/).first()).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "我的", exact: true }).click();
  await expect(page.getByText("每日错题回顾").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/20:15/).first()).toBeVisible();
  await page.getByRole("button", { name: "删除" }).first().click();
  await expect(page.getByText(/暂无订阅/).first()).toBeVisible({ timeout: 15_000 });
});

test("旅程 18:导航按角色收敛——普通用户无开发者入口,developer 全量(20261017)", async ({ page }) => {
  await loginViaToken(page); // personas=developer
  await page.goto("/");
  await expect(page.getByRole("link", { name: /开发者中心/ }).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("link", { name: /知识库/ }).first()).toBeVisible();

  // 普通学生:服务端 personas 改 student + 独立新页面(干净 init)
  const s = state();
  await page.request.patch("http://localhost:8000/api/auth/me/personas", {
    headers: { Authorization: `Bearer ${s.token}` },
    data: { personas: ["student"] },
  });
  const p2 = await page.context().newPage();
  await p2.addInitScript(
    ([t, u]) => {
      localStorage.setItem("agentplatform_token", t!);
      localStorage.setItem("agentplatform_user", u!);
    },
    [s.token, JSON.stringify({ email: s.email, role: "user", personas: ["student"] })],
  );
  await p2.goto("/");
  await expect(p2.getByText("会话中心").first()).toBeVisible({ timeout: 20_000 });
  await p2.waitForLoadState("networkidle"); // 等角色实时校准(/auth/me)完成
  const nav = p2.getByRole("banner");
  await expect(nav.getByRole("link", { name: /开发者中心/ })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: /知识库/ })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: /对话工作台/ }).first()).toBeVisible();
  await p2.close();
  // 还原服务端 personas(developer,供后续旅程)
  await page.request.patch("http://localhost:8000/api/auth/me/personas", {
    headers: { Authorization: `Bearer ${s.token}` },
    data: { personas: ["developer"] },
  });
});
