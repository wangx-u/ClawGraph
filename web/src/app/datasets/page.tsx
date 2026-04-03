import { getDashboardBundle } from "@/lib/data-source";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { DatasetWorkspace } from "@/components/dashboard/dataset-workspace";

export default async function DatasetsPage() {
  const {
    bundle: { readinessRows, snapshots }
  } = await getDashboardBundle();
  const readyBuilders = readinessRows.filter((row) => row.ready).length;
  const predictedRecords = readinessRows.reduce((sum, row) => sum + row.predictedRecords, 0);

  if (!readinessRows.length && !snapshots.length) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="数据集"
          description="当前真实数据源里还没有可导出的 builder 或快照。先完成策展、监督或 bootstrap，再回来查看。"
          primaryAction={<Button href="/curation/candidates" variant="primary">返回策展</Button>}
          secondaryAction={<Button href="/flows/build-dataset" variant="secondary">查看导出流程</Button>}
        />
        <EmptyState
          actionHref="/curation/candidates"
          actionLabel="打开候选池"
          description="当 ClawGraph store 中出现就绪 builder 或历史 snapshot 后，这里会自动切换成高保真工作区。"
          title="还没有数据集资产"
        />
      </div>
    );
  }

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

      <DatasetWorkspace readinessRows={readinessRows} snapshots={snapshots} />
    </div>
  );
}
