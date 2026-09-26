import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

// 前端渲染器测试(2026-09-26 表单三连崩教训:renderers 曾零测试,
// tsc 类型对≠行为对)。运行: npm test / npm run test:run
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["components/**/*.test.tsx", "lib/**/*.test.ts"],
    globals: true,
  },
  resolve: {
    alias: { "@": path.resolve(__dirname) },
  },
});
