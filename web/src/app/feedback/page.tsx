import { getDashboardBundle } from "@/lib/data-source";
import { genericStatusLabel, genericStatusTone, workflowStageLabel } from "@/lib/presenters";
import { confirmRunByHuman, markFeedbackReviewed, resolveFeedback } from "@/app/feedback/actions";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";

export default async function FeedbackPage() {
  const {
    bundle: { cohorts, feedbackItems },
    meta
  } = await getDashboardBundle();
  const cohortHref = cohorts[0] ? `/curation/cohorts/${cohorts[0].id}` : "/curation/candidates";
  const queuedCount = feedbackItems.filter((item) => item.status === "queued").length;
  const reviewedCount = feedbackItems.filter((item) => item.status === "reviewed").length;
  const resolvedCount = feedbackItems.filter((item) => item.status === "resolved").length;
  const canMutate = Boolean(meta.supportsMutations);

  return (
    <div className="space-y-6">
      <PageHeader
        title="人工复核"
        description="把低置信、失败和分歧样本送回复查、数据准备或数据筛选，形成可追溯的闭环。"
        primaryAction={<Button href="/sessions" variant="primary">打开会话收件箱</Button>}
        secondaryAction={<Button href={cohortHref} variant="secondary">查看当前批次</Button>}
      />

      <div className="grid gap-4 md:grid-cols-3">
        <Card eyebrow="待处理" title={String(queuedCount)}>还需要人工决定下一步。</Card>
        <Card eyebrow="已人工确认" title={String(reviewedCount)}>已经确认过，但还未正式关闭。</Card>
        <Card eyebrow="已关闭" title={String(resolvedCount)}>已完成处理，不再阻塞当前流程。</Card>
      </div>

      {!canMutate ? (
        <Card eyebrow="当前模式" title="此数据源暂为只读" strong>
          <p className="text-sm leading-6 text-[color:var(--text-muted)]">
            当前页面连接的数据源暂不支持写操作。浏览器内直接 resolve / override 需要启用首方
            Dashboard HTTP API，或让当前部署拥有本地 store 写入能力。
          </p>
        </Card>
      ) : null}

      <div className="grid gap-4">
        {feedbackItems.map((item) => (
          <Card
            action={
              <Badge tone={genericStatusTone(item.status)}>
                {genericStatusLabel(item.status)}
              </Badge>
            }
            eyebrow={item.sliceLabel ?? item.sliceId}
            key={item.id}
            strong={item.status === "queued"}
            title={item.targetLabel ?? item.targetRef}
          >
            <div className="space-y-4">
              <p className="text-sm leading-6 text-[color:var(--text-muted)]">{item.reason}</p>
              <div className="grid gap-3 md:grid-cols-3">
                <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
                  <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">任务</div>
                  <div className="mt-2">{item.taskLabel ?? "待识别"}</div>
                </div>
                <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
                  <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">流程阶段</div>
                  <div className="mt-2">{workflowStageLabel(item.stage ?? undefined)}</div>
                </div>
                <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
                  <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">处理记录</div>
                  <div className="mt-2">{item.resolutionNote ?? item.reviewer ?? "等待处理"}</div>
                </div>
              </div>

              <div className="flex flex-wrap gap-3">
                {canMutate && item.status === "queued" && item.sessionId && item.runId ? (
                  <form action={confirmRunByHuman}>
                    <input name="feedbackId" type="hidden" value={item.id} />
                    <input name="sessionId" type="hidden" value={item.sessionId} />
                    <input name="runId" type="hidden" value={item.runId} />
                    <Button type="submit" variant="primary">人工确认并入池</Button>
                  </form>
                ) : null}

                {canMutate && item.status === "queued" ? (
                  <form action={markFeedbackReviewed}>
                    <input name="feedbackId" type="hidden" value={item.id} />
                    <Button type="submit" variant="secondary">标记已人工确认</Button>
                  </form>
                ) : null}

                {canMutate && item.status !== "resolved" ? (
                  <form action={resolveFeedback}>
                    <input name="feedbackId" type="hidden" value={item.id} />
                    <Button type="submit" variant="ghost">关闭当前事项</Button>
                  </form>
                ) : null}

                {item.sessionId && item.runId ? (
                  <Button href={`/sessions/${item.sessionId}/runs/${item.runId}/replay`} variant="secondary">
                    查看回放
                  </Button>
                ) : null}
              </div>
            </div>
          </Card>
        ))}

        {!feedbackItems.length ? (
          <Card eyebrow="回流队列" title="当前没有待处理事项" strong>
            <p className="text-sm leading-6 text-[color:var(--text-muted)]">
              新的低置信或失败样本会自动出现在这里，人工处理后会直接回写到同一份 store。
            </p>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
