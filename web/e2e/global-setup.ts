import { execSync } from "node:child_process";
import fs from "node:fs";

/**
 * E2E 全局准备:向本地 docker 平台注入一枚邀请码(平台开启邀请码注册)。
 * 写入 e2e/.state.json 供测试读取(invite/email/password)。
 */
export default async function globalSetup() {
  const invite = `e2e-${Date.now().toString(36)}`;
  const pg = "agentplatform-pg-1";
  execSync(
    `docker exec ${pg} psql -U agentplatform -d agentplatform -c ` +
      `"INSERT INTO invite_codes (id, code, max_uses, used_count, expires_at, disabled) ` +
      `VALUES (gen_random_uuid(), '${invite}', 5, 0, now() + interval '1 day', false)"`,
    { stdio: "pipe" },
  );
  const state = {
    invite,
    email: `e2e-${Date.now().toString(36)}@qq.com`,
    password: "e2e-password-123",
  };
  fs.writeFileSync(`${__dirname}/.state.json`, JSON.stringify(state));
}
