import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "agentplatform",
  description: "AI 助手开发与分发平台",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
