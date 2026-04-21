import { getDashboardBundle } from "@/lib/data-source";
import {
  getTrainingRequest,
  relatedCandidatesForRequest,
  relatedExecutionsForRequest,
  relatedHandoffsForRequest
} from "@/lib/training-registry";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";

export default async function TrainingRequestDetailPage({
  params
}: {
  params: Promise<{ requestId: string }>;
}) {
  const { requestId } = await params;
  const { bundle } = await getDashboardBundle();
  const request = getTrainingRequest(bundle, requestId);

  if (!request) {
    return (
        <EmptyState
          actionHref="/training"
          actionLabel="返回训练资产"
          description="当前还没有可查看的训练请求。先从数据快照生成一份训练请求配置清单。"
          title="训练请求不存在"
        />
    );
  }

  const candidates = relatedCandidatesForRequest(bundle, request.id);
  const executions = relatedExecutionsForRequest(bundle, request.id);
  const handoffs = relatedHandoffsForRequest(bundle, request.id);

  return (
    <div className="space-y-6">
      <PageHeader
        title={request.title}
        description="查看一个训练请求如何从冻结快照进入训练，并沿着候选、评测和交接继续向下游扩展。"
        primaryAction={<Button href="/training" variant="primary">返回训练资产</Button>}
        secondaryAction={request.datasetSnapshotId ? <Button href={`/datasets/${request.datasetSnapshotId}`} variant="secondary">打开数据快照</Button> : undefined}
      />

      <Card eyebrow="请求摘要" title={request.recipeName} strong>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="tech-highlight rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">当前状态</div>
            <div className="mt-3"><Badge tone={genericStatusTone(request.status)}>{genericStatusLabel(request.status)}</Badge></div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">基座模型</div>
            <div className="mt-3 text-lg font-semibold">{request.baseModel}</div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">候选数</div>
            <div className="mt-3 text-lg font-semibold">{candidates.length}</div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">最近更新时间</div>
            <div className="mt-3 text-lg font-semibold">{request.createdAt}</div>
          </div>
        </div>
        <div className="mt-4 rounded-2xl bg-white/70 px-4 py-3 text-sm text-[color:var(--text-muted)]">
          {request.summary}
        </div>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card eyebrow="上游输入" title="这份请求绑定了什么">
          <div className="space-y-3 text-sm text-[color:var(--text-muted)]">
            <div className="panel-soft rounded-2xl p-4">数据快照：{request.datasetSnapshotTitle ?? request.datasetSnapshotId ?? "未绑定"}</div>
            <div className="panel-soft rounded-2xl p-4">评测套件：{request.evalSuiteTitle ?? request.evalSuiteId ?? "未绑定"}</div>
            <div className="panel-soft rounded-2xl p-4">训练方式：{request.recipeFamily.toUpperCase()} · {request.recipeName}</div>
            <div className="panel-soft rounded-2xl p-4">当前判断：这份请求已经从冻结快照出发，可继续产出候选模型。</div>
            <details className="panel-soft rounded-2xl p-4">
              <summary className="cursor-pointer text-sm font-medium text-[color:var(--text)]">查看技术明细</summary>
              <div className="mt-3 grid gap-2 text-xs text-[color:var(--text-soft)]">
                <div>输入路径：{request.inputPath ?? "待补充"}</div>
                <div>日志路径：{request.logPath}</div>
                <div>配置清单：<span className="mono">{request.manifestPath}</span></div>
              </div>
            </details>
          </div>
        </Card>

        <Card eyebrow="下游血缘" title="这份请求产出了什么">
          <div className="space-y-3">
            <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
              候选模型 {candidates.length} 个 · 评测执行 {executions.length} 个 · 交接包 {handoffs.length} 个
            </div>
            {candidates.map((candidate) => (
              <div className="tech-highlight rounded-2xl p-4" key={candidate.id}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium">{candidate.title}</div>
                    <div className="mt-2 text-sm text-[color:var(--text-muted)]">{candidate.summary}</div>
                  </div>
                  <Button href={`/training/candidates/${candidate.id}`} variant="ghost">打开候选</Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
