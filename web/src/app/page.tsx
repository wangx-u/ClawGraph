import Link from "next/link";
import { getDashboardBundle } from "@/lib/data-source";
import { guidedFlows } from "@/lib/navigation";
import { buildPipelineStageSummaries, pickPriorityPipelineStage } from "@/lib/pipeline";
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
    bundle,
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
  const pipelineStages = buildPipelineStageSummaries(bundle);
  const priorityStage = pickPriorityPipelineStage(pipelineStages);
  const blockerStageCount = pipelineStages.filter((stage) => stage.blockerCount > 0).length;
  const activeStageCount = pipelineStages.filter((stage) => stage.count > 0).length;
  const datasetStage = pipelineStages.find((stage) => stage.id === "dataset");
  const validationStage = pipelineStages.find((stage) => stage.id === "validation");
  const feedbackStage = pipelineStages.find((stage) => stage.id === "feedback");
  const stageFlowMap = {
    access: "connect-runtime",
    trajectory: "investigate-failure",
    judge: "build-dataset",
    curation: "build-dataset",
    dataset: "build-dataset",
    training: "operate-training",
    validation: "validate-slice",
    launch: "validate-slice",
    feedback: "review-feedback"
  } as const;
  const priorityFlow =
    guidedFlows.find((flow) => flow.id === stageFlowMap[priorityStage.id]) ?? guidedFlows[0];
  const latestSessionLabel =
    ingestSummary?.latestSessionTitle ?? ingestSummary?.latestRunTitle ?? ingestSummary?.latestSessionId ?? "-";
  const latestSessionId = ingestSummary?.latestSessionId ?? "-";

  return (
    <div className="space-y-6">
      <PageHeader
        title="闭环控制台"
        description="把 proxy 接入、轨迹判断、自动筛选、数据集生产、训练回写、验证和上线接替串成一条可追溯流程，先看哪里卡住，再决定下一步动作。"
        primaryAction={<Button href={priorityStage.href} variant="primary">{`继续第 ${priorityStage.step} 步`}</Button>}
        secondaryAction={<Button href={`/flows/${priorityFlow.id}`} variant="secondary">{priorityFlow.title}</Button>}
      />

      <div className="grid gap-6 xl:grid-cols-[1.12fr_0.88fr]">
        <Card
          action={<Button href={priorityStage.href} variant="primary">{priorityStage.actionLabel}</Button>}
          eyebrow="当前推进点"
          title={`第 ${priorityStage.step} 步 · ${priorityStage.title}`}
          strong
        >
          <p className="max-w-3xl text-sm leading-6 text-[color:var(--text-muted)]">{priorityStage.description}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className="tech-highlight rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">当前规模</div>
              <div className="mt-3 text-2xl font-semibold">{priorityStage.countLabel}</div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">待处理阻塞</div>
              <div className="mt-3 text-2xl font-semibold">{priorityStage.blockerCount}</div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">最近活动</div>
              <div className="mt-3 text-lg font-semibold">{ingestSummary?.latestActivity ?? "-"}</div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">数据源</div>
              <div className="mt-3 flex items-center gap-2">
                <div className="text-lg font-semibold">{meta.status}</div>
                <Badge tone={meta.status === "prod" ? "success" : meta.status === "prod-fallback" ? "warning" : "info"}>
                  已连接
                </Badge>
              </div>
            </div>
          </div>
          <div className="tech-highlight mt-4 rounded-[1.2rem] p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">当前说明</div>
            <div className="mt-2 text-base font-medium">{priorityStage.detail}</div>
            <p className="mt-2 text-sm leading-6 text-[color:var(--text-muted)]">
              推荐流程：{priorityFlow.description}
            </p>
          </div>
        </Card>

        <div className="space-y-6">
          <Card eyebrow="控制面摘要" title="全链路现在进行到哪">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="panel-soft rounded-[1.1rem] p-4">
                <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">已激活阶段</div>
                <div className="mt-3 text-2xl font-semibold">{activeStageCount} / 9</div>
                <div className="mt-2 text-xs text-[color:var(--text-muted)]">已经产生真实数据或下游资产的阶段数。</div>
              </div>
              <div className="panel-soft rounded-[1.1rem] p-4">
                <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">阻塞阶段</div>
                <div className="mt-3 text-2xl font-semibold">{blockerStageCount}</div>
                <div className="mt-2 text-xs text-[color:var(--text-muted)]">这些阶段还需要人工决策或补齐资产。</div>
              </div>
              <div className="panel-soft rounded-[1.1rem] p-4">
                <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">已冻结快照</div>
                <div className="mt-3 text-2xl font-semibold">{datasetStage?.count ?? 0}</div>
                <div className="mt-2 text-xs text-[color:var(--text-muted)]">已进入训练或待训练的数据集资产。</div>
              </div>
              <div className="panel-soft rounded-[1.1rem] p-4">
                <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">待处理回流</div>
                <div className="mt-3 text-2xl font-semibold">{feedbackStage?.blockerCount ?? 0}</div>
                <div className="mt-2 text-xs text-[color:var(--text-muted)]">仍未闭环回到下一轮的数据问题。</div>
              </div>
            </div>
          </Card>

          <Card eyebrow="当前阻塞" title="最需要优先决策的事项" strong>
            <div className="space-y-3">
              {risks.length ? (
                risks.slice(0, 3).map((risk) => (
                  <Link
                    className="panel-soft block rounded-[1.1rem] p-4 transition hover:-translate-y-[1px]"
                    href={risk.href}
                    key={risk.id}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-medium">{risk.label}</div>
                        <p className="mt-2 text-sm text-[color:var(--text-muted)]">{risk.detail}</p>
                      </div>
                      <Badge tone={risk.tone}>{risk.tone}</Badge>
                    </div>
                  </Link>
                ))
              ) : (
                <div className="panel-soft rounded-[1.1rem] p-4 text-sm text-[color:var(--text-muted)]">
                  当前没有高优先级阻塞，继续推进 {priorityStage.title} 即可。
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
        {overviewMetrics.map((metric) => (
          <MetricCard key={metric.label} metric={metric} />
        ))}
      </div>

      <WorkflowBoard lanes={workflowLanes ?? []} runs={workflowRuns ?? []} />

      <Card eyebrow="数据源" title="联调状态与最近活动" strong>
        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="text-sm text-[color:var(--text-muted)]">{meta.statusText}</div>
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
              <div className="mt-3 text-2xl font-semibold">{validationStage?.count ?? ingestSummary?.evaluationAssetCount ?? 0}</div>
              <div className="mt-2 text-xs text-[color:var(--text-muted)]">已经冻结并可用于对比 candidate / baseline 的验证套件。</div>
            </div>
          </div>
        </Card>

        <Card eyebrow="平台边界" title="当前交付方式">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">当前可直接承接</div>
              <div className="mt-3 space-y-2 text-sm text-[color:var(--text-muted)]">
                <p>真实流量接入、回放、自动判断、人工筛选、快照导出和候选模型验证。</p>
                <p>训练资产、评测结果和替代建议已经能串成同一条可追溯链路。</p>
              </div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">当前责任边界</div>
              <div className="mt-3 space-y-2 text-sm text-[color:var(--text-muted)]">
                <p>训练执行仍由外部系统负责，当前 Web 主要展示训练血缘、评测和接替决策。</p>
                <p>首方 HTTP API 已可联调，但安全、权限和服务化能力仍在继续补强。</p>
              </div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">生产发布前补齐</div>
              <div className="mt-3 space-y-2 text-sm text-[color:var(--text-muted)]">
                <p>安全鉴权、审计身份绑定、性能与滥用测试，以及更稳定的远端服务形态。</p>
                <p>这些能力补齐后，整条闭环才适合进一步对外扩展。</p>
              </div>
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
