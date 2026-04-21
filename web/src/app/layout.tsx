import type { Metadata } from "next";
import type { ReactNode } from "react";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import "@/app/globals.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "ClawGraph 控制面",
  description: "把真实 agent 运行沉淀为训练数据、验证资产和替代建议的控制面。"
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <DashboardShell>{children}</DashboardShell>
      </body>
    </html>
  );
}
