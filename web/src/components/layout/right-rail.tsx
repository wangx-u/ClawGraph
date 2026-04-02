"use client";

import { usePathname } from "next/navigation";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

function getRailContent(pathname: string) {
  if (pathname.startsWith("/access")) {
    return {
      title: "接入建议",
      points: ["先从透明代理开始，不先改业务逻辑", "当 replay 关联变差时，再补稳定 Header", "只有在高价值路由和 retry 上再补语义事件"],
      cta: { label: "打开接入流程", href: "/flows/connect-runtime" }
    };
  }
  if (pathname.startsWith("/sessions")) {
    return {
      title: "证据缺口分诊",
      points: ["优先检查缺失的 task_instance_key", "导出前先处理 open span", "declared branch 覆盖率过低时应优先补结构"],
      cta: { label: "排查失败流程", href: "/flows/investigate-failure" }
    };
  }
  if (pathname.startsWith("/supervision")) {
    return {
      title: "监督下一步",
      points: ["先补 e1 annotation", "优先使用 active artifact，而不是临时裸标签", "每次写入都明确 producer 与 version"],
      cta: { label: "打开数据集流程", href: "/flows/build-dataset" }
    };
  }
  if (pathname.startsWith("/curation")) {
    return {
      title: "策展标准",
      points: ["冻结前先处理低置信样本", "严格遵守 cluster 配额与 holdout", "训练 cohort 与评测 cohort 必须分开冻结"],
      cta: { label: "前往数据集", href: "/datasets" }
    };
  }
  if (pathname.startsWith("/datasets")) {
    return {
      title: "导出指引",
      points: ["正式写出 JSONL 前先做 dry-run", "利用 blocker 直接回跳上游模块", "把 manifest 当成一等资产维护"],
      cta: { label: "验证切片替代", href: "/flows/validate-slice" }
    };
  }
  if (pathname.startsWith("/evaluation") || pathname.startsWith("/coverage")) {
    return {
      title: "替代纪律",
      points: ["所有结论必须按 slice 成立，不能看全局平均", "rollback 条件必须明确写出", "所有回归都应进入 feedback 闭环"],
      cta: { label: "查看回流队列", href: "/feedback" }
    };
  }
  return {
    title: "控制台引导",
    points: ["先看证据采集，再做监督与策展", "导出前必须经过 cohort 与 readiness", "评测和回流共同构成闭环"],
    cta: { label: "开始引导流程", href: "/flows/connect-runtime" }
  };
}

export function RightRail() {
  const pathname = usePathname();
  const content = getRailContent(pathname);

  return (
    <aside className="hidden w-[320px] shrink-0 2xl:block">
      <div className="sticky top-4 space-y-4">
        <Card eyebrow="上下文侧栏" title={content.title} strong>
          <div className="space-y-3">
            {content.points.map((point) => (
              <div className="flex gap-3" key={point}>
                <div className="mt-2 h-2 w-2 rounded-full bg-[color:var(--accent)]" />
                <p className="text-sm leading-6 text-[color:var(--text-muted)]">{point}</p>
              </div>
            ))}
          </div>
          <Button className="mt-5 w-full" href={content.cta.href} variant="primary">
            {content.cta.label}
          </Button>
        </Card>
      </div>
    </aside>
  );
}
