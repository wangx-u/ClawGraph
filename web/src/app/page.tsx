import Link from "next/link";
import { getDashboardBundle } from "@/lib/data-source";
import { guidedFlows } from "@/lib/navigation";
import { formatCompact } from "@/lib/utils";
import { FlowSteps } from "@/components/dashboard/flow-steps";
import { MetricCard } from "@/components/dashboard/metric-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";

export default async function OverviewPage() {
  const {
    bundle: { healthMatrix, opportunities, overviewMetrics, risks },
    meta
  } = await getDashboardBundle();

  return (
    <div className="space-y-6">
      <PageHeader
        title="总览"
        description="围绕证据健康度、训练资产产出、切片替代机会和回流风险的学习数据驾驶舱。"
        primaryAction={<Button href="/flows/connect-runtime" variant="primary">开始引导流程</Button>}
        secondaryAction={<Button href="/datasets" variant="secondary">查看导出摘要</Button>}
      />

      <Card eyebrow="数据源" title="当前读取模式">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-sm text-[color:var(--text-muted)]">{meta.statusText}</div>
            <div className="mt-2 mono text-xs text-[color:var(--text-soft)]">
              mode={meta.configuredMode} · resolved={meta.resolvedMode}
            </div>
          </div>
          <Badge tone={meta.status === "prod" ? "success" : meta.status === "prod-fallback" ? "warning" : "info"}>
            {meta.status}
          </Badge>
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
        {overviewMetrics.map((metric) => (
          <MetricCard key={metric.label} metric={metric} />
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <Card eyebrow="健康矩阵" title="系统与治理健康度" strong>
          <div className="grid gap-3 md:grid-cols-2">
            {healthMatrix.map((item) => (
              <div className="panel-soft rounded-[1.1rem] p-4" key={item.label}>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-sm font-medium">{item.label}</div>
                    <p className="mt-2 text-xs leading-5 text-[color:var(--text-muted)]">{item.detail}</p>
                  </div>
                  <Badge tone={item.tone}>{item.score}</Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card eyebrow="机会面板" title="切片替代机会">
          <div className="space-y-3">
            {opportunities.map((item) => (
              <div className="tech-highlight rounded-[1.1rem] p-4" key={item.sliceId}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="mono text-xs text-[color:var(--text-soft)]">{item.sliceId}</div>
                    <div className="mt-1 text-lg font-medium">{item.opportunity}</div>
                    <div className="mt-2 text-sm text-[color:var(--text-muted)]">{item.reason}</div>
                  </div>
                  <Button href={item.href} variant="secondary">打开覆盖策略</Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Card eyebrow="风险流" title="近期决策阻塞项">
          <div className="space-y-3">
            {risks.map((risk) => (
              <Link className="panel-soft block rounded-[1.1rem] p-4 transition hover:-translate-y-[1px]" href={risk.href} key={risk.id}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium">{risk.label}</div>
                    <p className="mt-2 text-sm text-[color:var(--text-muted)]">{risk.detail}</p>
                  </div>
                  <Badge tone={risk.tone}>{risk.tone}</Badge>
                </div>
              </Link>
            ))}
          </div>
        </Card>

        <Card eyebrow="业务视角" title="价值叙事">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">首次回放耗时</div>
              <div className="mt-3 text-2xl font-semibold">18 分钟</div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">会话转数据集产出率</div>
              <div className="mt-3 text-2xl font-semibold">62%</div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">可替代切片数</div>
              <div className="mt-3 text-2xl font-semibold">2 / 7</div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">预估月度降本空间</div>
              <div className="mt-3 text-2xl font-semibold">{formatCompact(240000)}/月</div>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <Card eyebrow="快捷入口" title="从你真正要做的任务开始">
          <div className="grid gap-3 md:grid-cols-2">
            {guidedFlows.map((flow) => (
              <Link className="panel-soft rounded-[1.2rem] p-5 transition hover:-translate-y-[1px] hover:border-sky-200" href={`/flows/${flow.id}`} key={flow.id}>
                <div className="text-lg font-medium">{flow.title}</div>
                <p className="mt-2 text-sm leading-6 text-[color:var(--text-muted)]">{flow.description}</p>
              </Link>
            ))}
          </div>
        </Card>
        <FlowSteps flow={guidedFlows[0]} />
      </div>
    </div>
  );
}
