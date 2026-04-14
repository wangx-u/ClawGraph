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
    bundle: { snapshots }
  } = await getDashboardBundle();
  const snapshot = snapshots.find((item) => item.id === snapshotId) ?? snapshots[0];

  if (!snapshot) {
    return (
      <EmptyState
        actionHref="/datasets"
        actionLabel="返回数据集"
        description="当前还没有可查看的数据快照。先从 cohort 导出第一份 snapshot。"
        title="快照不存在"
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={snapshot.title ?? `数据快照 ${snapshot.id}`}
        description="查看单个冻结快照的 manifest、切分策略、lineage 和导出输出，确保后续评测与训练都能追溯来源。"
        primaryAction={<Button href="/evaluation" variant="primary">创建评测套件</Button>}
        secondaryAction={<Button href="/datasets" variant="secondary">返回数据集</Button>}
      />

      <Card eyebrow="快照摘要" title={snapshot.builder} strong>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="tech-highlight rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">Builder</div><div className="mt-3 text-xl font-semibold">{snapshot.builder}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">样本单元</div><div className="mt-3 text-xl font-semibold">{snapshot.sampleUnit}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">记录数</div><div className="mt-3 text-xl font-semibold">{snapshot.recordCount}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">来源批次</div><div className="mt-3 text-xl font-semibold">{snapshot.cohortName ?? snapshot.cohortId}</div></div>
        </div>
      </Card>

      <Card eyebrow="快照标签" title="Manifest 浏览器">
        <Tabs active="Manifest" items={["Manifest", "切分分布", "记录预览", "谱系"]} />
        <div className="mt-5 grid gap-3 md:grid-cols-2">
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
        </div>
        <div className="mt-4 rounded-2xl bg-white/70 px-4 py-3 text-sm text-[color:var(--text-muted)]">
          快照 ID：<span className="mono">{snapshot.id}</span>
        </div>
      </Card>
    </div>
  );
}
