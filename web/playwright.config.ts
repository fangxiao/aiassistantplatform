import { defineConfig } from "@playwright/test";

/**
 * 用户旅程 E2E(C2,20261009 立项):跑在本地 docker 平台(localhost:3000)。
 * global-setup 经 docker exec 注入邀请码(平台开启邀请码注册)。
 * 运行:npx playwright test(平台需已 compose up)
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  retries: 0,
  workers: 1, // 旅程有状态(登录/任务),串行最稳
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    locale: "zh-CN",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  globalSetup: "./e2e/global-setup.ts",
});
