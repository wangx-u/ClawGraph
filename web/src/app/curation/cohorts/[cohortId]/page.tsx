import { getDashboardBundle } from "@/lib/data-source";
import { getDatasetBuilderMeta } from "@/lib/dataset-flow";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";

export default async function CohortDetailPage({
  params
}: {
  params: Promise<{ cohortId: string }>;
}) {
  const { cohortId } = await params;
  const {
    bundle: { cohorts, evalSuites, readinessRows, routerHandoffs, snapshots, trainingRequests }
  } = await getDashboardBundle();
  const cohort = cohorts.find((item) => item.id === cohortId) ?? cohorts[0];

  if (!cohort) {
    return (
      <EmptyState
        actionHref="/curation/candidates"
        actionLabel="打开候选池"
        description="当前还没有冻结的数据批次。先从候选池冻结一版训练批次。"
        title="数据批次不存在"
      />
      );
  }

  const cohortSnapshots = snapshots.filter((snapshot) => snapshot.cohortId === cohort.id);
  const cohortSnapshotIds = new Set(cohortSnapshots.map((snapshot) => snapshot.id));
  const latestSnapshot = cohortSnapshots.slice(-1)[0];
  const relatedRequests = (trainingRequests ?? []).filter((request) =>
    request.datasetSnapshotId ? cohortSnapshotIds.has(request.datasetSnapshotId) : false
  );
  const relatedSuiteIds = new Set(
    [
      ...(evalSuites ?? [])
        .filter((suite) => suite.datasetSnapshotId && cohortSnapshotIds.has(suite.datasetSnapshotId))
        .map((suite) => suite.id),
      ...relatedRequests
        .map((request) => request.evalSuiteId)
        .filter((value): value is string => Boolean(value))
    ]
  );
  const relatedSuites = (evalSuites ?? []).filter((suite) => relatedSuiteIds.has(suite.id));
  const relatedHandoffs = (routerHandoffs ?? []).filter((handoff) =>
    relatedRequests.some((request) => (request.handoffIds ?? []).includes(handoff.id))
  );
  const readyBuilders = readinessRows.filter((row) => row.ready);
  const blockedBuilders = readinessRows.filter((row) => !row.ready);
  const nextAction = latestSnapshot
    ? "当前批次已经导出过数据快照，优先打开最近版本确认是否还要刷新版本，或继续接训练和评测。"
    : readyBuilders.length
      ? "当前批次已经有可导出的类型，先进入数据集工作区确认导出类型，再冻结首版快照。"
      : "当前批次还没有 ready builder，先回候选池补齐标签、复核和阻塞条件。";

  return (
    <div className="space-y-6">
      <PageHeader
        title={cohort.title ?? cohort.name}
        description="先确认这批训练数据是否已经满足导出条件，再从 ready builder 冻结首版或新版本；已有快照时直接继续串到训练、评测和上线。"
        primaryAction={
          <Button href={latestSnapshot ? `/datasets/${latestSnapshot.id}` : "/datasets"} variant="primary">
            {latestSnapshot ? "打开最近快照" : "进入数据集工作区"}
          </Button>
        }
        secondaryAction={
          <Button href={blockedBuilders.length ? "/curation/candidates" : "/datasets"} variant="secondary">
            {blockedBuilders.length ? "回候选池补数据" : "查看导出队列"}
          </Button>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card eyebrow="批次摘要" title={cohort.name} strong>
          <div className="grid gap-3 md:grid-cols-4">
            <div className="tech-highlight rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">用途</div><div className="mt-3 text-xl font-semibold">{cohort.purpose}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">选中</div><div className="mt-3 text-xl font-semibold">{cohort.selectedCount}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">保留集</div><div className="mt-3 text-xl font-semibold">{cohort.holdoutCount}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">待复核</div><div className="mt-3 text-xl font-semibold">{cohort.reviewCount}</div></div>
          </div>
        </Card>
        <Card eyebrow="当前批次动作" title="先决定是否进入导出">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={readyBuilders.length ? "success" : "warning"}>
              {readyBuilders.length ? `${readyBuilders.length} 个导出类型就绪` : "还没有可导出类型"}
            </Badge>
            <Badge tone={latestSnapshot ? "info" : "neutral"}>
              {latestSnapshot ? `${cohortSnapshots.length} 份历史快照` : "还没有历史快照"}
            </Badge>
          </div>
          <div className="mt-4 grid gap-3 xl:grid-cols-3">
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">Step 1 批次成员</div>
              <div className="mt-2 font-medium">{cohort.selectedCount} 条已选记录</div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                保留集 {cohort.holdoutCount} · 待复核 {cohort.reviewCount}
              </div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">Step 2 导出类型</div>
              <div className="mt-2 font-medium">
                {readyBuilders.length
                  ? readyBuilders.map((row) => getDatasetBuilderMeta(row.builder).label).join(" / ")
                  : "先补齐 blocker"}
              </div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                {blockedBuilders[0]?.blockers[0] ?? "当前没有额外 blocker。"}
              </div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">Step 3 当前动作</div>
              <div className="mt-2 font-medium">
                {latestSnapshot ? "判断是否继续导出新版本" : readyBuilders.length ? "冻结首版快照" : "先回上游补数据"}
              </div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">{nextAction}</div>
            </div>
          </div>
          <div className="mt-4 rounded-2xl bg-white/70 px-4 py-3 text-sm text-[color:var(--text-muted)]">
            {latestSnapshot
              ? `最近版本是 ${latestSnapshot.title ?? latestSnapshot.id}，可直接继续接训练、评测或上线链路。`
              : readyBuilders.length
                ? "当前训练批次已经具备进入数据集导出的条件。"
                : "先返回候选池处理低置信样本和缺失 blocker，再回来导出。"}
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button href={latestSnapshot ? `/datasets/${latestSnapshot.id}` : "/datasets"} variant="primary">
              {latestSnapshot ? "打开最近快照" : "去冻结首版快照"}
            </Button>
            <Button href="/datasets" variant="secondary">查看全部导出类型</Button>
            <Button href={relatedRequests.length ? "/training" : "/evaluation"} variant="ghost">
              {relatedRequests.length ? "查看下游训练" : "查看评测入口"}
            </Button>
          </div>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <Card eyebrow="冻结规则" title="批次说明">
          <div className="space-y-3">
            {[
              `覆盖任务：${cohort.sliceLabels?.join(" / ") || cohort.sliceIds.join(", ")}`,
              `筛选规则：${cohort.selectionSummary ?? "待补充"}`,
              `时间范围：${cohort.timeRangeLabel ?? "待补充"}`,
              `质量门槛：${cohort.qualityGateLabel ?? "待补充"}`
            ].map((line) => (
              <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]" key={line}>
                {line}
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-2xl bg-white/70 px-4 py-3 text-sm text-[color:var(--text-muted)]">
            批次 ID：<span className="mono">{cohort.id}</span>
          </div>
        </Card>
        <Card eyebrow="下游消费" title="这批数据现在接到了哪里">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="tech-highlight rounded-2xl p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">数据快照</div>
              <div className="mt-3 text-2xl font-semibold">{cohortSnapshots.length}</div>
            </div>
            <div className="panel-soft rounded-2xl p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">训练请求</div>
              <div className="mt-3 text-2xl font-semibold">{relatedRequests.length}</div>
            </div>
            <div className="panel-soft rounded-2xl p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">评测 / 上线</div>
              <div className="mt-3 text-2xl font-semibold">{relatedSuites.length} / {relatedHandoffs.length}</div>
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {cohortSnapshots.length ? (
              cohortSnapshots.map((snapshot) => {
                const snapshotRequests = relatedRequests.filter((request) => request.datasetSnapshotId === snapshot.id);
                const snapshotSuites = relatedSuites.filter(
                  (suite) =>
                    suite.datasetSnapshotId === snapshot.id ||
                    snapshotRequests.some((request) => request.evalSuiteId === suite.id)
                );
                const snapshotHandoffs = relatedHandoffs.filter((handoff) =>
                  snapshotRequests.some((request) => (request.handoffIds ?? []).includes(handoff.id))
                );
                const meta = getDatasetBuilderMeta(snapshot.builder);

                return (
                  <div className="panel-soft rounded-[1.15rem] p-4" key={snapshot.id}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-medium">{snapshot.title ?? snapshot.id}</div>
                        <div className="mt-1 text-sm text-[color:var(--text-muted)]">
                          {meta.label} · {snapshot.recordCount} 条记录 · {snapshot.createdAt}
                        </div>
                      </div>
                      <Badge tone="info">已冻结</Badge>
                    </div>
                    <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                      训练 {snapshotRequests.length} · 评测 {snapshotSuites.length} · 上线 {snapshotHandoffs.length}
                    </div>
                    <div className="mt-3">
                      <Button href={`/datasets/${snapshot.id}`} variant="ghost">打开这份快照</Button>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="panel-soft rounded-[1.15rem] p-4 text-sm text-[color:var(--text-muted)]">
                当前批次还没有任何历史快照，先进入数据集工作区冻结首版。
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
