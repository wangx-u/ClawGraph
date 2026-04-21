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
      points: ["先补基础任务标签和 verifier", "优先写可追溯的判断记录，而不是临时裸标签", "让自动判断和人工覆盖都能回查来源"],
      cta: { label: "打开数据集流程", href: "/flows/build-dataset" }
    };
  }
  if (pathname.startsWith("/curation")) {
    return {
      title: "数据筛选标准",
      points: ["冻结前先清空低置信样本", "严格遵守切片配额和保留集规则", "训练批次和评测批次必须分开冻结"],
      cta: { label: "前往数据集", href: "/datasets" }
    };
  }
  if (pathname.startsWith("/datasets")) {
    return {
      title: "导出指引",
      points: ["正式写出 JSONL 前先做 dry-run", "看到 blocker 就直接回到上游处理", "把导出清单和数据快照当成正式资产维护"],
      cta: { label: "验证切片替代", href: "/flows/validate-slice" }
    };
  }
  if (pathname.startsWith("/training")) {
    return {
      title: "模型接替纪律",
      points: ["候选一旦产出，就尽快送进固定评测", "评测完成后必须形成保留、放量或回退决策", "交接包就绪后立刻进入上线控制面，确认审批和 router ack"],
      cta: { label: "打开上线控制面", href: "/coverage" }
    };
  }
  if (pathname.startsWith("/evaluation") || pathname.startsWith("/coverage")) {
    return {
      title: "上线守则",
      points: ["切流范围和流量比例要明确锁定", "审批人、router ack 和监控来源缺一不可", "所有 rollback 条件都必须绑定值班责任人和回流闭环"],
      cta: { label: "查看回流队列", href: "/feedback" }
    };
  }
  return {
    title: "使用建议",
    points: ["先验证真实流量和数据闭环，再扩展训练与替代流程", "优先围绕当前阻塞和下一步动作推进，而不是同时展开所有模块", "训练执行由外部系统负责，ClawGraph 负责数据、评测和替代建议"],
    cta: { label: "打开上手流程", href: "/flows/connect-runtime" }
  };
}

export function RightRail() {
  const pathname = usePathname();
  const content = getRailContent(pathname);

  return (
    <aside className="hidden w-[300px] shrink-0 xl:block 2xl:w-[320px]">
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
