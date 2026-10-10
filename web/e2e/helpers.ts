import { execSync } from "node:child_process";
import fs from "node:fs";
import { Page, expect } from "@playwright/test";

/** 重试点击:工作台卡片轮询会周期性重建 DOM(detach),单次 click 易扑空 */
export async function clickStable(page: Page, name: string, attempts = 4) {
  for (let i = 0; i < attempts; i++) {
    try {
      await page.getByRole("button", { name }).click({ timeout: 8_000 });
      return;
    } catch {
      /* detach/超时则重试 */
    }
  }
  try {
    // 兜底:跳过稳定性检查直接点(按钮场景安全,onClick 照常派发)
    await page.getByRole("button", { name }).click({ force: true, timeout: 5_000 });
  } catch {
    await page.getByRole("button", { name }).click(); // 原样抛出供诊断
  }
}

interface State {
  invite: string;
  email: string;
  password: string;
  token?: string;
}

const STATE_PATH = `${__dirname}/.state.json`;

/** DB 直标已验证(E2E 环境模拟"用户点了邮件链接"——邮件通道不可自动化) */
function verifyEmailViaDb(email: string): void {
  try {
    execSync(
      `docker exec agentplatform-pg-1 psql -U agentplatform -d agentplatform -c ` +
        `"UPDATE users SET email_verified_at=now() WHERE email='${email}'"`,
      { stdio: "pipe" },
    );
  } catch {
    /* 标记失败时后续登录被拦,测试会显式暴露 */
  }
}

export function state(): State {
  return JSON.parse(fs.readFileSync(STATE_PATH, "utf-8"));
}

function saveState(s: State) {
  fs.writeFileSync(STATE_PATH, JSON.stringify(s));
}

/** 经真实注册表单开户(带邀请码)并进入工作台(仅旅程 1 使用) */
export async function registerAndLogin(page: Page) {
  const s = state();
  await page.goto("/auth");
  await page.getByRole("button", { name: "注册" }).click();
  await page.getByPlaceholder("you@example.com").fill(s.email);
  await page.locator('input[type="password"]').first().fill(s.password);
  await page.getByPlaceholder("向管理员索取(inv-xxxxxxxxxx)").fill(s.invite);
  await page.getByRole("button", { name: "注册并登录" }).click();
  // M33 邮箱闸门:注册后自动登录被拦 → 进入待验证引导视图(新 UI 一并验收);
  // DB 标记模拟"用户点了邮件链接" → 点「我已验证,重新登录」走完闭环
  await expect(page.getByText("验证邮件已发送")).toBeVisible({ timeout: 15_000 });
  verifyEmailViaDb(s.email);
  await page.getByRole("button", { name: /我已验证/ }).click();
  await expect(page.getByText("💬 会话中心")).toBeVisible({ timeout: 30_000 });
  // 注册成功后缓存当前 token,后续旅程注入复用(避开登录限频 5/min)
  const token = await page.evaluate(() => localStorage.getItem("agentplatform_token"));
  if (token) {
    saveState({ ...s, token });
  }
}

/** token 登录态注入(旅程 2+):不触碰注册/登录接口,规避限频 */
export async function loginViaToken(page: Page) {
  const s = state();
  if (!s.token) {
    // 兜底:账号可能未注册(--grep 跳过旅程 1 时)——先注册再登录
    await page.request.post("http://localhost:8000/api/auth/register", {
      data: { email: s.email, password: s.password, invite_code: s.invite },
    });
    verifyEmailViaDb(s.email);
    const resp = await page.request.post("http://localhost:8000/api/auth/login", {
      data: { email: s.email, password: s.password },
    });
    const body = (await resp.json()) as { token: string; user: unknown };
    if (!body.token) throw new Error(`E2E 登录失败: ${JSON.stringify(body)}`);
    saveState({ ...s, token: body.token });
  }
  const cur = state();
  await page.addInitScript(
    ([t, u]) => {
      localStorage.setItem("agentplatform_token", t!);
      localStorage.setItem("agentplatform_user", u!);
    },
    [cur.token, JSON.stringify({ email: cur.email, role: "user" })],
  );
  await page.goto("/");
  // 视图无关的登录成功标志(视图可能注入为 chat)
  await expect(page.getByRole("button", { name: "退出" })).toBeVisible({ timeout: 30_000 });
}

/** 新建每周任务(周报场景):选每周 + 周一 + 时刻 */
export async function createWeeklyTask(page: Page, name: string) {
  await clickStable(page, "＋ 新建任务");
  await page.getByPlaceholder("例如: 每日晨报").fill(name);
  await page.locator('select', { has: page.locator('option[value="weekly"]') }).selectOption("weekly");
  await page.locator('select', { has: page.locator('option[value="1"]') }).selectOption("1");
  await page.locator('input[type="time"]').fill("09:00");
  await clickStable(page, "创建任务");
  await expect(page.getByText(name).first()).toBeVisible({ timeout: 15_000 });
}

/** 按任务名精确定位 SchedulerCard 行(data-task-name 锚点) */
export function taskRow(page: Page, name: string) {
  return page.locator(`[data-task-name="${name}"]`);
}

/** 跑最新任务(列表按创建时间倒序,最新任务行的「跑一次」排第一) */
export async function runLatestTask(page: Page) {
  const btn = page.getByRole("button", { name: "跑一次" }).first();
  for (let i = 0; i < 4; i++) {
    try {
      await btn.click({ timeout: 8_000 });
      return;
    } catch {
      /* detach 重试 */
    }
  }
  await btn.click({ force: true, timeout: 5_000 });
}

/** 新建定时任务(自定义指令;推送默认不推),保存后任务名可见 */
export async function createScheduledTask(page: Page, name: string, prompt: string) {
  await clickStable(page, "＋ 新建任务");
  await page.getByPlaceholder("例如: 每日晨报").fill(name);
  // kind 默认晨报(模板任务);下拉切「自定义指令」才出现指令输入框
  await page.getByLabel("任务模板").selectOption("custom");
  await page.getByPlaceholder("到点让助手做什么,例如: 总结我知识库里最近一周新增的内容").fill(prompt);
  await clickStable(page, "创建任务");
  await expect(page.getByText(name).first()).toBeVisible({ timeout: 15_000 });
}
