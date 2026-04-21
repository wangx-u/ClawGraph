import { getDashboardBundle } from "@/lib/data-source";
import { getEvalExecution, getModelCandidate } from "@/lib/training-registry";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";

export default async function TrainingEvaluationDetailPage({
  params
}: {
  params: Promise<{ executionId: string }>;
}) {
  const { executionId } = await params;
  const { bundle } = await getDashboardBundle();
  const execution = getEvalExecution(bundle, executionId);

  if (!execution) {
    return (
      <EmptyState
        actionHref="/training"
        actionLabel="返回训练资产"
        description="当前还没有可查看的评测执行。先让候选模型在冻结套件上跑一轮离线评测。"
        title="评测执行不存在"
      />
    );
  }

  const candidate = getModelCandidate(bundle, execution.candidateModelId);

  return (
    <div className="space-y-6">
      <PageHeader
        title={execution.title}
        description="查看一次候选模型评测执行的套件、评分器、scorecard 和 promotion 关联。"
        primaryAction={<Button href="/training" variant="primary">返回训练资产</Button>}
        secondaryAction={candidate ? <Button href={`/training/candidates/${candidate.id}`} variant="secondary">查看候选模型</Button> : undefined}
      />

      <Card eyebrow="执行摘要" title={execution.evalSuiteTitle ?? execution.evalSuiteId} strong>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="tech-highlight rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">Scorecard</div>
            <div className="mt-3">
              <Badge tone={genericStatusTone(execution.scorecardVerdict ?? "completed")}>
                {genericStatusLabel(execution.scorecardVerdict ?? "completed")}
              </Badge>
            </div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">评分器</div>
            <div className="mt-3 text-lg font-semibold">{execution.graderName}</div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">样本数</div>
            <div className="mt-3 text-lg font-semibold">{execution.caseCount}</div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">放量建议</div>
            <div className="mt-3 text-lg font-semibold">{execution.promotionStage ?? "待补充"}</div>
          </div>
        </div>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card eyebrow="比较对象" title="候选 vs 基线">
          <div className="space-y-3 text-sm text-[color:var(--text-muted)]">
            <div className="panel-soft rounded-2xl p-4">候选模型：{execution.candidateModel ?? execution.candidateTitle ?? execution.candidateModelId}</div>
            <div className="panel-soft rounded-2xl p-4">基线模型：{execution.baselineModel ?? "待补充"}</div>
            <div className="panel-soft rounded-2xl p-4">指标摘要：{execution.metricsSummary ?? "待补充"}</div>
            <div className="panel-soft rounded-2xl p-4">业务判断：这轮验证已经产出可用于替换决策的结果。</div>
            <details className="panel-soft rounded-2xl p-4">
              <summary className="cursor-pointer text-sm font-medium text-[color:var(--text)]">查看技术明细</summary>
              <div className="mt-3 grid gap-2 text-xs text-[color:var(--text-soft)]">
                <div>配置清单：<span className="mono">{execution.manifestPath}</span></div>
                <div>评测执行 ID：<span className="mono">{execution.id}</span></div>
              </div>
            </details>
          </div>
        </Card>

        <Card eyebrow="决策关联" title="它回写了哪些治理对象">
          <div className="space-y-3 text-sm text-[color:var(--text-muted)]">
            <div className="panel-soft rounded-2xl p-4">评测套件：{execution.evalSuiteTitle ?? execution.evalSuiteId}</div>
            <div className="panel-soft rounded-2xl p-4">评分结论：{execution.scorecardVerdict ?? "待补充"}</div>
            <div className="panel-soft rounded-2xl p-4">放量决策：{execution.promotionDecision ? `${execution.promotionDecision} · ${execution.promotionStage ?? "待补充"}` : "未生成"}</div>
            <details className="panel-soft rounded-2xl p-4">
              <summary className="cursor-pointer text-sm font-medium text-[color:var(--text)]">查看技术明细</summary>
              <div className="mt-3 grid gap-2 text-xs text-[color:var(--text-soft)]">
                <div>评分卡：<span className="mono">{execution.scorecardId ?? "待补充"}</span></div>
                <div>Promotion：<span className="mono">{execution.promotionDecisionId ?? "未生成"}</span></div>
              </div>
            </details>
            {execution.evalSuiteId ? (
              <Button href={`/evaluation/${execution.evalSuiteId}`} variant="secondary">打开评测套件</Button>
            ) : null}
          </div>
        </Card>
      </div>
    </div>
  );
}
