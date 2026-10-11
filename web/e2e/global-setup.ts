import { execSync } from "node:child_process";
import fs from "node:fs";

/**
 * E2E 全局准备:向本地平台注入一枚邀请码(平台开启邀请码注册)。
 * 写入 e2e/.state.json 供测试读取(invite/email/password)。
 *
 * 默认走 docker compose 平台;无 docker 时回退本机 psql(原生 PG 开发环境,
 * 连接参数与 .env 的 DATABASE_URL 一致)。
 */
function runPsql(sql: string): void {
  try {
    execSync(
      `docker exec agentplatform-pg-1 psql -U agentplatform -d agentplatform -c "${sql}"`,
      { stdio: "pipe" },
    );
  } catch {
    execSync(`psql -h localhost -U agentplatform -d agentplatform -c "${sql}"`, {
      stdio: "pipe",
    });
  }
}

export default async function globalSetup() {
  const invite = `e2e-${Date.now().toString(36)}`;
  runPsql(
    `INSERT INTO invite_codes (id, code, max_uses, used_count, expires_at, disabled) ` +
      `VALUES (gen_random_uuid(), '${invite}', 5, 0, now() + interval '1 day', false)`,
  );
  const state = {
    invite,
    email: `e2e-${Date.now().toString(36)}@qq.com`,
    password: "e2e-password-123",
  };
  fs.writeFileSync(`${__dirname}/.state.json`, JSON.stringify(state));
}
