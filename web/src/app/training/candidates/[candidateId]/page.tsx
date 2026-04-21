import { getDashboardBundle } from "@/lib/data-source";
import {
  getModelCandidate,
  getTrainingRequest,
  relatedExecutionsForCandidate,
  relatedHandoffsForCandidate
} from "@/lib/training-registry";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";

export default async function CandidateDetailPage({
  params
}: {
  params: Promise<{ candidateId: string }>;
}) {
  const { candidateId } = await params;
  const { bundle } = await getDashboardBundle();
  const candidate = getModelCandidate(bundle, candidateId);

  if (!candidate) {
    return (
        <EmptyState
          actionHref="/training"
          actionLabel="返回训练资产"
          description="当前还没有可查看的候选模型。先提交训练请求并生成候选模型配置清单。"
          title="候选模型不存在"
        />
    );
  }

  const request = getTrainingRequest(bundle, candidate.trainingRequestId);
  const executions = relatedExecutionsForCandidate(bundle, candidate.id);
  const handoffs = relatedHandoffsForCandidate(bundle, candidate.id);

  return (
    <div className="space-y-6">
      <PageHeader
        title={candidate.title}
        description="查看一个候选模型从训练请求、冻结快照，到评测执行和交接包的完整血缘。"
        primaryAction={<Button href="/training" variant="primary">返回训练资产</Button>}
        secondaryAction={request ? <Button href={`/training/requests/${request.id}`} variant="secondary">查看上游请求</Button> : undefined}
      />

      <Card eyebrow="候选摘要" title={candidate.candidateModel} strong>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="tech-highlight rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">当前阶段</div>
            <div className="mt-3"><Badge tone={genericStatusTone(candidate.status ?? "active")}>{genericStatusLabel(candidate.status ?? "active")}</Badge></div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">来源请求</div>
            <div className="mt-3 text-lg font-semibold">{candidate.trainingRequestTitle ?? candidate.trainingRequestId}</div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">评测执行</div>
            <div className="mt-3 text-lg font-semibold">{executions.length}</div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">交接包</div>
            <div className="mt-3 text-lg font-semibold">{handoffs.length}</div>
          </div>
        </div>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card eyebrow="产物信息" title="模型和路径">
          <div className="space-y-3 text-sm text-[color:var(--text-muted)]">
            <div className="panel-soft rounded-2xl p-4">输出快照：{candidate.datasetSnapshotTitle ?? candidate.datasetSnapshotId ?? "未绑定"}</div>
            <div className="panel-soft rounded-2xl p-4">输出状态：{candidate.publishedModelPath ? "已发布，可进入替换评估" : candidate.samplerPath ? "已生成采样器，可进入离线评测" : candidate.checkpointPath ? "已生成训练 Checkpoint" : "训练结果待回写"}</div>
            <div className="panel-soft rounded-2xl p-4">业务判断：这个候选已经和上游快照建立血缘，可以继续进入评测或交接。</div>
            <details className="panel-soft rounded-2xl p-4">
              <summary className="cursor-pointer text-sm font-medium text-[color:var(--text)]">查看技术明细</summary>
              <div className="mt-3 grid gap-2 text-xs text-[color:var(--text-soft)]">
                <div>Checkpoint：{candidate.checkpointPath ?? "待补充"}</div>
                <div>Sampler：{candidate.samplerPath ?? "待补充"}</div>
                <div>Published：{candidate.publishedModelPath ?? "待补充"}</div>
                <div>配置清单：<span className="mono">{candidate.manifestPath}</span></div>
              </div>
            </details>
          </div>
        </Card>

        <Card eyebrow="下游使用" title="是否已经验证并交接">
          <div className="space-y-3">
            {executions.map((execution) => (
              <div className="panel-soft rounded-2xl p-4" key={execution.id}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium">{execution.title}</div>
                    <div className="mt-2 text-sm text-[color:var(--text-muted)]">{execution.metricsSummary ?? execution.summary}</div>
                  </div>
                  <Button href={`/training/evaluations/${execution.id}`} variant="ghost">打开评测</Button>
                </div>
              </div>
            ))}
            {handoffs.map((handoff) => (
              <div className="tech-highlight rounded-2xl p-4" key={handoff.id}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium">{handoff.title}</div>
                    <div className="mt-2 text-sm text-[color:var(--text-muted)]">{handoff.summary}</div>
                  </div>
                  <Button href={`/training/handoffs/${handoff.id}`} variant="ghost">打开交接</Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
