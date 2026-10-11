import { defineConfig } from "@playwright/test";

/**
 * 用户旅程 E2E(C2,20261009 立项):跑在本地平台(localhost:3000)。
 * global-setup 注入邀请码(优先 docker exec,无 docker 回退本机 psql)。
 * 平台启动需带:e2e 认证形态(邮箱验证开)+ 假 SMTP + 关限频,即
 *   EMAIL_VERIFICATION_REQUIRED=true NOTIFY_SMTP_HOST=smtp.example.com \
 *   NOTIFY_SMTP_PORT=25 E2E_NO_RATELIMIT=true
 * 运行:npx playwright test
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
