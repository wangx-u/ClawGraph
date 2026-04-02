import { getDashboardBundle } from "@/lib/data-source";
import { readinessLabel } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";

export default async function DatasetsPage() {
  const {
    bundle: { readinessRows, snapshots }
  } = await getDashboardBundle();
  const readyBuilders = readinessRows.filter((row) => row.ready).length;
  const predictedRecords = readinessRows.reduce((sum, row) => sum + row.predictedRecords, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="数据集"
        description="在导出之前查看各类 builder 的 readiness、阻塞项和快照历史，确保每次写出都带完整 manifest。"
        primaryAction={<Button href="/flows/build-dataset" variant="primary">导出快照</Button>}
        secondaryAction={<Button href="/curation/candidates" variant="secondary">返回策展</Button>}
      />

      <div className="grid gap-4 md:grid-cols-3">
        <div className="surface-strong rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">已就绪 Builder</div>
          <div className="mt-3 text-3xl font-semibold">{readyBuilders}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">预测总记录</div>
          <div className="mt-3 text-3xl font-semibold">{predictedRecords}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">最近快照数</div>
          <div className="mt-3 text-3xl font-semibold">{snapshots.length}</div>
        </div>
      </div>

      <Card eyebrow="Builder 目录" title="支持的数据集家族" strong>
        <Tabs active="sft" items={["facts", "sft", "preference", "binary_rl"]} />
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card eyebrow="Readiness" title="Builder 就绪度">
          <DataTable
            headers={["Builder", "状态", "预测记录", "阻塞项"]}
            rows={readinessRows.map((row) => [
              row.builder,
              <Badge key={`${row.builder}-ready`} tone={row.ready ? "success" : "warning"}>{readinessLabel(row.ready)}</Badge>,
              row.predictedRecords,
              row.blockers.length ? row.blockers.join("，") : "无"
            ])}
          />
        </Card>

        <Card eyebrow="快照历史" title="最近导出的数据快照">
          <DataTable
            headers={["Snapshot", "Builder", "样本单元", "Cohort", "记录数", "创建时间", "动作"]}
            rows={snapshots.map((snapshot) => [
              <span className="mono text-xs text-[color:var(--text-soft)]" key={`${snapshot.id}-id`}>{snapshot.id}</span>,
              snapshot.builder,
              snapshot.sampleUnit,
              snapshot.cohortId,
              snapshot.recordCount,
              snapshot.createdAt,
              <Button href={`/datasets/${snapshot.id}`} key={`${snapshot.id}-action`} variant="secondary">打开</Button>
            ])}
          />
        </Card>
      </div>
    </div>
  );
}
