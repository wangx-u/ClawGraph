"use client";

import { usePathname } from "next/navigation";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

function getRailContent(pathname: string) {
  if (pathname.startsWith("/access")) {
    return {
      title: "接入建议",
      points: ["先只切到 proxy，确认真实请求已被捕获", "当回放关联不稳定时，再补 durable id", "只在关键 route、retry、fallback 节点补语义事件"],
      cta: { label: "打开接入流程", href: "/flows/connect-runtime" }
    };
  }
  if (pathname.startsWith("/sessions")) {
    return {
      title: "运行分诊建议",
      points: ["优先处理 open span 和失败运行", "缺少 task_instance_key 的运行先进入数据准备", "关键分支主要靠推断恢复时，优先补结构语义"],
      cta: { label: "排查失败流程", href: "/flows/investigate-failure" }
    };
  }
  if (pathname.startsWith("/supervision")) {
    return {
      title: "数据准备建议",
      points: ["先补基础任务标签和 verifier", "优先写 versioned artifact，而不是临时裸标签", "让自动判断和人工 override 都可追溯"],
      cta: { label: "打开数据集流程", href: "/flows/build-dataset" }
    };
  }
  if (pathname.startsWith("/curation")) {
    return {
      title: "数据筛选标准",
      points: ["冻结前先清空低置信样本", "严格遵守 cluster 配额和 holdout", "训练 cohort 和评测 cohort 必须分开冻结"],
      cta: { label: "前往数据集", href: "/datasets" }
    };
  }
  if (pathname.startsWith("/datasets")) {
    return {
      title: "导出指引",
      points: ["正式写出 JSONL 前先做 dry-run", "看到 blocker 就直接回到上游处理", "把 manifest 和 snapshot 当成正式资产维护"],
      cta: { label: "验证切片替代", href: "/flows/validate-slice" }
    };
  }
  if (pathname.startsWith("/evaluation") || pathname.startsWith("/coverage")) {
    return {
      title: "替代纪律",
      points: ["所有结论必须按 slice 成立，不能只看全局平均", "rollback 条件必须明确写出", "所有回归都应进入 feedback 闭环"],
      cta: { label: "查看回流队列", href: "/feedback" }
    };
  }
  return {
    title: "控制台引导",
    points: ["先确认真实流量，再做数据准备和监督", "训练数据导出前必须经过筛选和复核", "评测和回流共同构成完整闭环"],
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
