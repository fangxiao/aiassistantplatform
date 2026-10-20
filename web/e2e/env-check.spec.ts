import { test, expect } from "@playwright/test";
import { loginViaToken, state } from "./helpers";

test("cloud-after-deploy", async ({ page }) => {
  const s = state();
  await page.addInitScript(
    ([t, u]) => {
      localStorage.setItem("agentplatform_token", t!);
      localStorage.setItem("agentplatform_user", u!);
    },
    [s.token, JSON.stringify({ email: s.email, role: "user", personas: ["developer"] })],
  );
  await page.goto("https://agent.ailearning.top/");
  await expect(page.getByText("会话中心").first()).toBeVisible({ timeout: 30_000 });
  console.log("CLOUD 验证线出现次数:", await page.getByText("双环境验证线").count());
  await page.screenshot({ path: "/tmp/env-cloud-after.png" });
});
