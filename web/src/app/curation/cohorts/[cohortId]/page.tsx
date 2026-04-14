import { getDashboardBundle } from "@/lib/data-source";
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
    bundle: { cohorts }
  } = await getDashboardBundle();
  const cohort = cohorts.find((item) => item.id === cohortId) ?? cohorts[0];

  if (!cohort) {
    return (
      <EmptyState
        actionHref="/curation/candidates"
        actionLabel="打开候选池"
        description="当前还没有冻结的 cohort。先从 candidate pool 冻结一版 cohort。"
        title="Cohort 不存在"
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={cohort.title ?? cohort.name}
        description="在导出数据快照或建立评测资产之前，先确认 cohort 成员构成、manifest 意图以及下游消费路径。"
        primaryAction={<Button href="/datasets" variant="primary">打开数据集</Button>}
        secondaryAction={<Button href="/evaluation" variant="secondary">创建评测套件</Button>}
      />

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card eyebrow="Cohort 摘要" title={cohort.name} strong>
          <div className="grid gap-3 md:grid-cols-4">
            <div className="tech-highlight rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">用途</div><div className="mt-3 text-xl font-semibold">{cohort.purpose}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">选中</div><div className="mt-3 text-xl font-semibold">{cohort.selectedCount}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">保留集</div><div className="mt-3 text-xl font-semibold">{cohort.holdoutCount}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">待复核</div><div className="mt-3 text-xl font-semibold">{cohort.reviewCount}</div></div>
          </div>
        </Card>
        <Card eyebrow="Manifest 预览" title="冻结摘要">
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
            Cohort ID：<span className="mono">{cohort.id}</span>
          </div>
        </Card>
      </div>
    </div>
  );
}
