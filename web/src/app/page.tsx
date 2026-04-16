import Link from "next/link";
import { getDashboardBundle } from "@/lib/data-source";
import { guidedFlows } from "@/lib/navigation";
import { shortId } from "@/lib/presenters";
import { FlowSteps } from "@/components/dashboard/flow-steps";
import { MetricCard } from "@/components/dashboard/metric-card";
import { WorkflowBoard } from "@/components/dashboard/workflow-board";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";

export default async function OverviewPage() {
  const {
    bundle: {
      healthMatrix,
      ingestSummary,
      opportunities,
      overviewMetrics,
      risks,
      workflowLanes,
      workflowRuns
    },
    meta
  } = await getDashboardBundle();
  const latestSessionLabel =
    ingestSummary?.latestSessionTitle ?? ingestSummary?.latestRunTitle ?? ingestSummary?.latestSessionId ?? "-";
  const latestSessionId = ingestSummary?.latestSessionId ?? "-";

  return (
    <div className="space-y-6">
      <PageHeader
        title="总览"
        description="把真实 agent 流量接进来以后，按“采集、数据准备、人工复核、导出与评估”的顺序推进完整数据闭环。"
        primaryAction={<Button href="/flows/connect-runtime" variant="primary">开始引导流程</Button>}
        secondaryAction={<Button href="/sessions" variant="secondary">打开最近运行</Button>}
      />

      <Card eyebrow="数据源" title="当前联调状态" strong>
        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-sm text-[color:var(--text-muted)]">{meta.statusText}</div>
            </div>
            <Badge tone={meta.status === "prod" ? "success" : meta.status === "prod-fallback" ? "warning" : "info"}>
              {meta.status}
            </Badge>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">最近活动</div>
              <div className="mt-3 text-lg font-semibold">{ingestSummary?.latestActivity ?? "-"}</div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">最近任务</div>
              <div className="mt-3 text-lg font-semibold">{latestSessionLabel}</div>
              {latestSessionLabel !== latestSessionId ? (
                <div className="mt-2 mono text-xs text-[color:var(--text-soft)]">会话 {shortId(latestSessionId)}</div>
              ) : null}
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">最近请求</div>
              <div className="mt-3 text-lg font-semibold">{ingestSummary?.requestCount ?? 0}</div>
            </div>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
        {overviewMetrics.map((metric) => (
          <MetricCard key={metric.label} metric={metric} />
        ))}
      </div>

      <WorkflowBoard lanes={workflowLanes ?? []} runs={workflowRuns ?? []} />

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
                    <div className="text-sm font-medium">{item.sliceLabel ?? item.sliceId}</div>
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

        <Card eyebrow="接入质量" title="当前联调进度">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">请求归属清晰度</div>
              <div className="mt-3 text-2xl font-semibold">{ingestSummary?.identityCoverage ?? "-"}</div>
              <div className="mt-2 text-xs text-[color:var(--text-muted)]">能否稳定归到同一 session / run。</div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">任务标签覆盖率</div>
              <div className="mt-3 text-2xl font-semibold">{ingestSummary?.taskCoverage ?? ingestSummary?.semanticCoverage ?? "-"}</div>
              <div className="mt-2 text-xs text-[color:var(--text-muted)]">能否稳定识别任务族、任务类型和实例键。</div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">决策语义覆盖率</div>
              <div className="mt-3 text-2xl font-semibold">{ingestSummary?.decisionCoverage ?? ingestSummary?.semanticCoverage ?? "-"}</div>
              <div className="mt-2 text-xs text-[color:var(--text-muted)]">是否已经补到 retry、fallback、route、task_completed 等关键节点。</div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">待补基础标签</div>
              <div className="mt-3 text-2xl font-semibold">{ingestSummary?.needsAnnotationRuns ?? 0}</div>
              <div className="mt-2 text-xs text-[color:var(--text-muted)]">这些运行还不能直接进入数据池。</div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">已生成验证资产</div>
              <div className="mt-3 text-2xl font-semibold">{ingestSummary?.evaluationAssetCount ?? 0}</div>
              <div className="mt-2 text-xs text-[color:var(--text-muted)]">已经冻结并可用于对比 candidate / baseline 的验证套件。</div>
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
