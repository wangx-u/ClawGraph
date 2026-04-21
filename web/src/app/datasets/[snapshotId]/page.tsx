import { getDashboardBundle } from "@/lib/data-source";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";

export default async function SnapshotDetailPage({
  params
}: {
  params: Promise<{ snapshotId: string }>;
}) {
  const { snapshotId } = await params;
  const {
    bundle: { evalSuites, routerHandoffs, snapshots, trainingRequests }
  } = await getDashboardBundle();
  const snapshot = snapshots.find((item) => item.id === snapshotId) ?? snapshots[0];

  if (!snapshot) {
    return (
      <EmptyState
        actionHref="/datasets"
        actionLabel="返回数据集"
        description="当前还没有可查看的数据快照。先从训练批次导出第一份数据快照。"
        title="快照不存在"
      />
    );
  }

  const requests = trainingRequests ?? [];
  const suites = evalSuites ?? [];
  const handoffs = routerHandoffs ?? [];
  const relatedRequests = requests.filter((request) => request.datasetSnapshotId === snapshot.id);
  const relatedSuites = suites.filter(
    (suite) =>
      suite.datasetSnapshotId === snapshot.id ||
      relatedRequests.some((request) => request.evalSuiteId === suite.id)
  );
  const requestIds = new Set(relatedRequests.map((request) => request.id));
  const relatedLaunches = handoffs.filter((handoff) =>
    requests.some((request) => requestIds.has(request.id) && (request.handoffIds ?? []).includes(handoff.id))
  );
  const tabItems = [
    {
      id: "manifest",
      label: "导出清单",
      content: (
        <div className="grid gap-3 md:grid-cols-2">
          {[
            `Taxonomy 版本：${snapshot.taxonomyVersions?.join(", ") || "待补充"}`,
            `时间范围：${snapshot.timeRangeLabel ?? "待补充"}`,
            `切分策略：${snapshot.splitSummary ?? "待补充"}`,
            `批次约束：${snapshot.selectionSummary ?? "待补充"}`,
            `输出路径：${snapshot.outputPath}`
          ].map((line) => (
            <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]" key={line}>
              {line}
            </div>
          ))}
          <details className="panel-soft rounded-2xl p-4 md:col-span-2">
            <summary className="cursor-pointer text-sm font-medium text-[color:var(--text)]">查看技术明细</summary>
            <div className="mono mt-3 text-xs text-[color:var(--text-soft)]">{snapshot.id}</div>
          </details>
        </div>
      )
    },
    {
      id: "split",
      label: "切分分布",
      content: (
        <div className="grid gap-3 md:grid-cols-3">
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">样本单元：{snapshot.sampleUnit}</div>
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">记录数：{snapshot.recordCount}</div>
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">来源批次：{snapshot.cohortName ?? snapshot.cohortId}</div>
        </div>
      )
    },
    {
      id: "preview",
      label: "记录说明",
      content: (
          <div className="space-y-3">
            <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            这份快照主要承载 {snapshot.builder} 导出类型的结果，当前以 {snapshot.sampleUnit} 为样本单元。
            </div>
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            如果要继续训练或评测，优先检查切分策略、selection summary 和下游套件是否与当前用途一致。
          </div>
        </div>
      )
    },
    {
      id: "lineage",
      label: "谱系",
      content: (
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">训练请求</div>
            <div className="mt-3 space-y-3">
              {relatedRequests.length ? relatedRequests.map((request) => (
                <div key={request.id}>
                  <div className="font-medium">{request.title}</div>
                  <div className="mt-1 text-sm text-[color:var(--text-muted)]">{request.summary}</div>
                </div>
              )) : <div className="text-sm text-[color:var(--text-muted)]">还没有关联训练请求。</div>}
            </div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">评测套件</div>
            <div className="mt-3 space-y-3">
              {relatedSuites.length ? relatedSuites.map((suite) => (
                <div key={suite.id}>
                  <div className="font-medium">{suite.title ?? suite.id}</div>
                  <div className="mt-1 text-sm text-[color:var(--text-muted)]">{suite.kind} · {suite.items} 项</div>
                </div>
              )) : <div className="text-sm text-[color:var(--text-muted)]">还没有关联评测套件。</div>}
            </div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">上线接替</div>
            <div className="mt-3 space-y-3">
              {relatedLaunches.length ? relatedLaunches.map((handoff) => (
                <div key={handoff.id}>
                  <div className="font-medium">{handoff.title}</div>
                  <div className="mt-1 text-sm text-[color:var(--text-muted)]">{handoff.trafficScope ?? handoff.sliceLabel ?? handoff.sliceId}</div>
                </div>
              )) : <div className="text-sm text-[color:var(--text-muted)]">还没有关联上线接替资产。</div>}
            </div>
          </div>
        </div>
      )
    }
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={snapshot.title ?? `${snapshot.builder} 数据快照`}
        description="查看单个冻结快照的导出清单、切分策略、上下游关系和导出输出，确保后续评测与训练都能追溯来源。"
        primaryAction={<Button href="/evaluation" variant="primary">创建评测套件</Button>}
        secondaryAction={<Button href="/datasets" variant="secondary">返回数据集</Button>}
      />

      <Card eyebrow="快照摘要" title={snapshot.builder} strong>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="tech-highlight rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">导出类型</div><div className="mt-3 text-xl font-semibold">{snapshot.builder}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">样本单元</div><div className="mt-3 text-xl font-semibold">{snapshot.sampleUnit}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">记录数</div><div className="mt-3 text-xl font-semibold">{snapshot.recordCount}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">来源批次</div><div className="mt-3 text-xl font-semibold">{snapshot.cohortName ?? snapshot.cohortId}</div></div>
        </div>
      </Card>

      <Card eyebrow="快照内容" title="数据快照说明">
        <Tabs active="manifest" items={tabItems} />
      </Card>
    </div>
  );
}
