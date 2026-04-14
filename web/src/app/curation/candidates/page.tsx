import { getDashboardBundle } from "@/lib/data-source";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { FilterBar } from "@/components/ui/filter-bar";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";

export default async function CandidatePoolPage() {
  const {
    bundle: { candidates, cohorts, slices }
  } = await getDashboardBundle();
  const eligibleCount = candidates.filter((item) => item.status === "eligible").length;
  const reviewCount = candidates.filter((item) => item.status === "review").length;
  const holdoutCount = candidates.filter((item) => item.status === "holdout").length;
  const cohortHref = cohorts[0] ? `/curation/cohorts/${cohorts[0].id}` : "/datasets";
  const primarySlice = slices[0];

  return (
    <div className="space-y-6">
      <PageHeader
        title="数据筛选"
        description="围绕切片复查候选运行、处理低置信样本，并决定哪些数据可以进入下一版冻结批次。"
        primaryAction={<Button href={cohortHref} variant="primary">查看冻结结果</Button>}
        secondaryAction={<Button href="/datasets" variant="secondary">打开导出流</Button>}
      />
      <FilterBar
        filters={[
          `当前切片：${primarySlice?.id ?? "全部"}`,
          "质量阈值：动态",
          "Verifier 阈值：动态",
          "来源：全部",
          "时间：最近 30 天"
        ]}
      />

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card eyebrow="候选统计" title="候选样本概览" strong>
          <div className="grid gap-3 md:grid-cols-4">
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">总量</div><div className="mt-3 text-2xl font-semibold">{candidates.length}</div></div>
            <div className="tech-highlight rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">可入池</div><div className="mt-3 text-2xl font-semibold">{eligibleCount}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">待复核</div><div className="mt-3 text-2xl font-semibold">{reviewCount}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">保留集</div><div className="mt-3 text-2xl font-semibold">{holdoutCount}</div></div>
          </div>
        </Card>
        <Card eyebrow="复核队列" title="当前最常见的阻塞原因">
          <div className="space-y-3">
            {(candidates
              .filter((candidate) => candidate.status !== "eligible")
              .slice(0, 5)
              .map((candidate) => `${candidate.runId} · ${genericStatusLabel(candidate.status)}`) || []
            ).map((reason) => (
              <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]" key={reason}>
                {reason}
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card eyebrow="候选列表" title="候选样本表">
        <DataTable
          headers={["Run", "Task Instance", "Template Hash", "质量", "Verifier", "来源", "Cluster", "状态"]}
          rows={candidates.map((candidate) => [
            <span className="mono text-xs text-[color:var(--text-soft)]" key={`${candidate.runId}-id`}>{candidate.runId}</span>,
            candidate.taskInstanceKey,
            candidate.templateHash,
            candidate.quality.toFixed(2),
            candidate.verifier.toFixed(2),
            candidate.source,
            candidate.clusterId,
            <Badge key={`${candidate.runId}-status`} tone={genericStatusTone(candidate.status)}>{genericStatusLabel(candidate.status)}</Badge>
          ])}
        />
      </Card>
    </div>
  );
}
